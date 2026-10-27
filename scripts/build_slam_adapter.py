"""Rebuild only our small SLAM adapter, preserving the existing Stella installation."""
import argparse
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_config import ROOT, pixi_executable

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-existing',action='store_true')
    args=parser.parse_args()
    home=Path.home()/'Documents/tello-slam'
    manifest=home/'pixi.toml' if args.reuse_existing else ROOT/'environments/slam/pixi.toml'
    prefix=home/'local' if args.reuse_existing else ROOT/'local'
    environment=manifest.parent/'.pixi/envs/default'
    build=ROOT/'build/adapter-legacy' if args.reuse_existing else ROOT/'build/live'
    if not prefix.is_dir():
        parser.error('Stella installation missing; run SLAM setup first.')
    command=[pixi_executable() or 'pixi','run','--manifest-path',str(manifest),'cmake']
    subprocess.run(command+['-S',str(ROOT/'slam/src/tello_live_slam'),'-B',str(build),'-G','Ninja',
                            '-DCMAKE_BUILD_TYPE=Release',f'-DCMAKE_PREFIX_PATH={prefix};{environment}'],check=True)
    subprocess.run(command+['--build',str(build),'--parallel','2'],check=True)

if __name__=='__main__':main()
