#!/usr/bin/env python3
"""Interfaz de navegador local para el procesador NotebookLM."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from collections import deque
from dataclasses import asdict, dataclass, field
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, quote, unquote, urlparse
import uuid
import webbrowser
import zipfile

import notebooklm_ffmpeg as core
from sesion_temporal import SessionDirectory

ROOT = Path(__file__).resolve().parent
DEFAULTS = {"perfil": "auto", "modo": "calidad", "recortar": True,
            "recorte_modo": "auto", "recorte_fotogramas": 90, "recorte_segundos": 3.0,
            "inteligente": False, "rtl": False, "rect": ""}
PROFILE_NAMES = {"auto": "Automático", "explainer": "Horizontal · Explainer",
                 "cinematic": "Horizontal · Cinematic", "short": "Short vertical",
                 "legacy": "Short antiguo", "manual": "Región personalizada"}


class AppError(Exception):
    pass


class Cancelled(Exception):
    pass


def hidden_process_options() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def find_tool(name: str) -> str | None:
    executable = name + (".exe" if os.name == "nt" else "")
    for folder in (ROOT / "bin", ROOT / "herramientas"):
        candidate = folder / executable
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    # Finder y los accesos directos pueden tener un PATH más reducido.
    for folder in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"):
        candidate = Path(folder) / executable
        if candidate.is_file():
            return str(candidate)
    return None


def validated_settings(values: dict) -> dict:
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise AppError("Los ajustes recibidos no son válidos.")
    result = dict(DEFAULTS)
    result.update(values)
    if result["perfil"] not in PROFILE_NAMES or result["modo"] not in ("calidad", "equilibrado", "rapido"):
        raise AppError("Selecciona un formato y una calidad de la lista.")
    if any(type(result[key]) is not bool for key in ("recortar", "inteligente", "rtl")):
        raise AppError("Los interruptores de los ajustes no son válidos.")
    if result["recorte_modo"] not in ("auto", "fotogramas", "segundos"):
        raise AppError("Selecciona un modo de recorte de la lista.")
    if type(result["recorte_fotogramas"]) is not int or result["recorte_fotogramas"] < 0:
        raise AppError("Los fotogramas a recortar deben ser un número entero igual o mayor que cero.")
    seconds = result["recorte_segundos"]
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
        raise AppError("Los segundos a recortar deben ser un número finito igual o mayor que cero.")
    if not isinstance(result["rect"], str) or len(result["rect"]) > 80:
        raise AppError("La región debe tener el formato X:Y:ANCHO:ALTO.")
    if result["rect"].strip():
        try:
            core.parse_rect(result["rect"].strip())
        except argparse.ArgumentTypeError as exc:
            raise AppError(str(exc)) from exc
    if result["perfil"] == "manual" and not result["rect"].strip():
        raise AppError("Introduce la región para utilizar el formato personalizado.")
    if result["inteligente"] and (result["rect"].strip() or result["perfil"] in ("short", "legacy", "manual")):
        raise AppError("La detección superior se utiliza en horizontales, sin región personalizada.")
    return result


def validate_item_settings(item: Item, settings: dict) -> None:
    if not item.info:
        return
    if settings["rect"].strip():
        core.parse_rect(settings["rect"].strip()).validate(item.info.width, item.info.height)
    if settings["recortar"] and settings["recorte_modo"] != "auto":
        if settings["recorte_modo"] == "fotogramas":
            frames = settings["recorte_fotogramas"]
            too_long = frames >= item.info.frames if item.info.frames else frames / float(item.info.fps) >= item.info.duration
        else:
            too_long = settings["recorte_segundos"] >= item.info.duration
        if too_long:
            raise AppError("El recorte debe ser menor que la duración del vídeo. Reduce la cantidad o desactiva el recorte.")


@dataclass
class Item:
    id: str
    name: str
    size: int
    source: Path
    info: core.VideoInfo | None = None
    settings: dict = field(default_factory=lambda: dict(DEFAULTS))
    state: str = "ready"
    progress: float = 0
    message: str = "Listo para procesar"
    error: str = ""
    output: Path | None = None
    preview: Path | None = None
    preview_version: str = ""
    preview_settings: dict | None = None
    preview_at: float | None = None
    tail: Path | None = None
    tail_version: str = ""
    tail_start: float = 0
    tail_start_frame: int = 0
    tail_total_frames: int = 0
    tail_window: float = 0
    tail_precise: bool = False
    tail_error: str = ""


class Application:
    def __init__(self, sessions_dir: Path | None = None):
        self.session = SessionDirectory(sessions_dir)
        self.work_dir = self.session.path
        self.output_dir = self.work_dir / "Resultados"
        (self.work_dir / "inputs").mkdir(parents=True, exist_ok=True)
        (self.work_dir / "previews").mkdir(exist_ok=True)
        self.items: dict[str, Item] = {}
        self.lock = threading.RLock()
        self.transfer_condition = threading.Condition(self.lock)
        self.transfers = set()
        self.closed = False
        self.cancel_event = threading.Event()
        self.closing = False
        self.busy = False
        self.job_kind = ""
        self.current_id = None
        self.job_ids: list[str] = []
        self.job_finished = 0
        self.job_message = "Añade tus vídeos para comenzar."
        self.process: subprocess.Popen | None = None
        self.worker: threading.Thread | None = None
        self.ffmpeg = find_tool("ffmpeg")
        self.ffprobe = find_tool("ffprobe")
        self.tools_error = ""
        if not self.ffmpeg or not self.ffprobe:
            self.tools_error = "Falta FFmpeg o ffprobe. Puedes colocarlos en la carpeta bin de esta aplicación."
        else:
            try:
                filters = subprocess.run([self.ffmpeg, "-hide_banner", "-filters"], capture_output=True,
                                         text=True, timeout=15, **hidden_process_options()).stdout
                encoders = subprocess.run([self.ffmpeg, "-hide_banner", "-encoders"], capture_output=True,
                                          text=True, timeout=15, **hidden_process_options()).stdout
                if " delogo " not in filters or " libx264 " not in encoders:
                    self.tools_error = "FFmpeg necesita incluir delogo y libx264."
            except (OSError, subprocess.TimeoutExpired) as exc:
                self.tools_error = f"No se pudo iniciar FFmpeg: {exc}"

    def item(self, identifier: str) -> Item:
        try:
            return self.items[identifier]
        except KeyError as exc:
            raise AppError("Ese vídeo ya no está en la lista.") from exc

    def detect(self, item: Item) -> str:
        if item.info is None:
            return "Por revisar"
        try:
            return PROFILE_NAMES[core.select_profile(item.info, item.settings["perfil"])]
        except core.ProcessingError:
            return "Selecciona formato"

    def snapshot(self) -> dict:
        with self.lock:
            items = []
            for item in self.items.values():
                info = item.info
                items.append({"id": item.id, "name": item.name, "size": item.size,
                    "width": info.width if info else None, "height": info.height if info else None,
                    "fps": float(info.fps) if info else None, "duration": info.duration if info else None,
                    "frames": info.frames if info else None,
                    "format": self.detect(item), "settings": dict(item.settings), "state": item.state,
                    "progress": round(item.progress, 1), "message": item.message, "error": item.error,
                    "result": item.output.name if item.output and item.output.is_file() else None,
                    "preview": f"/media/{item.id}/preview?v={item.preview_version}" if item.preview and item.preview.is_file() else None,
                    "preview_at": item.preview_at, "preview_stale": item.preview_settings != item.settings,
                    "tail": f"/media/{item.id}/tail?v={item.tail_version}" if item.tail and item.tail.is_file() else None,
                    "tail_start": item.tail_start, "tail_start_frame": item.tail_start_frame,
                    "tail_total_frames": item.tail_total_frames, "tail_window": item.tail_window,
                    "tail_precise": item.tail_precise, "tail_error": item.tail_error})
            fraction = 0
            if self.job_ids:
                fraction = self.job_finished / len(self.job_ids)
                if self.busy and self.current_id in self.items and self.job_kind == "batch":
                    fraction += self.items[self.current_id].progress / 100 / len(self.job_ids)
            return {"items": items, "busy": self.busy, "job_kind": self.job_kind,
                "current_id": self.current_id, "job_total": len(self.job_ids), "job_finished": self.job_finished,
                "job_progress": min(100, round(fraction * 100, 1)), "message": self.job_message,
                "output_dir": str(self.output_dir), "tools_error": self.tools_error, "closing": self.closing,
                "temporary_results": True}

    @contextmanager
    def transfer(self, connection):
        with self.transfer_condition:
            if self.closing:
                raise AppError("La aplicación se está cerrando; no se pueden iniciar más descargas.")
            self.transfers.add(connection)
        try:
            yield
        finally:
            with self.transfer_condition:
                self.transfers.discard(connection)
                self.transfer_condition.notify_all()

    def accept_upload(self, name: str, size: int, stream) -> Item:
        if self.closing:
            raise AppError("La aplicación se está cerrando.")
        if self.tools_error:
            raise AppError(self.tools_error)
        name = Path(name.replace("\\", "/")).name
        if not name or len(name) > 240 or Path(name).suffix.lower() not in (".mp4", ".mov", ".mkv", ".webm"):
            raise AppError("Elige un vídeo MP4, MOV, MKV o WebM.")
        if size <= 0:
            raise AppError("El archivo está vacío.")
        if shutil.disk_usage(self.work_dir).free < size + 64 * 1024 * 1024:
            raise AppError("No hay espacio suficiente para añadir este vídeo.")
        identifier = uuid.uuid4().hex
        source = self.work_dir / "inputs" / (identifier + Path(name).suffix.lower())
        try:
            remaining = size
            with source.open("xb") as destination:
                while remaining:
                    part = stream.read(min(1024 * 1024, remaining))
                    if not part:
                        raise AppError("La copia del vídeo se interrumpió; vuelve a añadirlo.")
                    destination.write(part)
                    remaining -= len(part)
            item = Item(identifier, name, size, source)
            try:
                item.info = core.probe(source, self.ffprobe)
                self.detect(item)
            except (core.ProcessingError, OSError, ValueError) as exc:
                item.state, item.error, item.message = "error", str(exc), "No se pudo leer el vídeo"
            with self.lock:
                self.items[item.id] = item
            return item
        except BaseException:
            source.unlink(missing_ok=True)
            raise

    def update(self, identifier: str, settings: dict) -> None:
        settings = validated_settings(settings)
        with self.lock:
            if self.busy or self.closing:
                raise AppError("Espera a que termine la tarea antes de cambiar los ajustes.")
            item = self.item(identifier)
            validate_item_settings(item, settings)
            if settings != item.settings:
                item.settings = settings
                item.state, item.progress, item.error = "ready", 0, ""
                item.message = "Ajustes guardados"

    def remove(self, identifiers: list[str]) -> None:
        with self.lock:
            if self.busy or self.closing:
                raise AppError("Detén la tarea antes de quitar vídeos.")
            for identifier in identifiers:
                item = self.items.pop(identifier, None)
                if item:
                    item.source.unlink(missing_ok=True)
                    if item.preview:
                        item.preview.unlink(missing_ok=True)
                    if item.tail:
                        item.tail.unlink(missing_ok=True)
                    if item.output:
                        item.output.unlink(missing_ok=True)

    def start_tail(self, identifier: str, seconds: float) -> None:
        if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 0 < seconds <= 60:
            raise AppError("Elige un tramo final de hasta 60 segundos.")
        with self.lock:
            if self.busy or self.closing:
                raise AppError("Espera a que termine la tarea actual.")
            if self.tools_error:
                raise AppError(self.tools_error)
            item = self.item(identifier)
            if not item.info:
                raise AppError("No se pudo leer el vídeo.")
            if item.tail and item.tail.is_file() and item.tail_window == seconds:
                return
            self.busy = True
            self.cancel_event.clear()
            self.job_kind, self.job_ids, self.job_finished = "tail", [identifier], 0
            self.current_id = identifier
            self.job_message = "Preparando los últimos segundos del original…"
            self.worker = threading.Thread(target=self.work_tail, args=(item, seconds), daemon=True)
            self.worker.start()

    def work_tail(self, item: Item, seconds: float) -> None:
        target = self.work_dir / "previews" / f"{item.id}-{uuid.uuid4().hex}.mp4"
        with self.lock:
            previous = (item.state, item.message, item.progress)
            item.state, item.message, item.tail_error = "tailing", "Preparando cierre", ""
        try:
            info = item.info
            fps = float(info.fps)
            precise = bool(info.frames and (not info.nominal_fps or abs(float(info.fps / info.nominal_fps) - 1) <= .005))
            total = info.frames or max(1, math.ceil(info.duration * fps - 1e-6))
            start_frame = max(0, total - math.ceil(seconds * fps))
            start = start_frame / fps if precise else max(0, info.duration - seconds)
            duration = total / fps - start if precise else info.duration - start
            command = [self.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning", "-y",
                       "-ss", f"{start:.9f}", "-protocol_whitelist", "file,pipe", "-noautorotate",
                       "-i", str(item.source), "-map", f"0:{info.stream_index}", "-map", "0:a:0?",
                       "-sn", "-dn", "-vf", "scale=w='min(1280,iw)':h='min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
                       "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                       "-r", str(info.fps), "-fps_mode", "cfr", "-c:a", "aac", "-b:a", "128k",
                       "-t", f"{duration:.9f}", "-movflags", "+faststart", "-stats", str(target)]
            self.execute(command, item, duration)
            if self.cancel_event.is_set():
                raise Cancelled
            with self.lock:
                old = item.tail
                item.tail, item.tail_version = target, uuid.uuid4().hex
                item.tail_start, item.tail_start_frame = start, start_frame
                item.tail_total_frames, item.tail_window, item.tail_precise = total, seconds, precise
                if old:
                    old.unlink(missing_ok=True)
                self.job_finished = 1
                self.job_message = "Cierre listo. Reproduce el original y elige dónde terminar."
        except Cancelled:
            self.job_message = "Vista del cierre detenida."
        except (AppError, core.ProcessingError, OSError, ValueError) as exc:
            with self.lock:
                item.tail_error = str(exc)
                self.job_message = "No se pudo preparar el cierre. Puedes volver a intentarlo."
        finally:
            if item.tail != target:
                target.unlink(missing_ok=True)
            with self.lock:
                item.state, item.message, item.progress = previous
                self.busy, self.current_id = False, None

    def update_many(self, identifiers: list[str], settings: dict) -> None:
        settings = validated_settings(settings)
        if not isinstance(identifiers, list) or not identifiers or any(not isinstance(i, str) for i in identifiers):
            raise AppError("Selecciona al menos un vídeo.")
        with self.lock:
            if self.busy or self.closing:
                raise AppError("Espera a que termine la tarea antes de cambiar los ajustes.")
            targets = [self.item(identifier) for identifier in identifiers]
            for item in targets:
                try:
                    validate_item_settings(item, settings)
                except (core.ProcessingError, AppError) as exc:
                    raise AppError(f"{item.name}: {exc}") from exc
            for item in targets:
                self.update(item.id, settings)

    def cli(self, item: Item) -> list[str]:
        options = item.settings
        # pythonw en Windows se sustituye por python para recoger el progreso.
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe" and python.with_name("python.exe").exists():
            python = python.with_name("python.exe")
        command = [str(python), "-u", str(ROOT / "notebooklm_ffmpeg.py"), str(item.source),
                   "--ffmpeg", self.ffmpeg, "--ffprobe", self.ffprobe,
                   "--perfil", options["perfil"], "--modo", options["modo"]]
        if not options["recortar"]:
            command += ["--sin-recorte"]
        elif options["recorte_modo"] == "fotogramas":
            command += ["--recortar-fotogramas", str(options["recorte_fotogramas"])]
        elif options["recorte_modo"] == "segundos":
            command += (["--recortar-segundos", str(options["recorte_segundos"])]
                        if options["recorte_segundos"] else ["--sin-recorte"])
        profile = core.select_profile(item.info, options["perfil"])
        if options["inteligente"] and profile in ("explainer", "cinematic"):
            command += ["--deteccion-inteligente"]
        if options["rtl"]:
            command += ["--rtl"]
        if options["rect"].strip():
            command += ["--rect", options["rect"].strip()]
        return command

    def execute(self, command: list[str], item: Item, duration: float) -> None:
        if self.cancel_event.is_set():
            raise Cancelled
        kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        environment = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace", env=environment, **kwargs)
        tail = deque(maxlen=15)
        with self.lock:
            self.process = process
            if self.cancel_event.is_set():
                self.stop_process()
        try:
            assert process.stdout is not None
            for line in process.stdout:
                tail.append(line.strip())
                timestamp = re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", line)
                planned = re.search(r"Duración de salida prevista: ([\d.]+)", line)
                with self.lock:
                    if planned:
                        duration = float(planned.group(1))
                    if timestamp and duration > 0:
                        elapsed = int(timestamp[1]) * 3600 + int(timestamp[2]) * 60 + float(timestamp[3])
                        item.progress = max(item.progress, min(98, elapsed / duration * 100))
                        item.message = "Procesando vídeo"
                    elif "Explorando" in line or "Contando fotogramas" in line:
                        item.message = "Analizando vídeo"
            code = process.wait()
            if self.cancel_event.is_set():
                raise Cancelled
            if code:
                readable = next((line.split(": ", 1)[-1] for line in reversed(tail) if line.startswith("Error con ")), None)
                raise AppError(readable or "\n".join(tail)[-1800:] or "No se pudo completar el vídeo.")
        finally:
            if process.poll() is None:
                self.stop_process()
                process.wait(timeout=10)
            if process.stdout:
                process.stdout.close()
            with self.lock:
                if self.process is process:
                    self.process = None

    def stop_process(self) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            return
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **hidden_process_options())
            else:
                os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass

    def start(self, identifiers: list[str], preview_at: float | None = None) -> None:
        if not isinstance(identifiers, list) or not identifiers or any(not isinstance(i, str) for i in identifiers):
            raise AppError("Selecciona al menos un vídeo.")
        identifiers = list(dict.fromkeys(identifiers))
        with self.lock:
            if self.busy or self.closing:
                raise AppError("Ya hay una tarea en curso.")
            if self.tools_error:
                raise AppError(self.tools_error)
            for identifier in identifiers:
                item = self.item(identifier)
                if item.info is None:
                    raise AppError(f"No se pudo leer {item.name}. Quítalo de la selección.")
            if preview_at is not None:
                if len(identifiers) != 1 or not math.isfinite(preview_at) or preview_at < 0:
                    raise AppError("Elige un vídeo y un segundo de previsualización válido.")
                if preview_at >= self.item(identifiers[0]).info.duration:
                    raise AppError("Ese instante queda fuera del vídeo.")
            self.busy = True
            self.cancel_event.clear()
            self.job_kind = "preview" if preview_at is not None else "batch"
            self.job_ids, self.job_finished = identifiers, 0
            self.job_message = "Generando previsualización…" if preview_at is not None else "Procesando la lista…"
            for identifier in identifiers:
                item = self.item(identifier)
                item.state = "queued"
                item.progress, item.error = 0, ""
                item.message = "En espera"
            self.worker = threading.Thread(target=self.work, args=(identifiers, preview_at), daemon=True)
            self.worker.start()

    def available_output(self, item: Item) -> Path:
        stem = Path(item.name).stem
        number = 1
        while True:
            name = f"{stem}_limpio{'' if number == 1 else '_' + str(number)}.mp4"
            candidate = self.output_dir / name
            if not candidate.exists():
                return candidate
            number += 1

    def work(self, identifiers: list[str], preview_at: float | None) -> None:
        errors = 0
        try:
            for identifier in identifiers:
                if self.cancel_event.is_set():
                    break
                with self.lock:
                    item = self.item(identifier)
                    self.current_id = identifier
                    previous_state = "done" if item.output else "ready"
                    item.state = "previewing" if preview_at is not None else "processing"
                    item.message = "Preparando previsualización" if preview_at is not None else "Preparando vídeo"
                    item.progress = 1
                staging = None
                try:
                    command = self.cli(item)
                    if preview_at is not None:
                        target = self.work_dir / "previews" / f"{identifier}-{uuid.uuid4().hex}.png"
                        command += ["--previsualizar", str(target), "--segundo", str(preview_at)]
                    else:
                        self.output_dir.mkdir(parents=True, exist_ok=True)
                        staging = Path(tempfile.mkdtemp(prefix=".trabajo-", dir=self.output_dir))
                        target = staging / "resultado.mp4"
                        command += ["-o", str(target)]
                    self.execute(command, item, item.info.duration)
                    if self.cancel_event.is_set():
                        raise Cancelled
                    with self.lock:
                        if preview_at is not None:
                            if item.preview:
                                item.preview.unlink(missing_ok=True)
                            item.preview = target
                            item.preview_version = uuid.uuid4().hex
                            item.preview_at = preview_at
                            item.preview_settings = dict(item.settings)
                            item.state, item.message = previous_state, "Previsualización lista"
                        else:
                            output = self.available_output(item)
                            core.publish(target, output, False)
                            previous_output = item.output
                            item.output = output
                            if previous_output and previous_output != output:
                                previous_output.unlink(missing_ok=True)
                            item.state, item.message = "done", "Listo para descargar; temporal hasta cerrar"
                        item.progress = 100
                        self.job_finished += 1
                except Cancelled:
                    with self.lock:
                        item.state, item.message, item.progress = "cancelled", "Detenido; puedes volver a intentarlo", 0
                    break
                except (AppError, core.ProcessingError, OSError, ValueError) as exc:
                    errors += 1
                    with self.lock:
                        item.state, item.message, item.error = "error", "Revisa este vídeo", str(exc)
                        self.job_finished += 1
                finally:
                    if staging:
                        shutil.rmtree(staging, ignore_errors=True)
            with self.lock:
                self.job_message = ("Tarea detenida. Descarga los resultados terminados antes de cerrar." if self.cancel_event.is_set()
                    else "Previsualización lista." if preview_at is not None and not errors
                    else f"Lista terminada: {len(identifiers) - errors} correctos y {errors} por revisar." if preview_at is None
                    else "No se pudo generar la previsualización. Revisa los ajustes.")
        finally:
            with self.lock:
                for identifier in identifiers:
                    item = self.items.get(identifier)
                    if item and item.state == "queued":
                        item.state, item.message = "ready", "Pendiente"
                self.busy, self.current_id = False, None

    def cancel(self) -> None:
        with self.lock:
            self.cancel_event.set()
            self.job_message = "Deteniendo la tarea…"
            self.stop_process()

    def close(self) -> None:
        if self.closed:
            return
        self.closing = True
        self.cancel()
        if self.worker:
            self.worker.join(timeout=15)
            if self.worker.is_alive():
                raise AppError("La tarea todavía se está deteniendo. Vuelve a intentar cerrar en unos segundos.")
        # Al confirmar el cierre se cancelan las transferencias que sigan abiertas.
        with self.transfer_condition:
            for connection in tuple(self.transfers):
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            deadline = time.monotonic() + 5
            while self.transfers and time.monotonic() < deadline:
                self.transfer_condition.wait(timeout=.1)
            if self.transfers:
                raise AppError("Hay una descarga que todavía se está cerrando. Vuelve a intentar cerrar.")
        try:
            self.session.close()
        except OSError as exc:
            raise AppError("No se pudo terminar de limpiar la sesión. Vuelve a intentar cerrar.") from exc
        with self.lock:
            self.items.clear()
            self.closed = True


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, application: Application):
        self.application = application
        self.secret = secrets.token_urlsafe(32)
        super().__init__(address, Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.cookie_name = f"notebooklm_{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    server_version = "NotebookLM-Local/2.4"

    def log_message(self, *_):
        pass

    @property
    def app(self) -> Application:
        return self.server.application

    def headers_common(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

    def send_json(self, value, status=200, cookie=False):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.headers_common()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if cookie:
            self.send_header("Set-Cookie", f"{self.server.cookie_name}={self.server.secret}; HttpOnly; SameSite=Strict; Path=/")
        self.end_headers()
        self.wfile.write(data)

    def allowed_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def authorized(self):
        if not self.allowed_host():
            return False
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            entry = cookie.get(self.server.cookie_name)
            return entry is not None and secrets.compare_digest(entry.value, self.server.secret)
        except (ValueError, TypeError):
            return False

    def json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length < 0 or length > 65536:
            raise AppError("La solicitud es demasiado grande.")
        value = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(value, dict):
            raise AppError("La solicitud no es válida.")
        return value

    def send_file(self, path: Path, media_type: str, download_name: str | None = None):
        if not path.is_file():
            raise AppError("El archivo no está disponible.")
        size = path.stat().st_size
        start, end = 0, size - 1
        partial = False
        requested_range = self.headers.get("Range", "") if media_type == "video/mp4" else ""
        if requested_range:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested_range)
            if match and (match[1] or match[2]):
                start = int(match[1]) if match[1] else max(0, size - int(match[2]))
                end = min(size - 1, int(match[2])) if match[1] and match[2] else size - 1
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                partial = True
        self.send_response(206 if partial else 200)
        self.headers_common()
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(end - start + 1))
        if media_type == "video/mp4":
            self.send_header("Accept-Ranges", "bytes")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if download_name:
            self.send_header("Content-Disposition", "attachment; filename=\"resultado\"; filename*=UTF-8''" + quote(download_name))
        self.end_headers()
        with path.open("rb") as source:
            source.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_GET(self):
        try:
            if not self.allowed_host():
                self.send_json({"error": "Dirección local no válida."}, 403)
                return
            path = urlparse(self.path).path
            static = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "application/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if path in static:
                name, content_type = static[path]
                self.send_file(ROOT / "interfaz" / name, content_type)
                return
            if not self.authorized():
                self.send_json({"error": "Abre la aplicación desde su acceso de inicio."}, 401)
                return
            if path == "/api/state":
                self.send_json(self.app.snapshot())
            elif path == "/download/all":
                with self.app.transfer(self.connection):
                    with self.app.lock:
                        results = [item.output for item in self.app.items.values() if item.output and item.output.is_file()]
                    if not results:
                        raise AppError("Todavía no hay resultados para descargar.")
                    fd, name = tempfile.mkstemp(suffix=".zip", dir=self.app.work_dir)
                    os.close(fd)
                    archive = Path(name)
                    try:
                        with zipfile.ZipFile(archive, "w", zipfile.ZIP_STORED, allowZip64=True) as bundle:
                            for result in results:
                                bundle.write(result, result.name)
                        self.send_file(archive, "application/zip", "videos_limpios.zip")
                    finally:
                        archive.unlink(missing_ok=True)
            else:
                match = re.fullmatch(r"/(media|download)/([a-f0-9]{32})/(preview|result|original|tail)", path)
                if not match:
                    self.send_json({"error": "Ruta no disponible."}, 404)
                    return
                with self.app.lock:
                    item = self.app.item(match[2])
                    file = item.preview if match[3] == "preview" else item.source if match[3] == "original" else item.tail if match[3] == "tail" else item.output
                    filename = None if match[1] == "media" else item.output.name if item.output else None
                if not file:
                    raise AppError("El resultado todavía no está listo.")
                with self.app.transfer(self.connection):
                    self.send_file(file, "image/png" if match[3] == "preview" else "video/mp4", filename)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (AppError, OSError, ValueError) as exc:
            self.send_json({"error": str(exc)}, 400)

    def do_POST(self):
        try:
            origin = self.headers.get("Origin")
            if not self.allowed_host() or (origin and origin != self.server.origin):
                self.send_json({"error": "La solicitud debe venir de esta aplicación local."}, 403)
                return
            path = urlparse(self.path).path
            if path == "/api/session":
                value = self.json_body().get("token", "")
                if not isinstance(value, str) or not secrets.compare_digest(value, self.server.secret):
                    self.send_json({"error": "Vuelve a abrir la aplicación desde el acceso de inicio."}, 401)
                    return
                self.send_json({"ok": True}, cookie=True)
                return
            if not self.authorized():
                self.send_json({"error": "Sesión local no autorizada."}, 401)
                return
            if path == "/api/upload":
                if "Content-Length" not in self.headers:
                    raise AppError("No se pudo determinar el tamaño del archivo.")
                name = parse_qs(urlparse(self.path).query).get("name", [""])[0]
                with self.app.transfer(self.connection):
                    item = self.app.accept_upload(name, int(self.headers["Content-Length"]), self.rfile)
                self.send_json({"id": item.id}, 201)
                return
            body = self.json_body()
            if path == "/api/run":
                self.app.start(body.get("ids"))
            elif path == "/api/preview":
                self.app.start([body.get("id")], float(body.get("second", 1)))
            elif path == "/api/tail":
                self.app.start_tail(body.get("id"), body.get("seconds", 10))
            elif path == "/api/settings":
                self.app.update(body.get("id"), body.get("settings"))
            elif path == "/api/settings-many":
                self.app.update_many(body.get("ids"), body.get("settings"))
            elif path == "/api/remove":
                identifiers = body.get("ids")
                if not isinstance(identifiers, list) or any(not isinstance(i, str) for i in identifiers):
                    raise AppError("Selecciona los vídeos que quieres quitar.")
                self.app.remove(identifiers)
            elif path == "/api/cancel":
                self.app.cancel()
            elif path == "/api/shutdown":
                self.app.close()
                self.send_json({"ok": True, "session_deleted": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            else:
                self.send_json({"error": "Acción no disponible."}, 404)
                return
            self.send_json({"ok": True})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (AppError, core.ProcessingError, ValueError, TypeError, OSError) as exc:
            self.close_connection = True
            self.send_json({"error": str(exc)}, 400)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sin-abrir", action="store_true", help="No abrir el navegador automáticamente.")
    parser.add_argument("--puerto", type=int, default=0)
    parser.add_argument("--sesiones", "--resultados", dest="sesiones", type=Path,
                        help="Carpeta base de sesiones temporales; cada sesión se elimina al cerrar.")
    args = parser.parse_args(argv)
    application = Application(args.sesiones)
    server = LocalServer(("127.0.0.1", args.puerto), application)
    address = f"{server.origin}/#{server.secret}"
    print("NotebookLM · Interfaz local\n" + address, flush=True)
    if not args.sin_abrir:
        threading.Timer(0.4, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            application.close()
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
