"""Comprueba que Git solo contenga código, documentación y recursos de texto."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
files = subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
allowed = {'.py','.c','.sh','.js','.html','.css','.svg','.md','.json','.yml','.yaml','.txt','.toml','.in'}
for name in filter(None,files):
    path = ROOT/name
    assert path.suffix in allowed or path.name in {'VERSION','.gitignore','.gitattributes'},name
    data = path.read_bytes()
    assert b'\0' not in data and len(data)<1024*1024,name
    data.decode('utf-8')
print('Git contiene únicamente fuentes y documentación de texto.')
