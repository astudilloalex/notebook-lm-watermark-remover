"""Disposable session directories with interprocess exclusion."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import uuid


OWNER = "notebooklm-studio-session-v1"
MARKER = ".notebooklm-session.json"


def lock_file(stream, blocking=True):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))


def unlock_file(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def open_lock(path, create=True):
    stream = path.open("a+b" if create else "r+b")
    if create and path.stat().st_size == 0:
        stream.write(b"0")
        stream.flush()
    return stream


@contextmanager
def store_lock(root):
    with open_lock(root / ".indice.lock") as stream:
        lock_file(stream)
        try:
            yield
        finally:
            unlock_file(stream)


def owned_session(path):
    if path.is_symlink() or not path.is_dir() or not re.fullmatch(r"sesion-[a-f0-9]{32}", path.name):
        return False
    marker = path / MARKER
    if marker.is_symlink():
        return False
    try:
        data = json.loads(marker.read_text())
        return data == {"owner": OWNER, "name": path.name}
    except (OSError, ValueError):
        return False


def remove_tree(path):
    for attempt in range(5):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 4:
                raise
            time.sleep(.1)


def remove_session(path):
    # Retain ownership metadata if a file remains locked by the OS.
    for child in path.iterdir():
        if child.name in (MARKER, ".activa.lock"):
            continue
        if child.is_dir() and not child.is_symlink():
            remove_tree(child)
        else:
            child.unlink(missing_ok=True)
    (path / ".activa.lock").unlink(missing_ok=True)
    (path / MARKER).unlink()
    path.rmdir()


class SessionDirectory:
    def __init__(self, root=None):
        self.root = Path(root or Path(tempfile.gettempdir()) / "NotebookLM-Studio-Sesiones").expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.closed = False
        self.stream = None
        self.abandoned_removed = 0
        self.cleanup_pending = 0
        with store_lock(self.root):
            for path in self.root.iterdir():
                if not owned_session(path):
                    continue
                try:
                    with open_lock(path / ".activa.lock", create=False) as stream:
                        lock_file(stream, blocking=False)
                        unlock_file(stream)
                    remove_session(path)
                    self.abandoned_removed += 1
                except OSError:
                    # An active session keeps its lock until it exits.
                    self.cleanup_pending += 1
            self.path = self.root / ("sesion-" + uuid.uuid4().hex)
            self.path.mkdir(mode=0o700)
            try:
                self.stream = open_lock(self.path / ".activa.lock")
                lock_file(self.stream)
                (self.path / MARKER).write_text(json.dumps({"owner": OWNER, "name": self.path.name}))
            except BaseException:
                if self.stream:
                    self.stream.close()
                remove_tree(self.path)
                raise

    def close(self):
        if self.closed:
            return
        with store_lock(self.root):
            if self.stream:
                self.stream.close()
                self.stream = None
            if self.path.exists():
                if not owned_session(self.path):
                    raise OSError("La carpeta de sesión no tiene una identificación válida; no se ha eliminado.")
                remove_session(self.path)
            self.closed = True
