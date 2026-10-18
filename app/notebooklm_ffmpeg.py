#!/usr/bin/env python3
"""Limpieza local de vídeos NotebookLM con Python 3.10+, FFmpeg y ffprobe."""

from __future__ import annotations

import argparse
import errno
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from fractions import Fraction

VERSION = "1.0.0"


class ProcessingError(Exception):
    """Error legible para quien utiliza la herramienta."""


def subprocess_options() -> dict:
    """Evita ventanas de consola de las herramientas al utilizar la interfaz."""
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def options(self) -> str:
        return f"x={self.x}:y={self.y}:w={self.w}:h={self.h}"

    def validate(self, width: int, height: int) -> Rect:
        # delogo necesita píxeles vecinos fuera de los cuatro lados.
        if min(self.x, self.y) < 1 or min(self.w, self.h) < 2:
            raise ProcessingError("La región necesita x/y >= 1 y ancho/alto >= 2.")
        if self.x + self.w >= width or self.y + self.h >= height:
            raise ProcessingError("La región sale del vídeo o toca su borde; deja al menos un píxel de margen.")
        return self


@dataclass(frozen=True)
class VideoInfo:
    stream_index: int
    width: int
    height: int
    fps: Fraction
    nominal_fps: Fraction
    frames: int | None
    duration: float
    has_audio: bool


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    region: Rect


@dataclass
class Plan:
    profile: str
    region: Rect
    remove_frames: int
    keep_frames: int | None
    duration: float
    segments: list[Segment] | None = None


def positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Introduce un número.") from exc
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("El número debe ser finito y mayor que cero.")
    return value


def nonnegative_float(text: str) -> float:
    if text in ("0", "0.0"):
        return 0.0
    return positive_float(text)


def nonnegative_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Introduce un entero.") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("El entero debe ser cero o positivo.")
    return value


def parse_rect(text: str) -> Rect:
    try:
        parts = [int(value) for value in text.split(":")]
        if len(parts) != 4:
            raise ValueError
        return Rect(*parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Usa x:y:ancho:alto, por ejemplo 1141:686:134:24.") from exc


def run_json(command: list[str]) -> dict:
    result = subprocess.run(command, capture_output=True, text=True, errors="replace", **subprocess_options())
    if result.returncode:
        raise ProcessingError(result.stderr.strip()[-2500:] or "ffprobe no pudo leer el archivo.")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProcessingError("ffprobe devolvió una respuesta que no es JSON válido.") from exc


def rate(value: str | None) -> Fraction:
    try:
        return Fraction(value or "0")
    except (ValueError, ZeroDivisionError):
        return Fraction(0)


def positive_number(value: object) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError):
        return None


def probe(path: Path, ffprobe: str) -> VideoInfo:
    data = run_json([ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe",
                     "-show_streams", "-show_format", "-of", "json", str(path)])
    streams = data.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"
              and not stream.get("disposition", {}).get("attached_pic")]
    if not videos:
        raise ProcessingError("El archivo no contiene una pista de vídeo.")
    video = videos[0]
    rotations = [video.get("tags", {}).get("rotate", 0)]
    rotations += [item.get("rotation", 0) for item in video.get("side_data_list", [])]
    if any(abs(float(value)) % 360 > 0.01 for value in rotations):
        raise ProcessingError("El vídeo tiene rotación por metadatos. Exporta una copia con la rotación aplicada primero.")
    fps = rate(video.get("avg_frame_rate")) or rate(video.get("r_frame_rate"))
    if fps <= 0:
        raise ProcessingError("No se pudieron determinar los FPS del vídeo.")
    width, height = int(video["width"]), int(video["height"])
    if min(width, height) < 64:
        raise ProcessingError("La resolución es demasiado pequeña para los perfiles NotebookLM.")
    if width % 2 or height % 2:
        raise ProcessingError("H.264 con yuv420p requiere dimensiones pares; normaliza la resolución primero.")
    sar = video.get("sample_aspect_ratio", "1:1")
    if sar not in ("1:1", "N/A", "0:1"):
        raise ProcessingError("Los perfiles requieren píxeles cuadrados (SAR 1:1).")
    frames_value = positive_number(video.get("nb_frames"))
    frames = int(frames_value) if frames_value else None
    duration = positive_number(video.get("duration")) or positive_number(data.get("format", {}).get("duration"))
    if duration is None and frames:
        duration = frames / float(fps)
    if duration is None:
        raise ProcessingError("No se pudo determinar la duración del vídeo.")
    return VideoInfo(int(video["index"]), width, height, fps, rate(video.get("r_frame_rate")), frames,
                     duration, any(s.get("codec_type") == "audio" for s in streams))


