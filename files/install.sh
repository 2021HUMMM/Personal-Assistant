#!/usr/bin/env bash
# Pasang semua dependensi ke virtualenv yang sedang aktif.
#
#   python3 -m venv venv && source venv/bin/activate && ./install.sh
set -euo pipefail

if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "Aktifkan virtualenv dulu:  source venv/bin/activate" >&2
    exit 1
fi

pip install -r requirements.txt

# --no-deps melewati tflite-runtime, yang tidak punya wheel untuk Python 3.12+
# dan memang tidak kita butuhkan (kita pakai backend ONNX).
pip install --no-deps "openwakeword>=0.5.1"

echo
echo "Selesai. Lanjut:  python miccheck.py"
