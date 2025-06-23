#!/usr/bin/env bash
# bpcss.sh: Installer and launcher for BPCSS workflow toolkit
# Usage: Run this script to install/setup the toolkit and launch the Python entrypoint.

set -e

# Configuration: GitHub repo URL containing bpcss.py and related files
REPO_URL="https://github.com/yourusername/bpcss-toolkit.git"
# Directory where toolkit will be installed
TOOLKIT_DIR="$HOME/.bpcss_toolkit"
# Minimum Python version
MIN_PY_MAJOR=3
MIN_PY_MINOR=2

# Function to compare versions: returns 0 if $1 >= $2
version_ge() {
    # usage: version_ge "3.8" "3.2"
    local IFS=.
    local i ver1=($1) ver2=($2)
    # fill empty fields with zeros
    for ((i=${#ver1[@]}; i<${#ver2[@]}; i++)); do
        ver1[i]=0
    done
    for ((i=0; i<${#ver1[@]}; i++)); do
        if [[ -z ${ver2[i]} ]]; then
            # no more to compare; equal
            break
        fi
        if ((10#${ver1[i]} > 10#${ver2[i]})); then
            return 0
        elif ((10#${ver1[i]} < 10#${ver2[i]})); then
            return 1
        fi
    done
    return 0
}

# Check for python3
if ! command -v python3 &>/dev/null; then
    echo "Python3 is not installed."
    # Attempt distro-specific install if possible
    if [ -f /etc/debian_version ]; then
        read -rp "Install Python3 via apt? [Y/n]: " resp
        resp=${resp:-Y}
        if [[ $resp =~ ^[Yy]$ ]]; then
            sudo apt update && sudo apt install -y python3 python3-venv python3-pip
        else
            echo "Please install Python3 >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR} and re-run."
            exit 1
        fi
    elif [ -f /etc/redhat-release ]; then
        read -rp "Install Python3 via yum? [Y/n]: " resp
        resp=${resp:-Y}
        if [[ $resp =~ ^[Yy]$ ]]; then
            sudo yum install -y python3 python3-venv python3-pip
        else
            echo "Please install Python3 >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR} and re-run."
            exit 1
        fi
    else
        echo "Unsupported distro or cannot auto-install Python. Please install Python3 >= ${MIN_PY_MAJOR}.${MIN_PY_MINOR}."
        exit 1
    fi
fi

# Check Python version
PY_VER_FULL=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if ! version_ge "$PY_VER_FULL" "${MIN_PY_MAJOR}.${MIN_PY_MINOR}"; then
    echo "Python version $PY_VER_FULL is less than required ${MIN_PY_MAJOR}.${MIN_PY_MINOR}."
    echo "Please upgrade Python and re-run."
    exit 1
fi
echo "Detected Python $PY_VER_FULL"

# Clone or update toolkit
if [[ ! -d "$TOOLKIT_DIR" ]]; then
    echo "Creating toolkit directory at $TOOLKIT_DIR"
    mkdir -p "$TOOLKIT_DIR"
    # Clone repository
    if command -v git &>/dev/null; then
        echo "Cloning repository from $REPO_URL"
        git clone "$REPO_URL" "$TOOLKIT_DIR"
    else
        echo "git not found. Attempting to download via wget."
        if command -v wget &>/dev/null; then
            tmp_archive="/tmp/bpcss_toolkit.tar.gz"
            echo "Downloading repository archive..."
            wget -O "$tmp_archive" "${REPO_URL%".git"}/archive/refs/heads/main.tar.gz"
            echo "Extracting to $TOOLKIT_DIR"
            tar -xzf "$tmp_archive" -C "$TOOLKIT_DIR" --strip-components=1
            rm -f "$tmp_archive"
        else
            echo "Neither git nor wget available. Please install git or wget and re-run."
            exit 1
        fi
    fi
else
    echo "Toolkit directory exists. Updating..."
    if [[ -d "$TOOLKIT_DIR/.git" ]] && command -v git &>/dev/null; then
        cd "$TOOLKIT_DIR"
        git pull
        cd - >/dev/null
    else
        echo "No git repo found; skipping update."
    fi
fi

# Enter toolkit directory
cd "$TOOLKIT_DIR"

# Create or activate virtual environment
VENV_DIR="venv"
if [[ ! -d "$VENV_DIR" ]]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
# Activate venv
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

# Install required Python packages
REQUIREMENTS=(biopython pyyaml matplotlib scipy selenium requests tqdm pandas beautifulsoup4)
echo "Installing required Python packages..."
pip install --upgrade pip
for pkg in "${REQUIREMENTS[@]}"; do
    if ! pip show "$pkg" &>/dev/null; then
        pip install "$pkg"
    fi
done

# Launch main Python entrypoint
if [[ -f "bpcss.py" ]]; then
    echo "Launching BPCSS main..."
    python3 bpcss.py
else
    echo "Error: bpcss.py not found in $TOOLKIT_DIR"
fi

# Deactivate venv and exit
deactivate
echo "BPCSS session ended."
