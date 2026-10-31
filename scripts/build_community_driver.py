"""Build pinned upstream ROS message types locally; never connect to a drone."""
import argparse
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_config import ROOT, CORE, pixi_executable

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--reuse-existing',action='store_true')
    args=p.parse_args()
    manifest=Path.home()/'Documents/tello-ros2/pixi.toml' if args.reuse_existing else CORE
    prefix=ROOT/'local/community'
    command=[pixi_executable() or 'pixi','run','--manifest-path',str(manifest),'cmake']
    subprocess.run(command+['-S',str(ROOT/'third_party/tello_ros2_driver/tello_msgs'),
                           '-B',str(ROOT/'build/community-msgs'),'-G','Ninja',
                           '-DCMAKE_POLICY_VERSION_MINIMUM=3.5',
                           '-DCMAKE_INSTALL_PREFIX='+str(prefix),
                           '-DCMAKE_INSTALL_RPATH='+str(prefix/'lib')+';'+str(manifest.parent/'.pixi/envs/default/lib'),
                           '-DPython3_EXECUTABLE='+str(manifest.parent/'.pixi/envs/default/bin/python')],check=True)
    subprocess.run(command+['--build',str(ROOT/'build/community-msgs'),'--parallel','2'],check=True)
    subprocess.run(command+['--install',str(ROOT/'build/community-msgs')],check=True)
    print('Community message types installed locally. No hardware was started.')

if __name__=='__main__':main()