def count_frames(path: Path, ffprobe: str, info: VideoInfo) -> int:
    if info.frames:
        return info.frames
    print("Contando fotogramas; este contenedor no incluye el total...", flush=True)
    data = run_json([ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe",
                     "-select_streams", str(info.stream_index), "-count_frames", "-show_entries",
                     "stream=nb_read_frames", "-of", "json", str(path)])
    value = positive_number(data.get("streams", [{}])[0].get("nb_read_frames"))
    if not value:
        raise ProcessingError("No se pudieron contar los fotogramas.")
    return int(value)


def rounded(value: float) -> int:
    """Redondeo de coordenadas positivas equivalente a Math.round de JavaScript."""
    return math.floor(value + 0.5)


def scaled(rect: Rect, width: int, height: int, base_w: int, base_h: int) -> Rect:
    return Rect(rounded(rect.x * width / base_w), rounded(rect.y * height / base_h),
                max(2, rounded(rect.w * width / base_w)), max(2, rounded(rect.h * height / base_h)))


def select_profile(info: VideoInfo, requested: str) -> str:
    if requested != "auto":
        return requested
    aspect = info.width / info.height
    if info.height > info.width and abs(aspect - 406 / 720) < 0.04:
        return "short"
    if info.width > info.height and abs(aspect - 16 / 9) < 0.04:
        if abs(float(info.fps) - 24) <= 0.1:
            return "explainer"
        if abs(float(info.fps) - 30) <= 0.1:
            return "cinematic"
    raise ProcessingError("Formato no reconocido. Indica --perfil explainer/cinematic/short o usa --perfil manual --rect x:y:w:h.")


def default_region(info: VideoInfo, profile: str, rtl: bool) -> Rect:
    if profile in ("short", "legacy"):
        return scaled(Rect(291, 688, 109, 27), info.width, info.height, 406, 720)
    if rtl and profile == "explainer":
        return scaled(Rect(43, 656, 133, 40), info.width, info.height, 1280, 720)
    x = rounded(1141 * info.width / 1280)
    y = rounded(686 * info.height / 720)
    bottom = min(rounded(710 * info.height / 720), info.height - 2)
    return Rect(x, y, info.width - x - 5, bottom - y)


def make_plan(path: Path, info: VideoInfo, args: argparse.Namespace) -> Plan:
    profile = select_profile(info, args.perfil)
    if profile == "manual" and args.rect is None:
        raise ProcessingError("--perfil manual requiere --rect x:y:ancho:alto.")
    if args.deteccion_inteligente and profile not in ("explainer", "cinematic"):
        raise ProcessingError("La detección inteligente solo corresponde a vídeos horizontales.")
    if args.deteccion_inteligente and (args.rect is not None or args.logo is not None):
        raise ProcessingError("Usa la detección inteligente por separado de --rect y --logo.")
    region = (args.rect or default_region(info, profile, args.rtl)).validate(info.width, info.height)
    remove = 0 if args.sin_recorte or profile == "manual" else (72 if profile == "explainer" else 60 if profile == "legacy" else 90)
    if args.recortar_fotogramas is not None:
        remove = args.recortar_fotogramas
    keep, duration = None, info.duration
    if args.recortar_segundos is not None:
        duration -= args.recortar_segundos
    elif remove and not args.previsualizar:
        if info.nominal_fps and abs(float(info.fps / info.nominal_fps) - 1) > 0.005:
            raise ProcessingError("FPS variables detectados: utiliza --recortar-segundos o --sin-recorte para evitar un corte temporal impreciso.")
        keep = count_frames(path, args.ffprobe, info) - remove
        duration = keep / float(info.fps)
    if duration <= 0 or (keep is not None and keep <= 0):
        raise ProcessingError("El vídeo es más corto que el cierre solicitado. Usa --sin-recorte o reduce el corte.")
    if args.duracion_prueba is not None:
        duration = min(duration, args.duracion_prueba)
    return Plan(profile, region, remove, keep, duration)


