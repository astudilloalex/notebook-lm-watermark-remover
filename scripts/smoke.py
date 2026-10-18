"""Exercise a staged or installed app without system tools, including downloads and cleanup."""

import argparse
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.parse import quote,urlparse
import zipfile

from build import BUILD,ROOT,TARGETS,layout

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target',required=True,choices=TARGETS)
parser.add_argument('--base',type=Path,help='Installed base directory (Resources inside a macOS bundle).')
parser.add_argument('--label',default='portable')
args = parser.parse_args()
package,base,app,launcher = layout(args.target)
if args.base:
    base = args.base.resolve()
    app = base/'app'
    launcher = base.parent/'MacOS/NotebookLM Studio' if args.target.startswith('macos') else base/('NotebookLM Studio.exe' if args.target.startswith('windows') else 'NotebookLM Studio')
work = BUILD/'smoke'/(args.label+'-'+args.target)
if work.exists():
    shutil.rmtree(work)
work.mkdir(parents=True)
suffix = '.exe' if args.target.startswith('windows') else ''
ffmpeg,ffprobe = app/'bin'/('ffmpeg'+suffix),app/'bin'/('ffprobe'+suffix)
fixtures = work/'Originals'
fixtures.mkdir()
for name,geometry,fps,seconds in [('horizontal.mp4','1280x720',24,5),('short.mp4','406x720',30,5)]:
    subprocess.run([str(ffmpeg),'-v','error','-f','lavfi','-i',f'color=c=gray:s={geometry}:r={fps}:d={seconds}',
                    '-c:v','libx264','-preset','ultrafast','-threads','2',str(fixtures/name)],check=True)
originals = {path.name:path.read_bytes() for path in fixtures.iterdir()}
data = work/'Data'
env = dict(os.environ,PATH=str(work/'no-tools'),PYTHONHOME=str(work/'no-system-python'),
           PYTHONPATH=str(work/'no-system-modules'),NOTEBOOKLM_DATA_DIR=str(data))
process = subprocess.Popen([str(launcher),'--sin-abrir'],env=env)
cookie = ''
address = None
shutdown = False


def wait_until(condition,timeout=60):
    deadline = time.monotonic()+timeout
    while not condition():
        if time.monotonic()>deadline:
            raise AssertionError('Timed out waiting for the app')
        time.sleep(.1)


def request(method,path,body=None):
    headers = {'Origin':origin}
    if cookie:
        headers['Cookie'] = cookie
    if isinstance(body,dict):
        body = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    connection = http.client.HTTPConnection(address.hostname,address.port,timeout=60)
    connection.request(method,path,body,headers)
    response = connection.getresponse()
    content = response.read()
    code = response.status
    headers = dict(response.getheaders())
    connection.close()
    assert code in (200,201),(path,code,content[:1000])
    return headers,content


def state():
    return json.loads(request('GET','/api/state')[1])


try:
    log = data/'aplicacion.log'
    wait_until(lambda:log.exists() and re.search(r'http://127\.0\.0\.1:\d+/#[\w-]+',log.read_text(encoding='utf-8')))
    url = re.search(r'http://127\.0\.0\.1:\d+/#[\w-]+',log.read_text(encoding='utf-8'))[0]
    address = urlparse(url)
    origin = f'http://{address.netloc}'
    headers,_ = request('POST','/api/session',{'token':address.fragment})
    cookie = headers['Set-Cookie'].split(';',1)[0]
    assert not state()['tools_error'],state()
    assert b'Descarga antes de cerrar' in request('GET','/')[1]
    ids = []
    uploaded = {}
    for filename,content in originals.items():
        identifier = json.loads(request('POST','/api/upload?name='+quote(filename),content)[1])['id']
        ids.append(identifier)
        uploaded[filename] = identifier
    request('POST','/api/tail',{'id':uploaded['horizontal.mp4'],'seconds':2})
    wait_until(lambda:not state()['busy'])
    tail_item = next(item for item in state()['items'] if item['id']==uploaded['horizontal.mp4'])
    assert tail_item['tail'] and tail_item['tail_precise'],state()
    request('POST','/api/run',{'ids':ids})
    wait_until(lambda:not state()['busy'])
    final = state()
    assert all(item['state']=='done' for item in final['items']),final
    downloads = work/'Downloads'
    downloads.mkdir()
    expected_frames = {uploaded['horizontal.mp4']:48,uploaded['short.mp4']:60}
    for item in final['items']:
        frames = expected_frames[item['id']]
        content = request('GET',f"/download/{item['id']}/result")[1]
        saved = downloads/item['result']
        saved.write_bytes(content)
        info = json.loads(subprocess.check_output([str(ffprobe),'-v','error','-show_streams','-of','json',str(saved)]))
        assert int(info['streams'][0]['nb_frames'])==frames,info
    archive = request('GET','/download/all')[1]
    (downloads/'videos.zip').write_bytes(archive)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        assert bundle.testzip() is None and len(bundle.namelist())==2
    saved_hashes = {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in downloads.iterdir()}
    result = json.loads(request('POST','/api/shutdown',{})[1])
    shutdown = True
    assert result['session_deleted']
    assert process.wait(timeout=30)==0
    assert not Path(final['output_dir']).parent.exists()
    assert not list((data/'Sesiones').rglob('*.mp4'))
    assert all(hashlib.sha256(path.read_bytes()).hexdigest()==saved_hashes[path.name] for path in downloads.iterdir())
    assert all(path.read_bytes()==originals[path.name] for path in fixtures.iterdir())
    record = {'target':args.target,'result':'OK','batch':'Horizontal 48 frames; Short 60 frames',
              'cleanup':'Session deleted; downloaded MP4/ZIP copies and originals preserved',
              'runtime':'Bundled Python and FFmpeg, no system tools in PATH'}
    (ROOT/'dist'/f'verification-{args.label}-{args.target}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(record,ensure_ascii=False),flush=True)
finally:
    if address and cookie and not shutdown:
        try:
            request('POST','/api/shutdown',{})
        except (OSError,AssertionError):
            pass
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=15)
