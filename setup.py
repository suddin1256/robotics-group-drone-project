"""Explicit setup: downloads dependencies and builds SLAM with two jobs."""
import json, os, subprocess, sys, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DEPS=json.loads((ROOT/'dependencies.json').read_text())
def run(*args):subprocess.run(list(map(str,args)),cwd=ROOT,check=True)
def pixi(env,*args):run('pixi','run','--manifest-path',ROOT/env/'pixi.toml',*args)
if __name__=='__main__':
    for env in ['ros','slam']:run('pixi','install','--manifest-path',ROOT/env/'pixi.toml','--locked')
    # Native package supplies cv2; avoid installing a second OpenCV wheel.
    pixi('ros','python','-m','pip','install','--no-deps',f"git+{DEPS['tellopy']['url']}@{DEPS['tellopy']['commit']}")
    pixi('ros','python','-c','import rclpy, cv2, av, tellopy; from cv_bridge import CvBridge')
    prefix=ROOT/'local';vendor=ROOT/'vendor';vendor.mkdir(exist_ok=True)
    for name in ['g2o','stella_vslam']:
        path=vendor/name
        if not path.exists():run('git','clone',DEPS[name]['url'],path)
        current=subprocess.check_output(['git','-C',str(path),'status','--porcelain'],text=True)
        if current.strip():raise RuntimeError(f'{path} has local edits; refusing to reset it')
        run('git','-C',path,'checkout','--detach',DEPS[name]['commit'])
        run('git','-C',path,'submodule','update','--init','--recursive')
    env=ROOT/'slam/.pixi/envs/default'
    common=['-G','Ninja','-DCMAKE_BUILD_TYPE=Release',f'-DCMAKE_INSTALL_PREFIX={prefix}',f'-DCMAKE_PREFIX_PATH={prefix};{env}','-DBUILD_WITH_MARCH_NATIVE=OFF']
    pixi('slam','cmake','-S',vendor/'g2o','-B',ROOT/'build/g2o',*common,'-DG2O_BUILD_APPS=OFF','-DG2O_BUILD_EXAMPLES=OFF','-DG2O_USE_OPENGL=OFF','-DG2O_USE_CHOLMOD=OFF','-DG2O_USE_OPENMP=OFF')
    pixi('slam','cmake','--build',ROOT/'build/g2o','--parallel','2')
    pixi('slam','cmake','--install',ROOT/'build/g2o')
    pixi('slam','cmake','-S',vendor/'stella_vslam','-B',ROOT/'build/stella',*common,'-DUSE_ARUCO=OFF','-DUSE_GTSAM=OFF','-DUSE_OPENMP=OFF','-DUSE_SSE_ORB=OFF','-DUSE_SSE_FP_MATH=OFF')
    pixi('slam','cmake','--build',ROOT/'build/stella','--parallel','2')
    pixi('slam','cmake','--install',ROOT/'build/stella')
    pixi('slam','cmake','-S',ROOT/'slam/src/tello_live_slam','-B',ROOT/'build/live',*common)
    pixi('slam','cmake','--build',ROOT/'build/live','--parallel','2')
    vocabulary=ROOT/'slam/assets/orb_vocab.fbow'
    if not vocabulary.exists():
        temporary=vocabulary.with_suffix('.download')
        urllib.request.urlretrieve('https://raw.githubusercontent.com/stella-cv/FBoW_orb_vocab/main/orb_vocab.fbow',temporary)
        temporary.replace(vocabulary)
    print('Setup complete. Start with: python3 start.py --replay /path/to/video.avi')