def read_exact(stream, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        part = stream.read(size - len(data))
        if not part:
            break
        data.extend(part)
    return bytes(data)


def rgb_variance(frame: bytes, width: int, region: Rect) -> float:
    total, squares, count = 0.0, 0.0, region.w * region.h
    for y in range(region.y, region.y + region.h):
        start = (y * width + region.x) * 3
        for index in range(start, start + region.w * 3, 3):
            brightness = (frame[index] + frame[index + 1] + frame[index + 2]) / 3
            total += brightness
            squares += brightness * brightness
    return max(0.0, squares / count - (total / count) ** 2)


def smart_scan(path: Path, info: VideoInfo, args: argparse.Namespace) -> list[Segment]:
    bottom = Rect(43, 656, 133, 30) if args.rtl else Rect(1104, 656, 133, 30)
    regions = [scaled(bottom, info.width, info.height, 1280, 720),
               scaled(Rect(539, 47, 186, 25), info.width, info.height, 1280, 720)]
    for rect in regions:
        rect.validate(info.width, info.height)
    command = [args.ffmpeg, "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
               "-noautorotate", "-i", str(path), "-map", f"0:{info.stream_index}", "-an", "-sn", "-dn",
               "-vf", "fps=fps=1:start_time=0", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"]
    print("Explorando una imagen por segundo (heurística de contraste)...", flush=True)
    winners: list[int | None] = []
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, **subprocess_options())
        try:
            assert process.stdout is not None
            while True:
                frame = read_exact(process.stdout, info.width * info.height * 3)
                if not frame:
                    break
                if len(frame) != info.width * info.height * 3:
                    raise ProcessingError("Fotograma incompleto durante la exploración.")
                scores = [rgb_variance(frame, info.width, region) for region in regions]
                best = max(range(len(scores)), key=scores.__getitem__)
                winners.append(best if scores[best] > args.umbral else None)
            code = process.wait()
            if code:
                errors.seek(0)
                raise ProcessingError(errors.read().decode(errors="replace")[-2500:])
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdout:
                process.stdout.close()
    # Agrupa muestras y amplía las transiciones como el método inspeccionado.
    segments: list[Segment] = []
    active, start, center_completed = None, 0, False
    for second in range(len(winners) + 1):
        winner = winners[second] if second < len(winners) else None
        if winner == 1 and center_completed:
            winner = active
        if winner == active:
            continue
        if active is not None:
            end = second + (1 if second == len(winners) else 0)
            segments.append(Segment(float(start), min(info.duration, float(end)), regions[active]))
            center_completed |= active == 1
        active = winner
        start = max(0, second - 1) if segments else second
    return segments


def logo_dimensions(path: Path, ffprobe: str) -> tuple[int, int]:
    data = run_json([ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe", "-select_streams", "v:0",
                     "-show_entries", "stream=width,height", "-of", "json", str(path)])
    streams = data.get("streams", [])
    if not streams:
        raise ProcessingError("No se pudo leer la imagen del logo.")
    return int(streams[0]["width"]), int(streams[0]["height"])


def cleaning_filters(plan: Plan, instant: float | None = None) -> list[str]:
    if plan.segments is None:
        return [f"delogo={plan.region.options()}"]
    filters = []
    for segment in plan.segments:
        if instant is not None:
            if segment.start <= instant <= segment.end:
                filters.append(f"delogo={segment.region.options()}")
        else:
            filters.append(f"delogo={segment.region.options()}:enable='between(t,{segment.start:.6f},{segment.end:.6f})'")
    return filters or ["null"]


def make_command(path: Path, target: Path, info: VideoInfo, plan: Plan, args: argparse.Namespace) -> list[str]:
    preview = args.previsualizar is not None
    command = [args.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning", "-y",
               "-protocol_whitelist", "file,pipe", "-noautorotate"]
    if preview:
        if args.segundo >= info.duration:
            raise ProcessingError("El segundo de previsualización queda fuera del vídeo.")
        command += ["-ss", f"{args.segundo:.6f}"]
    command += ["-i", str(path)]
    if args.logo is not None:
        command += ["-protocol_whitelist", "file,pipe", "-i", str(args.logo)]
    filters = cleaning_filters(plan, args.segundo if preview else None)
    if not preview and plan.keep_frames is not None:
        filters += [f"trim=end_frame={plan.keep_frames}", "setpts=PTS-STARTPTS"]
    video_input = f"[0:{info.stream_index}]"
    graph = [f"{video_input}split=2[reference][source]"] if preview else []
    graph.append(f"{'[source]' if preview else video_input}{','.join(filters)}[base]")
    clean = "base"
    if args.logo is not None:
        lw, lh = logo_dimensions(args.logo, args.ffprobe)
        ratio = min(plan.region.w / lw, plan.region.h / lh)
        w, h = max(1, int(lw * ratio)), max(1, int(lh * ratio))
        x, y = plan.region.x + (plan.region.w - w) // 2, plan.region.y + (plan.region.h - h) // 2
        graph += [f"[1:v:0]format=rgba,scale={w}:{h}[logo]",
                  f"[base][logo]overlay=x={x}:y={y}:eof_action=repeat:format=auto[clean]"]
        clean = "clean"
    if preview:
        boxes = [plan.region] if plan.segments is None else [s.region for s in plan.segments if s.start <= args.segundo <= s.end]
        markings = [f"drawbox={rect.options()}:color=red:thickness=2" for rect in boxes] or ["null"]
        graph += [f"[reference]{','.join(markings)}[marked]", f"[marked][{clean}]hstack=inputs=2[preview]"]
        command += ["-filter_complex", ";".join(graph), "-map", "[preview]", "-frames:v", "1", "-update", "1", str(target)]
        return command
    profiles = {"calidad": (18, "medium", None), "equilibrado": (23, "veryfast", "30"),
                "rapido": (28, "ultrafast", "15")}
    crf, preset, fps = profiles[args.modo]
    command += ["-filter_complex", ";".join(graph), "-map", f"[{clean}]"]
    if info.has_audio and args.audio != "sin":
        command += ["-map", "0:a:0?"]
        if args.audio == "copiar":
            command += ["-c:a", "copy"]
        else:
            command += ["-c:a", "aac", "-b:a", "192k", "-af", f"atrim=duration={plan.duration:.9f},asetpts=PTS-STARTPTS"]
    else:
        command += ["-an"]
    command += ["-c:v", "libx264", "-crf", str(args.crf if args.crf is not None else crf),
                "-preset", args.preset or preset, "-tune", "stillimage", "-pix_fmt", "yuv420p"]
    # El filtro trim puede dejar sin duración al último paquete en algunas
    # versiones de FFmpeg. Declarar la cadencia CFR mantiene la duración N/FPS.
    command += ["-r", fps or str(info.fps), "-fps_mode", "cfr"]
    command += ["-t", f"{plan.duration:.9f}", "-movflags", "+faststart", "-stats", str(target)]
    return command


def publish(temporary: Path, output: Path, overwrite: bool) -> None:
    if overwrite:
        os.replace(temporary, output)
        return
    try:
        os.link(temporary, output)
    except OSError as exc:
        if exc.errno not in (errno.EPERM, errno.ENOTSUP, errno.EXDEV):
            raise
        # Sistemas de archivos sin enlaces duros: creación exclusiva.
        with output.open("xb") as destination:
            try:
                with temporary.open("rb") as source:
                    shutil.copyfileobj(source, destination)
            except BaseException:
                output.unlink(missing_ok=True)
                raise


def process_file(path: Path, output: Path, args: argparse.Namespace) -> None:
    if not path.is_file():
        raise ProcessingError(f"No existe el archivo: {path}")
    if output == path or (output.exists() and os.path.samefile(path, output)):
        raise ProcessingError("La salida debe ser distinta del archivo original.")
    if output.exists() and not args.sobrescribir and not args.simular:
        raise ProcessingError(f"La salida ya existe: {output}. Usa otra ruta o --sobrescribir.")
    info = probe(path, args.ffprobe)
    plan = make_plan(path, info, args)
    if args.deteccion_inteligente:
        plan.segments = smart_scan(path, info, args)
        if not plan.segments:
            # Mantiene el perfil fijo cuando no hay candidatos, como la herramienta analizada.
            plan.segments = None
            print("No hubo candidatos claros: se utilizará la región fija del perfil.", flush=True)
    print(f"\nEntrada: {path}\nPerfil: {plan.profile} | {info.width}x{info.height} | {float(info.fps):.6g} fps"
          f"\nRegión: {plan.region.x}:{plan.region.y}:{plan.region.w}:{plan.region.h}", flush=True)
    if plan.segments:
        print(f"Intervalos de limpieza: {len(plan.segments)}", flush=True)
    if not args.previsualizar:
        print(f"Duración de salida prevista: {plan.duration:.3f} s | modo: {args.modo}", flush=True)
    if args.simular:
        command = make_command(path, output, info, plan, args)
        # El procesamiento real usa un archivo temporal único y protege la salida final.
        command[command.index("-y")] = "-y" if args.sobrescribir else "-n"
        print("Comando equivalente:\n" + (subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)))
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".notebooklm-", suffix=output.suffix, dir=output.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        command = make_command(path, temporary, info, plan, args)
        if subprocess.run(command, **subprocess_options()).returncode:
            raise ProcessingError("FFmpeg no pudo terminar. Revisa el mensaje anterior.")
        if not temporary.stat().st_size:
            raise ProcessingError("FFmpeg produjo un archivo vacío.")
        publish(temporary, output, args.sobrescribir)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Guardado: {output}", flush=True)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Ejemplos:\n  %(prog)s video.mp4\n  %(prog)s short.mp4 --previsualizar vista.png\n"
               "  %(prog)s video.mp4 --sin-recorte\n  %(prog)s video.mp4 --deteccion-inteligente\n"
               "  %(prog)s uno.mp4 dos.mp4 --carpeta-salida limpios\n")
    p.add_argument("entradas", nargs="+", type=Path, help="Uno o varios vídeos locales.")
    p.add_argument("--version", action="version", version=VERSION)
    destinations = p.add_mutually_exclusive_group()
    destinations.add_argument("-o", "--salida", type=Path, help="MP4 de salida; solo para una entrada.")
    destinations.add_argument("--carpeta-salida", type=Path, help="Carpeta para las salidas de un lote.")
    destinations.add_argument("--previsualizar", type=Path, metavar="PNG", help="Comparativa PNG: original marcado a la izquierda, limpio a la derecha.")
    p.add_argument("--segundo", type=nonnegative_float, default=1.0, help="Instante de la previsualización (1 por defecto).")
    p.add_argument("--perfil", choices=("auto", "explainer", "cinematic", "short", "legacy", "manual"), default="auto")
    p.add_argument("--rect", type=parse_rect, metavar="X:Y:ANCHO:ALTO", help="Región en píxeles del vídeo original.")
    p.add_argument("--rtl", action="store_true", help="Logo a la izquierda en Explainer y en la exploración inteligente.")
    cut = p.add_mutually_exclusive_group()
    cut.add_argument("--sin-recorte", action="store_true", help="Conservar el cierre completo.")
    cut.add_argument("--recortar-fotogramas", type=nonnegative_int, metavar="N", help="Cantidad de fotogramas a quitar al final.")
    cut.add_argument("--recortar-segundos", type=positive_float, metavar="S", help="Segundos a quitar al final.")
    p.add_argument("--modo", choices=("calidad", "equilibrado", "rapido"), default="calidad")
    p.add_argument("--crf", type=int, choices=range(0, 52), metavar="0..51", help="Compresión H.264; sustituye el CRF del modo.")
    p.add_argument("--preset", choices=("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"))
    p.add_argument("--audio", choices=("aac", "copiar", "sin"), default="aac", help="AAC permite recortar audio; copiar evita su recodificación.")
    p.add_argument("--logo", type=Path, metavar="PNG", help="Logo propio que se ajusta dentro de la región limpiada.")
    p.add_argument("--deteccion-inteligente", action="store_true", help="Exploración opcional por contraste; puede producir falsos positivos.")
    p.add_argument("--umbral", type=positive_float, default=400.0, help="Umbral de variación de brillo de la exploración (400).")
    p.add_argument("--duracion-prueba", type=positive_float, metavar="S", help="Exportar solamente los primeros S segundos del resultado.")
    p.add_argument("--simular", action="store_true", help="Mostrar el plan y el comando, sin generar salida.")
    p.add_argument("--sobrescribir", action="store_true", help="Permitir reemplazar una salida existente; el original se protege siempre.")
    p.add_argument("--ffmpeg", default="ffmpeg", help="Ejecutable de FFmpeg o su ruta completa.")
    p.add_argument("--ffprobe", default="ffprobe", help="Ejecutable de ffprobe o su ruta completa.")
    return p


