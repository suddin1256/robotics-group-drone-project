"""Pinned source build adapted from the existing Intel-Mac recipe; cross-platform runtime unverified."""
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_config import ROOT, host_platform, pixi_executable

def build():
    manifest = ROOT / 'environments/slam/pixi.toml'
    pixi = pixi_executable()
    if not pixi:
        raise RuntimeError('Run bootstrap.py first.')
    def run(*args):
        print('+', ' '.join(map(str,args)), flush=True)
        subprocess.run(list(map(str,args)), cwd=ROOT, check=True)
    def cmake(*args):
        run(pixi,'run','--locked','--manifest-path',manifest,'cmake',*args)
    deps = json.loads((ROOT / 'dependencies.json').read_text())
    vendor = ROOT / 'vendor'
    vendor.mkdir(exist_ok=True)
    for name in ['g2o','stella_vslam']:
        source = vendor / name
        if not source.exists():
            run('git','clone',deps[name]['url'],source)
        changed = subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True)
        if changed.strip():
            raise RuntimeError(f'{source} has local edits; refusing to reset it.')
        run('git','-C',source,'checkout','--detach',deps[name]['commit'])
        run('git','-C',source,'submodule','update','--init','--recursive')
    prefix = ROOT / 'local'
    environment = manifest.parent / '.pixi/envs/default'
    common = ['-G','Ninja','-DCMAKE_BUILD_TYPE=Release',f'-DCMAKE_INSTALL_PREFIX={prefix}',
              f'-DCMAKE_PREFIX_PATH={prefix};{environment}','-DBUILD_WITH_MARCH_NATIVE=OFF']
    cmake('-S',vendor/'g2o','-B',ROOT/'build/g2o',*common,
          '-DG2O_BUILD_APPS=OFF','-DG2O_BUILD_EXAMPLES=OFF','-DG2O_USE_OPENGL=OFF',
          '-DG2O_USE_CHOLMOD=OFF','-DG2O_USE_OPENMP=OFF')
    cmake('--build',ROOT/'build/g2o','--parallel','2')
    cmake('--install',ROOT/'build/g2o')
    architecture = []
    if host_platform() == 'osx-arm64':
        architecture = ['-DUSE_MMX=OFF','-DUSE_AVX=OFF','-DUSE_SSE=OFF','-DUSE_SSE2=OFF',
                        '-DUSE_SSE3=OFF','-DUSE_SSE4=OFF']
    cmake('-S',vendor/'stella_vslam','-B',ROOT/'build/stella',*common,*architecture,
          '-DUSE_ARUCO=OFF','-DUSE_GTSAM=OFF','-DUSE_OPENMP=OFF',
          '-DUSE_SSE_ORB=OFF','-DUSE_SSE_FP_MATH=OFF')
    cmake('--build',ROOT/'build/stella','--parallel','2')
    cmake('--install',ROOT/'build/stella')
    cmake('-S',ROOT/'slam/src/tello_live_slam','-B',ROOT/'build/live',*common)
    cmake('--build',ROOT/'build/live','--parallel','2')
    vocabulary = ROOT / 'slam/assets/orb_vocab.fbow'
    if not vocabulary.is_file():
        import ssl, urllib.request
        cert = Path('/etc/ssl/cert.pem')
        context = ssl.create_default_context(cafile=str(cert)) if cert.is_file() else ssl.create_default_context()
        temporary = vocabulary.with_suffix('.download')
        with urllib.request.urlopen('https://raw.githubusercontent.com/stella-cv/FBoW_orb_vocab/main/orb_vocab.fbow',context=context,timeout=120) as response:
            temporary.write_bytes(response.read())
        temporary.replace(vocabulary)
    print('SLAM build completed. Verify tracking with a suitable real recording.')

if __name__ == '__main__':
    try:
        build()
    except (RuntimeError,subprocess.CalledProcessError,OSError) as error:
        print(f'SLAM build failed: {error}',file=sys.stderr)
        raise SystemExit(1)
