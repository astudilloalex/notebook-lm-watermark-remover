"""Entrada de los paquetes que incluyen su propio intérprete y herramientas."""

from pathlib import Path
import os
import sys
import traceback

APP = Path(__file__).resolve().parent
sys.path.insert(0, str(APP))


def data_directory() -> Path:
    explicit = os.environ.get("NOTEBOOKLM_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "NotebookLM Studio"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "NotebookLM Studio"
    base = os.environ.get("XDG_DATA_HOME", "")
    return (Path(base) if base and Path(base).is_absolute() else Path.home() / ".local/share") / "notebooklm-studio"


def main() -> int:
    # El paquete mantiene su intérprete aislado también en los procesos hijos.
    os.environ.pop("PYTHONHOME", None)
    os.environ.pop("PYTHONPATH", None)
    data = data_directory()
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    # El navegador recibe la interfaz; los diagnósticos quedan en un archivo.
    with (data / "aplicacion.log").open("w", encoding="utf-8", buffering=1) as log:
        os.chmod(data / "aplicacion.log", 0o600)
        old_out, old_error = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = log
        try:
            import interfaz_local
            arguments = list(sys.argv[1:])
            if "--resultados" not in arguments and "--sesiones" not in arguments:
                arguments += ["--sesiones", str(data / "Sesiones")]
            # Se verifica el contenido local del paquete, no el PATH del equipo.
            suffix = ".exe" if os.name == "nt" else ""
            for tool in ("ffmpeg", "ffprobe"):
                if not (APP / "bin" / (tool + suffix)).is_file():
                    raise RuntimeError("Falta una herramienta incluida en el paquete: " + tool)
            interfaz_local.main(arguments)
            return 0
        except KeyboardInterrupt:
            return 130
        except Exception:
            traceback.print_exc()
            if os.name == "nt":
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, "No se pudo iniciar la aplicación. Comprueba que descomprimiste el paquete completo.\n\nEl detalle está en:\n" + str(data / "aplicacion.log"), "NotebookLM Studio", 0x10)
            return 1
        finally:
            sys.stdout, sys.stderr = old_out, old_error


if __name__ == "__main__":
    raise SystemExit(main())
