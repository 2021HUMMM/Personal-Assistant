"""
Server sintesis Chatterbox - dijalankan sebagai subprocess terpisah lewat
venv-chatterbox (chatterbox-tts butuh numpy<2.0, bentrok dengan venv utama).

Dijalankan oleh text_to_speech.py, TIDAK dijalankan langsung oleh pengguna.

Protokol lewat stdin/stdout, satu JSON per baris:
  stdin  {"text": "..."}                    -> minta sintesis
  stdout {"type": "ready"}                   -> model siap (sekali, di awal)
  stdout {"type": "result", "wav_path": ".."} -> berhasil
  stdout {"type": "error", "message": ".."}   -> gagal, proses tetap hidup

Model dimuat SEKALI dan tetap di GPU selama proses ini hidup. Panggilan
generate() pertama sekaligus dipakai untuk menyiapkan voice conditioning dari
reference.wav (~8 detik) - dilakukan di sini, saat startup, supaya permintaan
sungguhan dari pengguna tidak pernah kena jeda itu.
"""

import json
import os
import signal
import sys
import tempfile

# Lapisan pengaman kedua. Tombol interupsi fisik Jarvis mengirim SIGUSR1 ke
# proses UTAMA lewat `systemctl kill --kill-whom=main`. Kalau suatu saat ada
# yang mengirim tanpa --kill-whom (default systemctl kill: seluruh cgroup),
# proses ini TIDAK BOLEH ikut mati - default OS untuk SIGUSR1 tanpa handler
# adalah TERMINATE, dan proses ini butuh ~9-11 detik untuk nyala ulang.
signal.signal(signal.SIGUSR1, signal.SIG_IGN)

# Beberapa library yang dipakai chatterbox (torch, transformers, dst.) print()
# langsung ke stdout - misalnya "loaded PerthNet (Implicit) at step 250,000".
# Itu mengotori stdout yang kita pakai sebagai jalur protokol JSON. Simpan
# duplikat stdout asli SEBELUM mengimpor library apa pun, alihkan stdout biasa
# ke /dev/null, dan tulis protokol lewat duplikat yang disimpan.
_protokol = os.fdopen(os.dup(1), "w", buffering=1)
os.dup2(os.open(os.devnull, os.O_WRONLY), 1)

MODEL_DIR = os.environ.get("JV_CHATTERBOX_MODEL_DIR",
                           os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "models", "chatterbox-id"))
REFERENCE_WAV = os.environ.get("JV_CHATTERBOX_REFERENCE",
                               os.path.join(MODEL_DIR, "reference.wav"))
DEVICE = os.environ.get("JV_CHATTERBOX_DEVICE", "cuda")


def _kirim(obj):
    _protokol.write(json.dumps(obj) + "\n")
    _protokol.flush()


def main():
    import torch
    import torchaudio
    from chatterbox.tts import ChatterboxTTS

    model = ChatterboxTTS.from_local(MODEL_DIR, device=DEVICE)

    # Panggilan pemanasan: menyiapkan voice conditioning dari reference.wav
    # sekali di sini. Tanpa ini, permintaan PERTAMA dari pengguna yang kena
    # jeda ~8 detik, bukan cuma proses ini yang kena jeda startup.
    model.generate("Pemanasan.", audio_prompt_path=REFERENCE_WAV)
    _kirim({"type": "ready", "vram_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2)
            if DEVICE == "cuda" else None})

    for baris in sys.stdin:
        baris = baris.strip()
        if not baris:
            continue
        try:
            permintaan = json.loads(baris)
            teks = permintaan["text"]
        except (json.JSONDecodeError, KeyError) as e:
            _kirim({"type": "error", "message": f"permintaan tidak valid: {e}"})
            continue

        try:
            wav = model.generate(teks)
            path = tempfile.mktemp(suffix=".wav", prefix="chatterbox_")
            torchaudio.save(path, wav, model.sr)
            _kirim({"type": "result", "wav_path": path})
        except Exception as e:
            _kirim({"type": "error", "message": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
