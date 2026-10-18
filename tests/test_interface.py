"""Pruebas de la cola local y su transporte HTTP con FFmpeg real."""

import http.client
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile

sys.path.insert(0, str((Path(__file__).resolve().parents[1] / "app")))
import interfaz_local as ui


def execute(command):
    subprocess.run([str(v) for v in command], check=True, capture_output=True)


def metadata(path):
    return json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)]))


def wait_until(condition, timeout=20):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("La tarea no terminó en el plazo de la prueba.")
        time.sleep(.04)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Se necesita FFmpeg")
class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = tempfile.TemporaryDirectory(prefix="notebooklm-ui-fixtures-")
        cls.base = Path(cls.fixtures.name)
        cls.horizontal = cls.base / "horizontal.mp4"
        cls.short = cls.base / "short.mp4"
        cls.too_short = cls.base / "too_short.mp4"
        cls.closing = cls.base / "closing.mp4"
        for path, geometry, fps, seconds in [(cls.horizontal,"1280x720",24,5),(cls.short,"406x720",30,5),(cls.too_short,"406x720",30,1)]:
            execute(["ffmpeg","-v","error","-y","-f","lavfi","-i",f"color=c=gray:s={geometry}:r={fps}:d={seconds}",
                     "-c:v","libx264","-preset","ultrafast","-threads","2",path])
        execute(["ffmpeg","-v","error","-y","-f","lavfi","-i","color=c=gray:s=1280x720:r=24:d=4",
                 "-f","lavfi","-i","color=c=red:s=1280x720:r=24:d=1", "-f","lavfi","-i","sine=frequency=440:duration=5",
                 "-filter_complex","[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map","[v]","-map","2:a",
                 "-c:v","libx264","-preset","ultrafast","-threads","2","-c:a","aac",cls.closing])

    @classmethod
    def tearDownClass(cls):
        cls.fixtures.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="notebooklm-ui-test-")
        self.root = Path(self.temporary.name)
        self.app = ui.Application(self.root / "sessions")
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        self.app.close()
        self.temporary.cleanup()

    def add(self, path, name=None):
        data = path.read_bytes()
        return self.app.accept_upload(name or path.name, len(data), io.BytesIO(data))

    def test_mixed_queue_preview_exact_frames_and_unique_names(self):
        first = self.add(self.horizontal, "mis vídeos.mp4")
        second = self.add(self.short, "mis vídeos.mp4")
        original = self.horizontal.read_bytes()
        self.app.start([first.id], preview_at=.5)
        wait_until(lambda: not self.app.busy)
        self.assertTrue(first.preview.is_file(),first.error)
        image = metadata(first.preview)["streams"][0]
        self.assertEqual((image["width"],image["height"]),(2560,720))
        self.app.start([first.id,second.id])
        wait_until(lambda: not self.app.busy)
        self.assertEqual([first.state,second.state],["done","done"],self.app.snapshot())
        self.assertEqual([int(metadata(item.output)["streams"][0]["nb_frames"]) for item in (first,second)],[48,60])
        self.assertNotEqual(first.output.name,second.output.name)
        self.assertFalse(list(self.app.output_dir.glob(".trabajo-*")))
        self.assertEqual(self.horizontal.read_bytes(),original)
        self.assertEqual(self.app.snapshot()["job_progress"],100)

    def test_error_does_not_stop_remaining_queue(self):
        failed = self.add(self.too_short)
        valid = self.add(self.horizontal)
        self.app.start([failed.id, valid.id])
        wait_until(lambda: not self.app.busy)
        self.assertEqual(failed.state,"error")
        self.assertIn("más corto",failed.error)
        self.assertEqual(valid.state,"done")
        self.assertTrue(valid.output.is_file())
        self.assertFalse(list(self.app.output_dir.glob(".trabajo-*")))

    def test_settings_and_preview_invalidation(self):
        item = self.add(self.short)
        self.app.start([item.id],preview_at=.5)
        wait_until(lambda: not self.app.busy)
        self.assertFalse(self.app.snapshot()["items"][0]["preview_stale"])
        settings = dict(item.settings,recortar=False)
        self.app.update(item.id,settings)
        self.assertTrue(self.app.snapshot()["items"][0]["preview_stale"])
        self.app.start([item.id])
        wait_until(lambda: not self.app.busy)
        self.assertEqual(int(metadata(item.output)["streams"][0]["nb_frames"]),150)
        with self.assertRaises(ui.AppError):
            self.app.update(item.id,dict(settings,perfil="manual"))
        with self.assertRaises(ui.AppError):
            self.app.update(item.id,dict(settings,inteligente=True,perfil="short"))

    def test_cancel_kills_child_process_and_leaves_pending(self):
        item = self.add(self.horizontal)
        pending = self.add(self.short)
        marker = self.root / "child.pid"
        script = self.root / "slow_worker.py"
        script.write_text("import subprocess,sys,time\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])\nPath(sys.argv[1]).write_text(str(p.pid))\ntime.sleep(30)\n")
        self.app.cli = lambda _item: [sys.executable,"-u",str(script),str(marker)]
        self.app.start([item.id,pending.id])
        wait_until(marker.is_file,timeout=5)
        self.app.cancel()
        wait_until(lambda: not self.app.busy,timeout=10)
        self.assertEqual(item.state,"cancelled")
        self.assertEqual(pending.state,"ready")
        self.assertFalse(list(self.app.output_dir.glob(".trabajo-*")))
        if sys.platform.startswith("linux"):
            status=Path(f"/proc/{int(marker.read_text())}/stat")
            self.assertTrue(not status.exists() or status.read_text().split()[2] in ("Z","X"))

    def test_bulk_settings_validate_whole_selection_before_changes(self):
        horizontal=self.add(self.horizontal)
        short=self.add(self.short)
        values=dict(ui.DEFAULTS,rect="1141:686:134:24",recortar=False)
        with self.assertRaises(ui.AppError):
            self.app.update_many([horizontal.id,short.id],values)
        self.assertEqual(horizontal.settings,ui.DEFAULTS)
        self.assertEqual(short.settings,ui.DEFAULTS)
        self.app.update_many([horizontal.id,short.id],dict(ui.DEFAULTS,recortar=False))
        self.assertFalse(horizontal.settings["recortar"])
        self.assertFalse(short.settings["recortar"])

    def test_custom_trim_per_video_frames_and_fractional_seconds(self):
        horizontal = self.add(self.horizontal)
        short = self.add(self.short)
        self.app.update(horizontal.id, dict(ui.DEFAULTS, recorte_modo="fotogramas", recorte_fotogramas=24))
        self.app.update(short.id, dict(ui.DEFAULTS, recorte_modo="segundos", recorte_segundos=1.2))
        self.app.start([horizontal.id, short.id])
        wait_until(lambda: not self.app.busy)
        self.assertEqual([horizontal.state, short.state], ["done", "done"], self.app.snapshot())
        for item, frames in ((horizontal, 96), (short, 114)):
            video = metadata(item.output)["streams"][0]
            self.assertEqual(int(video["nb_frames"]), frames)
            self.assertAlmostEqual(float(video["duration"]), frames / float(item.info.fps), places=5)
        self.assertEqual(horizontal.settings["recorte_modo"], "fotogramas")
        self.assertEqual(short.settings["recorte_modo"], "segundos")

    def test_custom_trim_bulk_frames_then_seconds_with_different_fps(self):
        horizontal = self.add(self.horizontal)
        short = self.add(self.short)
        ids = [horizontal.id, short.id]
        for settings, expected in (
            (dict(ui.DEFAULTS, recorte_modo="fotogramas", recorte_fotogramas=30), (90, 120)),
            (dict(ui.DEFAULTS, recorte_modo="segundos", recorte_segundos=1.5), (84, 105))):
            self.app.update_many(ids, settings)
            self.app.start(ids)
            wait_until(lambda: not self.app.busy)
            self.assertEqual([horizontal.state, short.state], ["done", "done"], self.app.snapshot())
            self.assertEqual([int(metadata(item.output)["streams"][0]["nb_frames"]) for item in (horizontal, short)], list(expected))
        self.assertEqual(len(list(self.app.output_dir.glob("*.mp4"))), 2)

    def test_custom_trim_invalid_values_and_bulk_duration_are_atomic(self):
        horizontal = self.add(self.horizontal)
        short = self.add(self.too_short)
        invalid = [dict(recorte_modo="otro"), dict(recorte_fotogramas=1.5), dict(recorte_fotogramas=True),
                   dict(recorte_fotogramas=-1), dict(recorte_segundos=-.1), dict(recorte_segundos="1"),
                   dict(recorte_segundos=True), dict(recorte_segundos=float("nan")), dict(recorte_segundos=float("inf"))]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ui.AppError):
                self.app.update(horizontal.id, dict(ui.DEFAULTS, **values))
        for settings in (dict(ui.DEFAULTS, recorte_modo="fotogramas", recorte_fotogramas=30),
                         dict(ui.DEFAULTS, recorte_modo="segundos", recorte_segundos=1)):
            with self.assertRaisesRegex(ui.AppError, "too_short.mp4"):
                self.app.update_many([horizontal.id, short.id], settings)
            self.assertEqual(horizontal.settings, ui.DEFAULTS)
            self.assertEqual(short.settings, ui.DEFAULTS)
        with self.assertRaises(ui.AppError):
            self.app.update(horizontal.id, dict(ui.DEFAULTS, recorte_modo="fotogramas", recorte_fotogramas=120))

    def test_zero_and_disabled_custom_trim_preserve_full_video(self):
        for settings in (dict(ui.DEFAULTS, recorte_modo="fotogramas", recorte_fotogramas=0),
                         dict(ui.DEFAULTS, recorte_modo="segundos", recorte_segundos=0),
                         dict(ui.DEFAULTS, recortar=False, recorte_modo="fotogramas", recorte_fotogramas=999)):
            item = self.add(self.too_short)
            self.app.update(item.id, settings)
            self.app.start([item.id])
            wait_until(lambda: not self.app.busy)
            self.assertEqual(item.state, "done", self.app.snapshot())
            self.assertEqual(int(metadata(item.output)["streams"][0]["nb_frames"]), 30)

    def test_http_custom_trim_settings_preserved_and_validated(self):
        self.start_http()
        self.authenticate()
        first = self.add(self.horizontal)
        second = self.add(self.short)
        values = dict(ui.DEFAULTS, recorte_modo="segundos", recorte_segundos=.75)
        self.assertEqual(self.request("POST", "/api/settings-many", {"ids":[first.id, second.id], "settings":values}, self.server.origin)[0], 200)
        values = dict(ui.DEFAULTS, recorte_modo="fotogramas", recorte_fotogramas=12)
        self.assertEqual(self.request("POST", "/api/settings", {"id":first.id, "settings":values}, self.server.origin)[0], 200)
        self.assertEqual(self.app.snapshot()["items"][0]["settings"], values)
        self.assertEqual(second.settings["recorte_segundos"], .75)
        self.assertEqual(self.request("POST", "/api/settings", {"id":first.id, "settings":dict(values, recorte_fotogramas=1.5)}, self.server.origin)[0], 400)

    def test_tail_preview_preserves_closing_and_exact_selected_frame_cut(self):
        item = self.add(self.closing)
        self.app.start_tail(item.id, 2)
        wait_until(lambda:not self.app.busy)
        self.assertTrue(item.tail.is_file(), item.tail_error)
        self.assertEqual(item.state, "ready")
        self.assertEqual((item.tail_start_frame, item.tail_total_frames), (72,120))
        self.assertTrue(item.tail_precise)
        streams = metadata(item.tail)["streams"]
        self.assertEqual(int(streams[0]["nb_frames"]), 48)
        self.assertAlmostEqual(float(streams[0]["duration"]), 2, places=4)
        self.assertTrue(any(s["codec_type"] == "audio" for s in streams))
        def pixel(path, second):
            return list(subprocess.check_output(["ffmpeg","-v","error","-ss",str(second),"-i",str(path),"-frames:v","1",
                 "-vf","crop=2:2:100:100,scale=1:1","-f","rawvideo","-pix_fmt","rgb24","pipe:1"]))
        before = pixel(item.tail, .95)
        after = pixel(item.tail, 1.05)
        self.assertLess(abs(before[0]-before[1]), 5)
        self.assertGreater(after[0]-after[1], 150)
        # Se incluye el fotograma 96 (índice 95); el cierre rojo empieza en el 97.
        self.app.update(item.id, dict(ui.DEFAULTS, recorte_modo="fotogramas", recorte_fotogramas=120-95-1))
        self.app.start([item.id])
        wait_until(lambda:not self.app.busy)
        self.assertEqual(item.state, "done", item.error)
        streams=metadata(item.output)["streams"]
        self.assertEqual(int(streams[0]["nb_frames"]), 96)
        self.assertAlmostEqual(float(streams[0]["duration"]),4,places=5)
        audio=next(s for s in streams if s["codec_type"] == "audio")
        self.assertLess(abs(float(audio["duration"])-4), .04)
        last=pixel(item.output,95/24)
        self.assertLess(abs(last[0]-last[1]),5)

    def test_tail_cache_settings_independent_short_video_and_remove(self):
        item=self.add(self.too_short)
        self.app.start_tail(item.id,10)
        wait_until(lambda:not self.app.busy)
        self.assertEqual(item.tail_start,0)
        self.assertEqual(int(metadata(item.tail)["streams"][0]["nb_frames"]),30)
        original=item.tail
        version=item.tail_version
        self.app.update(item.id,dict(ui.DEFAULTS,recortar=False))
        self.app.start_tail(item.id,10)
        self.assertFalse(self.app.busy)
        self.assertEqual(item.tail_version,version)
        self.app.start_tail(item.id,.5)
        wait_until(lambda:not self.app.busy)
        self.assertNotEqual(item.tail,original)
        self.assertFalse(original.exists())
        self.assertEqual(int(metadata(item.tail)["streams"][0]["nb_frames"]),15)
        final=item.tail
        self.app.remove([item.id])
        self.assertFalse(final.exists())

    def test_tail_http_range_invalid_window_and_no_finished_result_invalidation(self):
        self.start_http()
        self.authenticate()
        item=self.add(self.horizontal)
        self.app.start([item.id])
        wait_until(lambda:not self.app.busy)
        result=item.output.read_bytes()
        for value in (0,-1,61,True,"10",float("nan"),float("inf")):
            self.assertEqual(self.request("POST","/api/tail",{"id":item.id,"seconds":value},self.server.origin)[0],400)
        self.assertEqual(self.request("POST","/api/tail",{"id":item.id,"seconds":2},self.server.origin)[0],200)
        wait_until(lambda:not self.app.busy)
        self.assertEqual(item.state,"done")
        self.assertEqual(item.output.read_bytes(),result)
        url=self.app.snapshot()["items"][0]["tail"]
        self.assertEqual(self.request("GET",url)[2], item.tail.read_bytes())
        connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port)
        connection.request("GET",url,headers={"Cookie":self.cookie,"Range":"bytes=0-31"})
        response=connection.getresponse()
        self.assertEqual(response.status,206)
        self.assertEqual(response.read(),item.tail.read_bytes()[:32])
        connection.close()

    def start_http(self):
        self.server=ui.LocalServer(("127.0.0.1",0),self.app)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.cookie=""

    def request(self, method, path, body=None, origin=None):
        headers={}
        if self.cookie: headers["Cookie"]=self.cookie
        if origin: headers["Origin"]=origin
        if isinstance(body,dict):
            body=json.dumps(body).encode()
            headers["Content-Type"]="application/json"
        connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=15)
        connection.request(method,path,body,headers)
        response=connection.getresponse()
        data=response.read()
        info=dict(response.getheaders())
        code=response.status
        connection.close()
        return code,info,data

    def authenticate(self):
        code,headers,_=self.request("POST","/api/session",{"token":self.server.secret},self.server.origin)
        self.assertEqual(code,200)
        self.cookie=headers["Set-Cookie"].split(";",1)[0]

    def test_http_auth_upload_download_range_and_zip(self):
        self.start_http()
        self.assertEqual(self.request("GET","/api/state")[0],401)
        self.authenticate()
        self.assertEqual(self.request("POST","/api/run",{"ids":[]},"https://otra-pagina.test")[0],403)
        code,_,data=self.request("POST","/api/upload?name=horizontal.mp4",self.horizontal.read_bytes(),self.server.origin)
        self.assertEqual(code,201)
        identifier=json.loads(data)["id"]
        self.assertEqual(self.request("POST","/api/run",{"ids":[identifier]},self.server.origin)[0],200)
        wait_until(lambda:not self.app.busy)
        self.assertEqual(self.app.item(identifier).state,"done",self.app.snapshot())
        code,headers,data=self.request("GET",f"/download/{identifier}/result")
        self.assertEqual(code,200)
        self.assertIn("attachment",headers["Content-Disposition"])
        self.assertEqual(data,self.app.item(identifier).output.read_bytes())
        connection=http.client.HTTPConnection("127.0.0.1",self.server.server_port)
        connection.request("GET",f"/media/{identifier}/result",headers={"Cookie":self.cookie,"Range":"bytes=0-31"})
        response=connection.getresponse()
        self.assertEqual(response.status,206)
        self.assertEqual(response.read(),data[:32])
        connection.close()
        code,_,archive=self.request("GET","/download/all")
        self.assertEqual(code,200)
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            self.assertEqual(len(zipped.namelist()),1)
            self.assertEqual(zipped.read(zipped.namelist()[0]),data)
        self.assertEqual(self.request("GET","/../../notebooklm_ffmpeg.py")[0],404)
        self.assertEqual(self.request("POST","/api/remove",{"ids":[identifier]},self.server.origin)[0],200)
        self.assertFalse(self.app.items)
        self.assertFalse(list(self.app.output_dir.glob("*.mp4")))

    def test_shutdown_deletes_session_and_preserves_downloaded_mp4_zip_and_originals(self):
        self.start_http()
        self.authenticate()
        first=self.add(self.horizontal)
        second=self.add(self.short)
        self.app.start([first.id, second.id])
        wait_until(lambda:not self.app.busy)
        self.app.start_tail(first.id,2)
        wait_until(lambda:not self.app.busy)
        source_original=self.horizontal.read_bytes()
        downloaded=self.root/'Downloads'
        downloaded.mkdir()
        saved=downloaded/'video.mp4'
        saved.write_bytes(self.request('GET',f'/download/{first.id}/result')[2])
        bundle=downloaded/'videos.zip'
        bundle.write_bytes(self.request('GET','/download/all')[2])
        saved_bytes=saved.read_bytes()
        session=self.app.work_dir
        output=first.output
        tail=first.tail
        response=self.request('POST','/api/shutdown',{},self.server.origin)
        self.assertEqual(response[0],200)
        self.assertTrue(json.loads(response[2])['session_deleted'])
        self.assertFalse(session.exists())
        self.assertFalse(output.exists())
        self.assertFalse(second.output.exists())
        self.assertFalse(tail.exists())
        self.assertEqual(saved.read_bytes(),saved_bytes)
        self.assertEqual(self.horizontal.read_bytes(),source_original)
        with zipfile.ZipFile(bundle) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(len(archive.namelist()),2)
        self.app.close()

    def test_shutdown_during_processing_removes_partial_files(self):
        item=self.add(self.horizontal)
        pending=self.add(self.short)
        started=self.root/'started'
        script=self.root/'slow.py'
        script.write_text("import sys,time\nfrom pathlib import Path\np=Path(sys.argv[sys.argv.index('-o')+1]);p.write_bytes(b'partial')\nPath(sys.argv[1]).write_text('ready')\ntime.sleep(30)\n")
        self.app.cli=lambda _item:[sys.executable,'-u',str(script),str(started)]
        self.app.start([item.id,pending.id])
        wait_until(started.is_file,timeout=5)
        session=self.app.work_dir
        self.app.close()
        self.assertFalse(session.exists())
        self.assertFalse(self.app.worker.is_alive())
        self.assertTrue(self.app.closed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
