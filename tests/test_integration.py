"""Pruebas de vídeo reales; solo usan FFmpeg, ffprobe y la biblioteca estándar."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = (Path(__file__).resolve().parents[1] / "app") / "notebooklm_ffmpeg.py"


def run(command, expected=0):
    result = subprocess.run([str(p) for p in command], capture_output=True, text=True)
    if result.returncode != expected:
        raise AssertionError(f"Código {result.returncode}, esperado {expected}\n{result.stdout}\n{result.stderr}")
    return result


def metadata(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]).stdout)


def video_stream(path):
    return next(s for s in metadata(path)["streams"] if s["codec_type"] == "video")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Se necesita FFmpeg y ffprobe")
class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="notebooklm-test-")
        cls.root = Path(cls.temp.name)
        cls.sources = {}
        cases = {
            "explainer": (1280, 720, 24, 5),
            "cinematic": (1920, 1080, 30, 4),
            "short": (406, 720, 30, 5),
            "short_hd": (720, 1280, 30, 4),
            "unknown": (1280, 720, 25, 4),
        }
        for name, (w, h, fps, duration) in cases.items():
            path = cls.root / f"{name}.mp4"
            if h > w:
                x, y = round(296 * w / 406), round(692 * h / 720)
                font = max(10, round(13 * w / 406))
            else:
                x, y = round(1147 * w / 1280), round(689 * h / 720)
                font = max(10, round(14 * w / 1280))
            source = f"color=c=0xdddddd:s={w}x{h}:r={fps}:d={duration}"
            run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", source,
                 "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
                 "-vf", f"drawtext=text='NotebookLM':x={x}:y={y}:fontsize={font}:fontcolor=black",
                 "-c:v", "libx264", "-preset", "ultrafast", "-threads", "2", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-shortest", path])
            cls.sources[name] = path
        cls.originals = {name: digest(path) for name, path in cls.sources.items()}

    @classmethod
    def tearDownClass(cls):
        try:
            for name, path in cls.sources.items():
                if digest(path) != cls.originals[name]:
                    raise AssertionError(f"El original cambió: {path}")
        finally:
            cls.temp.cleanup()

    def cli(self, source, *options, expected=0):
        return run([sys.executable, SCRIPT, source, *options], expected)

    def check_output(self, path, w, h, fps, frames):
        data = metadata(path)
        video = next(s for s in data["streams"] if s["codec_type"] == "video")
        audio = [s for s in data["streams"] if s["codec_type"] == "audio"]
        self.assertEqual((video["width"], video["height"]), (w, h))
        self.assertEqual(video["avg_frame_rate"], f"{fps}/1")
        self.assertEqual(int(video["nb_frames"]), frames)
        self.assertAlmostEqual(float(video["duration"]), frames / fps, places=3)
        self.assertEqual(len(audio), 1)
        self.assertLessEqual(abs(float(audio[0]["duration"]) - frames / fps), 0.04)

    def test_auto_profiles_trim_video_and_audio(self):
        for name, w, h, fps, frames in [("explainer",1280,720,24,48), ("cinematic",1920,1080,30,30),
                                       ("short",406,720,30,60), ("short_hd",720,1280,30,30)]:
            with self.subTest(name=name):
                output = self.root / f"{name}_output.mp4"
                self.cli(self.sources[name], "-o", output)
                self.check_output(output, w, h, fps, frames)

    def test_legacy_and_no_trim(self):
        legacy = self.root / "legacy.mp4"
        full = self.root / "full.mp4"
        self.cli(self.sources["short"], "--perfil", "legacy", "-o", legacy)
        self.check_output(legacy,406,720,30,90)
        self.cli(self.sources["explainer"], "--sin-recorte", "-o", full)
        self.check_output(full,1280,720,24,120)

    def test_explicit_cuts(self):
        for name, flag, value, frames in [("frames","--recortar-fotogramas","24",96),
                                          ("seconds","--recortar-segundos","1",96)]:
            output = self.root / f"cut_{name}.mp4"
            self.cli(self.sources["explainer"], flag, value, "-o", output)
            self.check_output(output,1280,720,24,frames)

    def test_preview_dimensions_and_region_reconstruction(self):
        preview = self.root / "preview.png"
        clean = self.root / "visual_clean.mp4"
        self.cli(self.sources["explainer"], "--previsualizar", preview, "--segundo", "0.5")
        data = video_stream(preview)
        self.assertEqual((data["width"],data["height"]),(2560,720))
        self.cli(self.sources["explainer"], "-o", clean, "--duracion-prueba", "1")
        def variance(path):
            result = subprocess.run(["ffmpeg","-v","error","-ss","0.5","-i",str(path),"-vf",
                "crop=120:18:1147:689","-frames:v","1","-pix_fmt","gray","-f","rawvideo","pipe:1"],capture_output=True,check=True)
            pixels = result.stdout
            mean = sum(pixels)/len(pixels)
            return sum((p-mean)**2 for p in pixels)/len(pixels)
        before, after = variance(self.sources["explainer"]), variance(clean)
        self.assertGreater(before,100)
        self.assertLess(after,before*0.1)

    def test_preserves_outputs_and_sources(self):
        existing = self.root / "existing.mp4"
        existing.write_bytes(b"existing output")
        before = digest(existing)
        self.cli(self.sources["explainer"], "-o", existing, expected=1)
        self.assertEqual(digest(existing),before)
        self.cli(self.sources["explainer"], "-o", self.sources["explainer"], "--sobrescribir", expected=2)
        self.cli(self.sources["explainer"], "-o", existing, "--sobrescribir", "--duracion-prueba", "0.5")
        self.assertGreater(existing.stat().st_size,20)

    def test_unknown_profile_bad_rectangle_and_short_input(self):
        self.cli(self.sources["unknown"], "--simular", expected=1)
        self.cli(self.sources["unknown"], "--perfil", "manual", "--rect", "1141:686:134:24", "--simular")
        self.cli(self.sources["explainer"], "--rect", "0:10:20:20", "--simular", expected=1)
        self.cli(self.sources["explainer"], "--rect", "1200:700:80:20", "--simular", expected=1)
        self.cli(self.sources["explainer"], "--recortar-fotogramas", "9999", "--simular", expected=1)

    def test_audio_copy_silent_and_literal_filename(self):
        copied = self.root / "copy_audio.mp4"
        self.cli(self.sources["short"], "--audio", "copiar", "-o", copied)
        silent = self.root / "silent_source.mp4"
        run(["ffmpeg","-v","error","-y","-i",self.sources["short"],"-c:v","copy","-an",silent])
        unusual = self.root / "espacio ; $(nombre literal).mp4"
        shutil.copyfile(silent,unusual)
        result = self.root / "literal_result.mp4"
        self.cli(unusual,"-o",result,"--duracion-prueba","0.5")
        self.assertFalse(any(s["codec_type"]=="audio" for s in metadata(result)["streams"]))

    def test_count_fallback_and_batch(self):
        mkv = self.root / "without_frame_count.mkv"
        run(["ffmpeg","-v","error","-y","-i",self.sources["short"],"-c","copy",mkv])
        self.assertNotIn("nb_frames",video_stream(mkv))
        output = self.root / "count_fallback.mp4"
        result = self.cli(mkv,"-o",output)
        self.assertIn("Contando fotogramas",result.stdout)
        self.check_output(output,406,720,30,60)
        batch = self.root / "batch"
        run([sys.executable,SCRIPT,self.sources["short"],self.sources["explainer"],"--carpeta-salida",batch,"--duracion-prueba","0.5"])
        self.assertTrue((batch/"short_limpio.mp4").is_file())
        self.assertTrue((batch/"explainer_limpio.mp4").is_file())

    def test_logo_and_smart_detection(self):
        logo = self.root / "logo.png"
        run(["ffmpeg","-v","error","-y","-f","lavfi","-i","color=red:s=80x20", "-frames:v","1", "-threads","1",logo])
        replaced = self.root / "logo_result.mp4"
        self.cli(self.sources["explainer"],"--logo",logo,"-o",replaced,"--duracion-prueba","1")
        pixels=subprocess.run(["ffmpeg","-v","error","-ss","0.5","-i",str(replaced),"-vf","crop=20:10:1190:690",
            "-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","pipe:1"],capture_output=True,check=True).stdout
        self.assertGreater(sum(pixels[0::3])/len(pixels[0::3]),200)
        self.assertLess(sum(pixels[1::3])/len(pixels[1::3]),70)
        moving = self.root / "moving.mp4"
        run(["ffmpeg","-v","error","-y","-f","lavfi","-i","color=c=0xdddddd:s=1280x720:r=24:d=5",
            "-vf","drawtext=text='NotebookLM':x=550:y=50:fontsize=20:fontcolor=black:enable='lt(t,2)',drawtext=text='NotebookLM':x=1110:y=660:fontsize=16:fontcolor=black:enable='gte(t,2)'",
            "-c:v","libx264","-preset","ultrafast","-threads","2",moving])
        scanned = self.root / "smart_result.mp4"
        result = self.cli(moving,"--deteccion-inteligente","-o",scanned)
        self.assertIn("Intervalos de limpieza: 2",result.stdout)
        self.assertEqual(int(video_stream(scanned)["nb_frames"]),48)


if __name__ == "__main__":
    unittest.main(verbosity=2)
