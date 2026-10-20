"""Pull shared updates; refresh dependencies only when their fingerprint changes."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def main():
    changes = subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True)
    if changes.strip():
        print('Local edits found. Commit/stash them and update through your branch workflow; no files were changed.')
        return 1
    subprocess.run(['git', 'pull', '--ff-only'], cwd=ROOT, check=True)
    check = subprocess.run([sys.executable, str(ROOT / 'bootstrap.py'), '--check'], cwd=ROOT)
    if check.returncode:
        subprocess.run([sys.executable, str(ROOT / 'bootstrap.py')], cwd=ROOT, check=True)
    print('Update complete. Restart the prototype to use the new code.')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (subprocess.CalledProcessError, OSError) as error:
        print(f'Update stopped: {error}', file=sys.stderr)
        raise SystemExit(1)
