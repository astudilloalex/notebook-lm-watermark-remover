"""Construye paquetes nativos desde el checkout y dependencias HTTPS verificadas."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import zipfile

from icons import generate

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT/'.build'
TARGETS = {
    'linux-x64': ('linux','x86_64',['python-linux','ffmpeg-linux'],'Linux-x64'),
    'windows-x64': ('windows','AMD64',['python-windows','ffmpeg-windows'],'Windows-x64'),
    'macos-arm64': ('darwin','arm64',['python-mac-arm','ffmpeg-mac-arm','ffprobe-mac-arm'],'macOS-AppleSilicon'),
    'macos-x64': ('darwin','x86_64',['python-mac-intel','ffmpeg-mac-intel','ffprobe-mac-intel'],'macOS-Intel'),
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def get_json(url):
    headers = {'User-Agent':'NotebookLM-Studio-build','Accept':'application/vnd.github+json'}
    if os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=60) as response:
        return json.load(response)


def resolve(identifier, value):
    result = dict(value, id=identifier)
    release = value.get('release')
    if release:
        metadata = get_json(f"https://api.github.com/repos/{release['repo']}/releases/tags/{release['tag']}")
        asset = next(item for item in metadata['assets'] if item['name'] == release['asset'])
        result.update(url=asset['browser_download_url'], sha256=asset.get('digest','').removeprefix('sha256:'))
    if not re.fullmatch('[a-f0-9]{64}',result['sha256']):
        raise RuntimeError('La dependencia no declara un SHA-256 verificable: '+identifier)
    return result


def download(item):
    cache = BUILD/'cache'
    cache.mkdir(parents=True,exist_ok=True)
    path = cache/(item['sha256']+'-'+item['file'])
    if path.exists():
        if digest(path) != item['sha256']:
            raise RuntimeError('El archivo de caché no coincide con su SHA-256: '+item['id'])
        return item,path
    for attempt in range(3):
        partial = path.with_name(path.name+'.part')
        try:
            print('Descargando',item['id'],flush=True)
            request = urllib.request.Request(item['url'],headers={'User-Agent':'NotebookLM-Studio-build'})
            with urllib.request.urlopen(request,timeout=120) as response, partial.open('wb') as stream:
                shutil.copyfileobj(response,stream,1024*1024)
            if digest(partial) != item['sha256']:
                raise RuntimeError('SHA-256 incorrecto: '+item['id'])
            partial.replace(path)
            return item,path
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt+1)
        finally:
            partial.unlink(missing_ok=True)


def layout(target):
    package = BUILD/'staging'/target
    if target.startswith('macos'):
        bundle = package/'NotebookLM Studio.app'
        base = bundle/'Contents/Resources'
        launcher = bundle/'Contents/MacOS/NotebookLM Studio'
    else:
        base = package/'NotebookLM Studio'
        launcher = base/('NotebookLM Studio.exe' if target.startswith('windows') else 'NotebookLM Studio')
    return package,base,base/'app',launcher


def unpack_python(archive, destination):
    if archive.name.endswith('.zip'):
        destination.mkdir(parents=True)
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(destination)
        (destination/'python313._pth').write_text('python313.zip\n.\n../app\n',encoding='utf-8')
    else:
        with tempfile.TemporaryDirectory(dir=BUILD) as scratch:
            with tarfile.open(archive) as bundle:
                bundle.extractall(scratch,filter='data')
            shutil.move(str(Path(scratch)/'python'),destination)


def unpack_ffmpeg(archive, destination):
    destination.mkdir(parents=True,exist_ok=True)
    if archive.name.endswith('.zip'):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.namelist():
                name = Path(member).name
                if name in ('ffmpeg','ffprobe','ffmpeg.exe','ffprobe.exe'):
                    with bundle.open(member) as stream, (destination/name).open('wb') as output:
                        shutil.copyfileobj(stream,output)
                    (destination/name).chmod(0o755)
    else:
        with tarfile.open(archive) as bundle:
            for member in bundle:
                if member.isfile() and Path(member.name).name in ('ffmpeg','ffprobe'):
                    target = destination/Path(member.name).name
                    with bundle.extractfile(member) as stream, target.open('wb') as output:
                        shutil.copyfileobj(stream,output)
                    target.chmod(0o755)


def compile_windows(launcher, version, icons):
    resources = BUILD/'windows'
    resources.mkdir(exist_ok=True)
    icon = str(icons/'icon.ico').replace('\\','/')
    numbers = version.replace('.',',')+',0'
    rc = resources/'launcher.rc'
    rc.write_text(f'1 ICON "{icon}"\n1 VERSIONINFO\nFILEVERSION {numbers}\nPRODUCTVERSION {numbers}\nBEGIN\n BLOCK "StringFileInfo"\n BEGIN\n  BLOCK "040904b0"\n  BEGIN\n   VALUE "FileDescription", "NotebookLM Studio"\n   VALUE "ProductVersion", "{version}"\n  END\n END\n BLOCK "VarFileInfo"\n BEGIN\n  VALUE "Translation", 0x409, 1200\n END\nEND\n')
    vswhere = Path(os.environ['ProgramFiles(x86)'])/'Microsoft Visual Studio/Installer/vswhere.exe'
    installation = subprocess.check_output([str(vswhere),'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).strip()
    vcvars = Path(installation)/'VC/Auxiliary/Build/vcvars64.bat'
    obj, res = resources/'launcher.obj', resources/'launcher.res'
    commands = [
        f'call "{vcvars}" >nul',
        f'cl.exe /nologo /O2 /GS- /Zl /c "{ROOT / "launchers/windows.c"}" /Fo"{obj}"',
        f'rc.exe /nologo /fo "{res}" "{rc}"',
        f'link.exe /nologo /entry:start /subsystem:windows /nodefaultlib /out:"{launcher}" "{obj}" "{res}" kernel32.lib user32.lib',
    ]
    script = resources/'compile.cmd'
    script.write_text('@echo off\n'+'\n'.join(command+'\nif errorlevel 1 exit /b %errorlevel%' for command in commands)+'\n')
    subprocess.run(['cmd.exe','/d','/c',str(script)],check=True)


def zip_tree(folder, output):
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(folder.rglob('*')):
            if '__pycache__' in path.parts or path.suffix == '.pyc':
                continue
            relative = str(path.relative_to(folder)).replace(os.sep,'/')
            if path.is_symlink():
                if not path.resolve().is_relative_to(folder.resolve()):
                    raise RuntimeError('Enlace fuera del paquete: '+relative)
                info = zipfile.ZipInfo(relative)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK|0o777)<<16
                archive.writestr(info,os.readlink(path).encode())
            elif path.is_file():
                archive.write(path,relative)


def build(target):
    system, architecture, identifiers, label = TARGETS[target]
    if platform.system().lower() != system or platform.machine().lower() != architecture.lower():
        raise RuntimeError('Este objetivo se construye en su sistema y arquitectura nativos: '+target)
    version = (ROOT/'VERSION').read_text().strip()
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):
        raise RuntimeError('VERSION debe contener tres números separados por puntos.')
    BUILD.mkdir(exist_ok=True)
    config = json.loads((ROOT/'dependencies.json').read_text())['components']
    resolved = [resolve(identifier,config[identifier]) for identifier in identifiers]
    with ThreadPoolExecutor(max_workers=3) as pool:
        components = list(pool.map(download,resolved))
    package,base,app,launcher = layout(target)
    if package.exists():
        shutil.rmtree(package)
    app.mkdir(parents=True)
    shutil.copytree(ROOT/'app',app,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for item,archive in components:
        if item['id'].startswith('python'):
            unpack_python(archive,base/'runtime')
        else:
            unpack_ffmpeg(archive,app/'bin')
    icons = BUILD/'icons'
    generate(icons)
    launcher.parent.mkdir(parents=True,exist_ok=True)
    if system == 'windows':
        compile_windows(launcher,version,icons)
    elif system == 'linux':
        subprocess.run(['gcc','-Os','-static','-s',str(ROOT/'launchers/linux.c'),'-o',str(launcher)],check=True)
        launcher.chmod(0o755)
    else:
        shutil.copyfile(ROOT/'launchers/macos.sh',launcher)
        launcher.chmod(0o755)
        shutil.copyfile(icons/'icon.icns',base/'icon.icns')
        info = {'CFBundleName':'NotebookLM Studio','CFBundleDisplayName':'NotebookLM Studio','CFBundleIdentifier':'local.notebooklm.studio','CFBundleVersion':version,'CFBundleShortVersionString':version,'CFBundlePackageType':'APPL','CFBundleExecutable':'NotebookLM Studio','CFBundleIconFile':'icon.icns','LSMinimumSystemVersion':'12.0','LSUIElement':True,'NSHighResolutionCapable':True}
        (package/'NotebookLM Studio.app/Contents/Info.plist').write_bytes(plistlib.dumps(info))
        (package/'NotebookLM Studio.app/Contents/PkgInfo').write_bytes(b'APPL????')
    docs = base if system != 'darwin' else package
    shutil.copyfile(ROOT/'docs/USO.md',docs/'Guia-de-uso.md')
    (docs/'LEEME.txt').write_text(f'NotebookLM Studio {version}\n\nDescomprime todo y abre {launcher.name}. Python y FFmpeg están incluidos.\nDESCARGA ANTES DE CERRAR: todos los resultados internos se eliminan al confirmar Eliminar sesión y cerrar.\nLos originales y las copias descargadas fuera de la sesión se conservan.\nCerrar solo la pestaña no apaga el servidor.\nLos paquetes no tienen firma comercial ni notarización Apple.\nConsulta Guia-de-uso.md para los botones y el recorte del cierre.\n',encoding='utf-8')
    licenses = docs/'Licencias'
    licenses.mkdir()
    python_license = base/'runtime/LICENSE.txt' if system == 'windows' else base/'runtime/lib/python3.13/LICENSE.txt'
    shutil.copyfile(python_license,licenses/'Python.txt')
    binary = app/'bin'/('ffmpeg.exe' if system == 'windows' else 'ffmpeg')
    for option,name in [('-L','FFmpeg-licencia.txt'),('-buildconf','FFmpeg-configuracion.txt')]:
        report = subprocess.run([str(binary),'-hide_banner',option],capture_output=True,check=True)
        (licenses/name).write_bytes(report.stdout+report.stderr)
    (licenses/'COMPONENTES.json').write_text(json.dumps(resolved,indent=2)+'\n')
    (licenses/'FUENTES.txt').write_text('Python: https://github.com/python/cpython y https://github.com/astral-sh/python-build-standalone\nFFmpeg: https://github.com/FFmpeg/FFmpeg\nRecetas Linux/Windows: https://github.com/BtbN/FFmpeg-Builds\nRecetas macOS: https://github.com/Martin-Riedl/FFmpeg-Builds\nAplicación y recetas: https://github.com/astudilloalex/notebook-lm-watermark-remover\nLos ejecutables de terceros no se modifican. COMPONENTES.json identifica las descargas y sus SHA-256.\n')
    if system == 'linux':
        shutil.copyfile('/usr/share/common-licenses/LGPL-2.1',licenses/'glibc-LGPL-2.1.txt')
        (licenses/'glibc-fuentes.txt').write_text('Lanzador enlazado estáticamente con '+os.confstr('CS_GNU_LIBC_VERSION')+'.\nFuentes: https://ftp.gnu.org/gnu/glibc/\nReceta: gcc -Os -static -s linux.c -o "NotebookLM Studio"\n')
    shutil.copytree(ROOT/'launchers',docs/'Fuentes-lanzador')
    output = ROOT/'dist'
    output.mkdir(exist_ok=True)
    artifact = output/f'NotebookLM-Studio-{label}.{ "tar.gz" if system == "linux" else "zip"}'
    if system == 'linux':
        with tarfile.open(artifact,'w:gz') as archive:
            for path in package.iterdir():
                archive.add(path,arcname=path.name,filter=lambda entry:None if '__pycache__' in Path(entry.name).parts or entry.name.endswith('.pyc') else entry)
    else:
        zip_tree(package,artifact)
    artifact.with_name(artifact.name+'.sha256').write_text(digest(artifact)+'  '+artifact.name+'\n')
    print('Paquete creado:',artifact,flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target',required=True,choices=TARGETS)
    build(parser.parse_args().target)
