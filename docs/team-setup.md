# First setup and shared updates

The same application source runs from each member's clone. Pixi selects a locked dependency set for Intel macOS (`osx-64`), Apple Silicon macOS (`osx-arm64`), or x86-64 Ubuntu/Linux (`linux-64`, including Windows WSL2). These three environments have resolved successfully. Actual clean installation/runtime on Apple Silicon and Windows/WSL2 still needs teammate verification.

## Mac: first time

Install Git and a Python 3 version (3.10 or later) if missing. On a Mac, `git --version` may open Apple's Command Line Tools installer; complete that first. Keep internet access during setup.

```sh
git clone https://github.com/suddin1256/robotics-group-drone-project.git
cd robotics-group-drone-project
python3 bootstrap.py --vision
python3 start.py --demo --no-slam --vision
```

The script detects hardware, uses an existing Pixi executable or downloads the official one locally, installs locked ROS/video packages, creates the separate V4 environment, downloads the model weights and warms up inference. Do not move/copy installed environments between computers. You can omit `--vision` to install only the ROS/dashboard baseline.

Dashboard: http://127.0.0.1:8082. The built-in moving pattern and telemetry are synthetic. It is a communication/display check, not realistic detection training data or evidence of mapping accuracy. To test actual vision, supply a suitable video:

```sh
python3 start.py --replay /absolute/path/to/video.avi --no-slam --vision
```

## Windows: first time

Windows runs the project in Ubuntu under WSL2, not native Windows Python. Enable virtualization and install WSL if needed (administrator PowerShell):

```powershell
wsl --install -d Ubuntu-24.04
```

Restart if requested, then open Ubuntu and finish creating its Linux user. Inside **Ubuntu**, install the OS prerequisites and clone into the Linux home directory for better filesystem performance:

```sh
sudo apt update
sudo apt install -y git python3 python3-venv libgl1 libglib2.0-0
git clone https://github.com/suddin1256/robotics-group-drone-project.git
cd robotics-group-drone-project
python3 bootstrap.py --vision
python3 start.py --demo --no-slam --vision
```

Open http://localhost:8082 in the Windows browser. If you already cloned from Windows, `powershell -File bootstrap.ps1 -Vision` delegates setup to Ubuntu-24.04; cloning inside Ubuntu is preferred. Neither script disables firewalls, changes execution policy or enables administrator settings automatically. Windows-on-ARM and other architectures are not yet covered.

Linux/WSL vision starts with CPU PyTorch to avoid large CUDA installs. Apple Silicon selects MPS when available; Intel Mac uses CPU and its older compatible PyTorch requirements. GPU acceleration on a particular Windows laptop requires separate verification; no automatic speed guarantee is made.

## Every update

Stop the program before updating. From a clean checkout on your tracking branch:

```sh
python3 update.py
```

This performs a fast-forward Git pull and checks a hash of dependency manifests/locks. Code-only changes do not reinstall packages. If dependencies change, it invokes bootstrap again, preserving that laptop's selected features. Local edits cause the update to stop rather than overwrite them. You can also use `git pull --ff-only` followed by `python3 bootstrap.py --check` manually.

The local `.local/setup.json` is ignored by Git. It remembers the host platform and whether vision/hardware were installed. The launcher rejects a changed dependency fingerprint and explains how to update.

## Hardware and SLAM

Direct drone access is optional:

```sh
python3 bootstrap.py --hardware
python3 start.py --no-slam
```

Only one laptop should own the direct Tello connection. Prepare models online before switching to TELLO Wi-Fi. The launcher runs model loading offline by default. Flight remains opt-in with `--enable-flight`, and is not enabled by bootstrap. Replay/demo cannot enable flight.

Optional Stella setup is available through `python3 bootstrap.py --slam`. This installs a separate locked compiler/SLAM environment, checks out pinned g2o/Stella revisions and builds locally with two jobs. It is adapted from the working Intel-Mac build recipe; the new fresh-machine builds and runtime are still unverified, particularly on Apple Silicon and WSL2. Setup reports compiler errors rather than claiming success. Keep `--no-slam` until the build passes; then use a real recording with `python3 start.py --replay /path/to/video.avi`. Shadib's verified legacy setup still uses `python3 start.py --reuse-existing` (and can run SLAM). Do not delete the original environment folders yet.

## Team access and validation

Everyone can clone the public repository. For direct pushes, the owner must invite each GitHub username through Settings → Collaborators. Otherwise members can fork and open pull requests. Follow CONTRIBUTING.md, use separate branches and review hardware/control changes.

Before claiming support on each laptop, record OS/CPU, bootstrap result, demo dashboard, ROS topic delivery, V4 model warm-up/inference and, separately, any hardware/SLAM tests. A dependency solver success is not a hardware or runtime test. Vision packages are top-level version-pinned but not fully transitively locked; model downloads follow upstream releases and are not checksum-pinned yet.

References: [RoboStack setup](https://robostack.github.io/GettingStarted.html), [WSL installation](https://learn.microsoft.com/windows/wsl/install), [WSL networking](https://learn.microsoft.com/windows/wsl/networking). Cross-computer ROS discovery and live Tello networking in WSL require separate network validation; the offline demo keeps all ROS nodes on one machine.
