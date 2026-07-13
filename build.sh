#!/usr/bin/env bash
# Build the standalone lmsload executable and install it to ~/.local/bin.
set -euo pipefail
cd "$(dirname "$0")"

uvx --with pyyaml pyinstaller --onefile --name lmsload lmsload.py

install -D dist/lmsload "$HOME/.local/bin/lmsload"
echo "Installed $(du -h dist/lmsload | cut -f1) binary to ~/.local/bin/lmsload"
