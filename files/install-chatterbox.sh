#!/usr/bin/env bash
# Pasang Chatterbox TTS (neural, GPU) sebagai suara utama Jarvis.
#
#   ./install-chatterbox.sh
#
# Terpisah dari venv utama (venv/) karena chatterbox-tts butuh numpy<2.0,
# yang bentrok dengan numpy yang dipakai openwakeword/faster-whisper di sana.
# Butuh GPU NVIDIA dengan CUDA - dites di RTX 4070 SUPER, VRAM terpakai ~3.9GB.
#
# Total unduhan ~11GB (6.3GB venv + 5GB bobot model). Kalau di tengah jalan
# gagal, jalankan lagi - langkah yang sudah selesai dilewati otomatis oleh
# pip/huggingface_hub.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=== 1/4: membuat venv-chatterbox ==="
python3 -m venv venv-chatterbox
venv-chatterbox/bin/pip install --upgrade pip -q

echo "=== 2/4: memasang chatterbox-tts (torch + CUDA, beberapa menit) ==="
venv-chatterbox/bin/pip install chatterbox-tts -q

# chatterbox-tts bergantung ke resemble-perth, yang lewat pkg_resources -
# dan setuptools terbaru sudah tidak membundelnya lagi. Tanpa ini, muat
# model gagal dengan "ModuleNotFoundError: No module named 'pkg_resources'".
echo "=== 3/4: menambal pkg_resources (setuptools<81) ==="
venv-chatterbox/bin/pip install "setuptools<81" -q

echo "=== 4/4: mengunduh bobot model bahasa Indonesia (~5GB) ==="
mkdir -p models/chatterbox-id
venv-chatterbox/bin/python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="grandhigh/Chatterbox-TTS-Indonesian",
    local_dir="models/chatterbox-id",
    allow_patterns=["*.safetensors", "*.json", "*.txt"],
)
PY

# Chatterbox itu voice-cloning TTS - butuh referensi audio, tidak otomatis
# punya "suara bawaan". Pakai contoh resmi dari model card sebagai default.
curl -sL -o models/chatterbox-id/reference.wav \
    "https://huggingface.co/grandhigh/Chatterbox-TTS-Indonesian/resolve/main/example1.wav"

echo
echo "Selesai. Uji dengan:  python cek.py"
echo "Ganti suara referensi: taruh wav lain di models/chatterbox-id/reference.wav"
echo "                       atau JV_CHATTERBOX_REFERENCE=/path/ke/suara.wav"
