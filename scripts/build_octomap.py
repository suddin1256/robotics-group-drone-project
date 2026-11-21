"""Build pinned upstream OctoMap without ROS, Qt, CUDA, or system-wide installs."""
import argparse,hashlib,os,subprocess,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_config import ROOT,pixi_executable

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--reuse-existing',action='store_true');args=parser.parse_args()
    archive=ROOT/'.cache/octomap-v1.10.1.zip';archive.parent.mkdir(exist_ok=True)
    digest='c6e88860e3be252d3e5e6e5caa69da4d8664da853871ded373307fc88b8dfa04'
    if not archive.exists():
        import requests
        response=requests.get('https://codeload.github.com/OctoMap/octomap/zip/refs/tags/v1.10.1',timeout=90);response.raise_for_status();archive.write_bytes(response.content)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=digest:raise ValueError('OctoMap source checksum mismatch')
    source=ROOT/'.tools/octomap-1.10.1';source.parent.mkdir(exist_ok=True)
    if not source.exists():
        with zipfile.ZipFile(archive) as stream:
            for item in stream.infolist():
                destination=(source.parent/item.filename).resolve()
                if not destination.is_relative_to(source.parent.resolve()):raise ValueError('Unsafe archive path')
            stream.extractall(source.parent)
    manifest=Path.home()/'Documents/tello-slam/pixi.toml' if args.reuse_existing else ROOT/'environments/slam/pixi.toml'
    cmake=[pixi_executable() or 'pixi','run','--manifest-path',str(manifest),'cmake']
    prefix=ROOT/'local/octomap';build=ROOT/'build/octomap'
    def run(tail):subprocess.run(cmake+list(map(str,tail)),check=True)
    run(['-S',source,'-B',build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',f'-DCMAKE_INSTALL_PREFIX={prefix}',
         '-DBUILD_OCTOVIS_SUBPROJECT=OFF','-DBUILD_DYNAMICETD3D_SUBPROJECT=OFF','-DBUILD_TESTING=OFF',
         '-DCMAKE_EXPORT_NO_PACKAGE_REGISTRY=ON'])
    run(['--build',build,'--parallel','2']);run(['--install',build])
    run(['-S',ROOT/'mapping','-B',ROOT/'build/occupancy','-G','Ninja','-DCMAKE_BUILD_TYPE=Release',f'-DCMAKE_PREFIX_PATH={prefix}'])
    run(['--build',ROOT/'build/occupancy','--parallel','2'])

if __name__=='__main__':main()
