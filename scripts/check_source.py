"""Verify that Git contains only source code, documentation and text assets."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
files = subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
allowed = {'.py','.c','.sh','.js','.html','.css','.svg','.md','.json','.yml','.yaml','.txt','.toml','.in','.iss','.desktop','.xml'}
for name in filter(None,files):
    path = ROOT/name
    assert path.suffix in allowed or path.name in {'VERSION','.gitignore','.gitattributes'},name
    data = path.read_bytes()
    assert b'\0' not in data and len(data)<1024*1024,name
    data.decode('utf-8')
print('Git contains only text source code and documentation.')
