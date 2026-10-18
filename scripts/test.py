"""Run the source suite with the FFmpeg bundled for this target."""
import argparse
import os
import subprocess
import sys
from build import ROOT, TARGETS, layout

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target',required=True,choices=TARGETS)
args = parser.parse_args()
_,_,app,_ = layout(args.target)
env = dict(os.environ,PATH=str(app/'bin')+os.pathsep+os.environ.get('PATH',''))
subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/'tests'),'-v'],env=env,cwd=ROOT,check=True)