def main(argv: list[str] | None = None) -> int:
    p = parser()
    args = p.parse_args(argv)
    if len(args.entradas) > 1 and (args.salida or args.previsualizar):
        p.error("--salida y --previsualizar requieren una sola entrada; usa --carpeta-salida para lotes.")
    for attribute in ("ffmpeg", "ffprobe"):
        executable = shutil.which(getattr(args, attribute))
        if executable is None:
            p.error(f"No se encontró {attribute}. Instala FFmpeg y agrega sus ejecutables al PATH.")
        setattr(args, attribute, executable)
    if args.previsualizar and args.previsualizar.suffix.lower() != ".png":
        p.error("La previsualización debe terminar en .png.")
    if args.salida and args.salida.suffix.lower() != ".mp4":
        p.error("La salida de vídeo debe terminar en .mp4.")
    if args.logo:
        args.logo = args.logo.expanduser().resolve()
        if not args.logo.is_file() or args.logo.suffix.lower() != ".png":
            p.error("--logo requiere un archivo PNG local existente.")
    capabilities = subprocess.run([args.ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True, **subprocess_options()).stdout
    encoders = subprocess.run([args.ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, **subprocess_options()).stdout
    if " delogo " not in capabilities or " libx264 " not in encoders:
        p.error("Esta instalación de FFmpeg necesita el filtro delogo y el codificador libx264.")
    sources = [path.expanduser().resolve() for path in args.entradas]
    outputs = []
    for source in sources:
        output = args.previsualizar or args.salida
        if output is None:
            output = (args.carpeta_salida or source.parent) / f"{source.stem}_limpio.mp4"
        outputs.append(output.expanduser().resolve())
    normalized = [os.path.normcase(str(output)) for output in outputs]
    if len(set(normalized)) != len(normalized):
        p.error("Varias entradas producirían la misma salida; separa los lotes o cambia sus nombres.")
    if any(output in sources for output in outputs):
        p.error("Una salida coincide con un archivo de entrada; elige otra carpeta o nombre.")
    if args.logo and any(output == args.logo or (output.exists() and os.path.samefile(output, args.logo)) for output in outputs):
        p.error("La salida no puede reemplazar la imagen del logo.")
    failures = 0
    for source, output in zip(sources, outputs):
        try:
            process_file(source, output, args)
        except (ProcessingError, OSError, ValueError) as exc:
            failures += 1
            print(f"Error con {source.name}: {exc}", file=sys.stderr, flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nProcesamiento interrumpido.", file=sys.stderr)
        raise SystemExit(130)
