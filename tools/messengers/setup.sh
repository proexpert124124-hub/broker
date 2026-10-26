#!/usr/bin/env bash
set -euo pipefail
kit_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 -m venv "$kit_dir/.venv"
"$kit_dir/.venv/bin/python" -m pip install -r "$kit_dir/requirements.txt"
"$kit_dir/.venv/bin/python" "$kit_dir/config.py"
