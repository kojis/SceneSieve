#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
echo 'SceneSieve 3.20 preview installer'
echo 'Installs required tools and a private Python environment; downloads may be large.'
echo 'System packages may request your administrator password.'
if [[ $(id -u) == 0 ]]; then echo 'Run as your normal desktop user, not root.'; exit 1; fi
if [[ $(uname -s) == Darwin ]]; then
    if ! command -v brew >/dev/null; then
        echo 'Installing Homebrew from its official installer.'
        curl --fail --location --proto '=https' https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o brew-install.sh
        /bin/bash brew-install.sh
    fi
    brew install python@3.12 ffmpeg mpv ollama
    PYTHON="$(brew --prefix python@3.12)/bin/python3.12"
elif [[ $(uname -s) == Linux ]]; then
    if ! command -v apt-get >/dev/null; then
        echo 'This installer currently supports Ubuntu/Debian desktops with apt.'; exit 1
    fi
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv ffmpeg mpv espeak-ng curl zstd libegl1 libopengl0 libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 xwayland
    PYTHON=python3
else
    echo 'Unsupported operating system.'; exit 1
fi
"$PYTHON" install.py "$@"
