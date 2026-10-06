"""Produce independently runnable macOS and Linux self-extracting installers."""
import base64,hashlib,io,tarfile,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'dist';out.mkdir(exist_ok=True);source=root/'src'
requirements='''PySide6==6.10.2
numpy==2.2.6
opencv-python-headless==4.12.0.88
pysubs2==1.8.0
faster-whisper==1.2.1
'''
readme='''SceneSieve 3.20 - macOS / Linux preview installers

These are executable, self-extracting shell installers with the application
source included. They are not signed native binaries or offline bundles.
Internet is required for dependencies and first-use AI models.

macOS: unzip SceneSieve-macOS-v3.20.zip and open Install-SceneSieve.command.
If executable permissions were lost, run in Terminal:
  bash /path/to/Install-SceneSieve.command
Installs Homebrew if missing, then Python 3.12, FFmpeg, mpv and Ollama.
Creates ~/Applications/SceneSieve.app. Homebrew may request administrator
approval and Command Line Tools. Current Homebrew supports Apple Silicon
macOS 15 or newer; Intel/older macOS availability is best effort.
This app is unsigned and not notarized. It may require Open Anyway in
System Settings > Privacy & Security after you attempt to open it.
macOS preview is a separate mpv window, controlled by the editor. In-window
video embedding requires a future libmpv rendering backend.

Linux: Ubuntu 22.04/24.04 or Debian 12/13 desktop, x86_64 or ARM64.
Run: bash SceneSieve-Linux-v3.20.run
Uses apt with sudo for Python, FFmpeg, mpv, eSpeak NG, XWayland and Qt libraries.
Downloads Ollama into the user's app assets if it is not already installed.
The application menu receives a SceneSieve entry. Qt uses X11/XWayland for
embedded playback; a graphical desktop and working DISPLAY are required.
Other Linux distributions are not handled by this installer.

App data and private Python environments:
  macOS: ~/Library/Application Support/SceneSieve
  Linux: ${XDG_DATA_HOME:-~/.local/share}/SceneSieve
System tools are managed by Homebrew/apt; models remain under app storage.
Speech replacement uses macOS system voices or Linux eSpeak NG.
Re-run the installer to repair missing Python dependencies. Existing settings,
models and media are preserved. --install-only skips launching after setup.
--check verifies the embedded archive without installing or downloading.

Verification: Python compilation and Windows regression tests; installer
shell syntax and payload integrity checked using Ubuntu WSL. Native macOS,
Linux desktop playback, GPU inference and new speech backends are UNVERIFIED.

Dependency sources:
https://docs.brew.sh/Installation
https://docs.ollama.com/linux
https://mpv.io/manual/stable/
Python packages: https://pypi.org/
'''
buffer=io.BytesIO()
with tarfile.open(fileobj=buffer,mode='w:gz') as archive:
    def add(name,data,mode=0o644):
        info=tarfile.TarInfo(name);info.size=len(data);info.mode=mode;archive.addfile(info,io.BytesIO(data))
    for p in sorted(source.glob('*.py')):add('src/'+p.name,p.read_bytes())
    add('src/app.ico',(source/'app.ico').read_bytes())
    add('setup.sh',(root/'packaging/unix_setup.sh').read_text(encoding='utf-8').encode(),0o755)
    add('install.py',(root/'packaging/unix_install.py').read_bytes())
    add('requirements.txt',requirements.encode())
    add('README.txt',readme.encode())
payload=buffer.getvalue();digest=hashlib.sha256(payload).hexdigest()
for platform,filename in [('Darwin','Install-SceneSieve.command'),('Linux','SceneSieve-Linux-v3.20.run')]:
    header='''#!/bin/bash
set -euo pipefail
if [[ "${1:-}" != --check && $(uname -s) != PLATFORM ]]; then echo 'Wrong operating system for this installer.'; exit 1; fi
temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/scenesieve.XXXXXXXX")
trap 'rm -rf -- "$temp_dir"' EXIT
line=$(awk '/^__SCENESIEVE_PAYLOAD__$/{print NR+1; exit}' "$0")
if [[ $(uname -s) == Darwin ]]; then
    tail -n +"$line" "$0" | base64 -D > "$temp_dir/app.tar.gz"
    actual=$(shasum -a 256 "$temp_dir/app.tar.gz" | awk '{print $1}')
else
    tail -n +"$line" "$0" | base64 -d > "$temp_dir/app.tar.gz"
    actual=$(sha256sum "$temp_dir/app.tar.gz" | awk '{print $1}')
fi
if [[ "$actual" != DIGEST ]]; then echo 'Installer payload is damaged.'; exit 1; fi
if [[ "${1:-}" == --check ]]; then echo 'Payload verified.'; exit 0; fi
tar -xzf "$temp_dir/app.tar.gz" -C "$temp_dir"
if ! bash "$temp_dir/setup.sh" "$@"; then
    echo 'Setup failed. Review the messages above and rerun the installer to retry.'
    if [[ -t 0 ]]; then read -r -p 'Press Enter to close.'; fi
    exit 1
fi
exit 0
__SCENESIEVE_PAYLOAD__
'''.replace('PLATFORM',platform).replace('DIGEST',digest)
    target=out/filename;target.write_bytes(header.encode()+base64.encodebytes(payload));target.chmod(0o755)
    if platform=='Darwin':
        with zipfile.ZipFile(out/'SceneSieve-macOS-v3.20.zip','w',zipfile.ZIP_DEFLATED) as z:
            info=zipfile.ZipInfo(filename);info.create_system=3;info.external_attr=0o100755<<16;z.writestr(info,target.read_bytes());z.writestr('README.txt',readme)
    (out/(filename+'.sha256')).write_text(hashlib.sha256(target.read_bytes()).hexdigest()+'  '+filename+'\n')
(out/'SceneSieve-macOS-Linux-v3.20-Readme.txt').write_text(readme,encoding='utf-8')
with zipfile.ZipFile(out/'SceneSieve-macOS-Linux-v3.20-Source.zip','w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(source.glob('*.py')):z.write(p,'src/'+p.name)
    z.write(source/'app.ico','src/app.ico')
    z.write(root/'packaging/unix_setup.sh','setup.sh');z.write(root/'packaging/unix_install.py','install.py')
    z.writestr('requirements.txt',requirements);z.writestr('README.txt',readme)
print('Created macOS and Linux preview installers and source package.')
