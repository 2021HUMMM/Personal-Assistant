"""
Uji logika perekaman - tanpa mic sungguhan.

    python test_audio.py

Menggantikan _read_frame dengan urutan RMS buatan, jadi bisa memverifikasi
kapan record_command() berhenti dan bagaimana terdengar_suara() bekerja,
tanpa perangkat keras apa pun.
"""

from collections import deque

import numpy as np

from jarvis import audio
from jarvis import config


def _listener_dari_rms(urutan_rms):
    """Listener dengan _read_frame yang mengembalikan RMS sesuai urutan."""
    l = audio.Listener()
    l._preroll = deque(maxlen=audio._PREROLL_FRAMES)
    it = iter(urutan_rms)

    def _read():
        rms = next(it, 50)  # setelah urutan habis, anggap hening
        return np.full(audio.FRAME_SIZE, rms, dtype=np.int16)

    l._read_frame = _read
    return l


def run() -> int:
    gagal = 0

    # 1. Diam total dengan maks_tunggu_bicara -> berhenti TEPAT di batas itu,
    #    bukan menunggu penuh sampai COMMAND_MAX_SECONDS.
    l = _listener_dari_rms([50] * 200)
    hasil = l.record_command(maks_tunggu_bicara=5)
    detik = len(hasil) / config.SAMPLE_RATE
    ok = 4.7 <= detik <= 5.2
    gagal += not ok
    print(f"{'ok  ' if ok else 'GAGAL'} diam total, tunggu=5s -> berhenti di {detik:.2f}s")

    # 2. Mulai bicara SEBELUM batas tunggu habis -> lanjut merekam normal
    #    (trailing silence SILENCE_SECONDS), tidak dipotong di titik tunggu.
    urutan = [50] * 20 + [3000] * 15 + [50] * 20  # diam 1.6s, bicara 1.2s, diam
    l = _listener_dari_rms(urutan)
    hasil = l.record_command(maks_tunggu_bicara=5)
    detik = len(hasil) / config.SAMPLE_RATE
    ok = detik > 2.5
    gagal += not ok
    print(f"{'ok  ' if ok else 'GAGAL'} mulai bicara di 1.6s -> total rekaman {detik:.2f}s "
          "(tidak dipotong di batas tunggu)")

    # 3. Tanpa maks_tunggu_bicara -> perilaku lama: tunggu penuh COMMAND_MAX_SECONDS.
    l = _listener_dari_rms([50] * 200)
    hasil = l.record_command()
    detik = len(hasil) / config.SAMPLE_RATE
    ok = abs(detik - config.COMMAND_MAX_SECONDS) < 0.2
    gagal += not ok
    print(f"{'ok  ' if ok else 'GAGAL'} tanpa maks_tunggu_bicara -> {detik:.2f}s "
          f"(harus ~{config.COMMAND_MAX_SECONDS}s, perilaku lama)")

    # 4. terdengar_suara() mendeteksi ambang dengan benar, dan mengisi preroll.
    l = _listener_dari_rms([50, 50, 3000, 3000])
    deteksi = [l.terdengar_suara(config.SILENCE_THRESHOLD) for _ in range(4)]
    ok = deteksi == [False, False, True, True]
    gagal += not ok
    print(f"{'ok  ' if ok else 'GAGAL'} terdengar_suara() -> {deteksi} (harus [F,F,T,T])")

    ok = len(l._preroll) == audio._PREROLL_FRAMES
    gagal += not ok
    print(f"{'ok  ' if ok else 'GAGAL'} preroll terisi setelah terdengar_suara() "
          f"-> {len(l._preroll)}/{audio._PREROLL_FRAMES} frame")

    total = 5
    print(f"\n{total - gagal}/{total} lolos")
    return 1 if gagal else 0


if __name__ == "__main__":
    raise SystemExit(run())
