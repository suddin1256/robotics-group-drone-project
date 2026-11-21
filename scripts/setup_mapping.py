"""Online preparation launched by the app; no drone connection."""
import os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    sys.path.insert(0,str(ROOT))
    from project_config import read_state,fingerprint,host_platform
    state=read_state()
    if state and state.get('fingerprint')!=fingerprint(state.get('features',[]),host_platform()):
        # Reconcile the existing portable installation instead of pretending that
        # a changed dependency fingerprint has already been satisfied.
        flags=['--'+feature for feature in ['hardware','vision','slam'] if feature in state.get('features',[])]
        if '--vision' not in flags:flags.append('--vision')
        subprocess.run([sys.executable,str(ROOT/'bootstrap.py'),*flags],check=True)
        raise SystemExit(0)
    subprocess.run([sys.executable,'-m','pip','install','transformers==4.46.3','open3d==0.19.0'],check=True)
    subprocess.run([sys.executable,str(ROOT/'vision/prepare_mapping.py')],check=True)
    command=[sys.executable,str(ROOT/'scripts/build_octomap.py')]
    if (Path.home()/'Documents/tello-slam/pixi.toml').exists() and not (ROOT/'local/lib/libstella_vslam.dylib').exists():command+=['--reuse-existing']
    subprocess.run(command,check=True)
