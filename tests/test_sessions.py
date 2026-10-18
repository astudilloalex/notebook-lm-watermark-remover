"""Session cleanup, interprocess isolation and crash recovery."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str((Path(__file__).resolve().parents[1] / "app")))
from sesion_temporal import SessionDirectory, MARKER, OWNER


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.store=self.root/'Sesiones'

    def tearDown(self):
        self.temp.cleanup()

    def test_cleanup_owns_only_its_session_and_is_idempotent(self):
        self.store.mkdir()
        legacy=self.store/'Resultados'
        legacy.mkdir()
        sentinel=legacy/'guardado.mp4'
        sentinel.write_bytes(b'legacy')
        downloads=self.root/'Descargas'
        downloads.mkdir()
        saved=downloads/'video.mp4'
        saved.write_bytes(b'downloaded')
        session=SessionDirectory(self.store)
        generated=session.path/'Resultados'
        generated.mkdir()
        (generated/'video.mp4').write_bytes(b'temporary')
        session.close()
        session.close()
        self.assertFalse(session.path.exists())
        self.assertEqual(sentinel.read_bytes(),b'legacy')
        self.assertEqual(saved.read_bytes(),b'downloaded')

    def test_parallel_sessions_do_not_clean_each_other(self):
        first=SessionDirectory(self.store)
        (first.path/'alive.mp4').write_bytes(b'active')
        second=SessionDirectory(self.store)
        try:
            self.assertTrue(first.path.exists())
            self.assertNotEqual(first.path,second.path)
            first.close()
            self.assertTrue(second.path.exists())
        finally:
            first.close()
            second.close()

    def test_abandoned_session_is_deleted_at_next_start(self):
        code="import os,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from sesion_temporal import SessionDirectory;s=SessionDirectory(Path(sys.argv[2]));(s.path/'video.mp4').write_bytes(b'crash');print(s.path,flush=True);os._exit(3)"
        result=subprocess.run([sys.executable,'-u','-c',code,str((Path(__file__).resolve().parents[1] / "app")),str(self.store)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,3,result.stderr)
        abandoned=Path(result.stdout.strip())
        self.assertTrue(abandoned.exists())
        next_session=SessionDirectory(self.store)
        try:
            self.assertFalse(abandoned.exists())
            self.assertEqual(next_session.abandoned_removed,1)
        finally:
            next_session.close()

    def test_active_session_in_another_process_is_preserved(self):
        code="import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from sesion_temporal import SessionDirectory;s=SessionDirectory(Path(sys.argv[2]));print(s.path,flush=True);sys.stdin.read();s.close()"
        process=subprocess.Popen([sys.executable,'-u','-c',code,str((Path(__file__).resolve().parents[1] / "app")),str(self.store)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            active=Path(process.stdout.readline().strip())
            self.assertTrue(active.is_dir())
            other=SessionDirectory(self.store)
            try:
                self.assertTrue(active.exists())
            finally:
                other.close()
            process.communicate('',timeout=10)
            self.assertEqual(process.returncode,0)
            self.assertFalse(active.exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)

    def test_unmarked_directories_and_symlinks_are_not_purged(self):
        self.store.mkdir()
        unknown=self.store/('sesion-'+'0'*32)
        unknown.mkdir()
        (unknown/'important.mp4').write_bytes(b'unknown')
        outside=self.root/'outside'
        outside.mkdir()
        target=outside/'video.mp4'
        target.write_bytes(b'outside')
        (outside/MARKER).write_text(json.dumps({'owner':OWNER,'name':'sesion-'+'1'*32}))
        if os.name!='nt':
            (self.store/('sesion-'+'1'*32)).symlink_to(outside,target_is_directory=True)
        session=SessionDirectory(self.store)
        session.close()
        self.assertEqual(target.read_bytes(),b'outside')
        self.assertTrue((unknown/'important.mp4').exists())


if __name__=='__main__':
    unittest.main(verbosity=2)
