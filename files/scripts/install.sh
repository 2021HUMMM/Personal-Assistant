#!/usr/bin/env bash
# Pasang semua dependensi ke virtualenv yang sedang aktif.
#
#   cd files && python3 -m venv venv && source venv/bin/activate && ./scripts/install.sh
set -euo pipefail

if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "Aktifkan virtualenv dulu:  source venv/bin/activate" >&2
    exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

pip install -r requirements.txt

# --no-deps melewati tflite-runtime, yang tidak punya wheel untuk Python 3.12+
# dan memang tidak kita butuhkan (kita pakai backend ONNX).
pip install --no-deps "openwakeword>=0.5.1"

# Daftarkan paket `jarvis` sendiri (src/jarvis/) - TANPA resolve dependensi
# (sudah dipasang di atas, --no-deps di sini murni supaya modulnya bisa
# diimpor dari mana pun venv ini aktif, "from jarvis import config" dkk.).
pip install -e . --no-deps

echo
echo "Selesai. Lanjut:  venv/bin/python -m jarvis.miccheck"
