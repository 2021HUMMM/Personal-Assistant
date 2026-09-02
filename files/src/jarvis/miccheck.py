"""
Cek mic dan cari nilai SILENCE_THRESHOLD yang pas untuk perangkatmu.

    python -m jarvis.miccheck

Butuh: pip install sounddevice numpy

Program akan mengukur level saat hening lalu saat kamu bicara, dan
menyarankan angka untuk config.SILENCE_THRESHOLD.
"""

import time

import numpy as np
import sounddevice as sd

from jarvis import config

FRAME = int(config.SAMPLE_RATE * config.FRAME_MS / 1000)


def _measure(stream, seconds, label):
    print(f"\n{label} ({seconds} detik)...")
    levels = []
    for _ in range(int(seconds * 1000 / config.FRAME_MS)):
        frame, _over = stream.read(FRAME)
        rms = float(np.sqrt(np.mean(frame.flatten().astype(np.float64) ** 2)))
        levels.append(rms)
        bar = "#" * min(60, int(rms / 40))
        print(f"  {rms:7.0f} |{bar}", end="\r", flush=True)
    print(" " * 78, end="\r")
    return np.array(levels)


def main():
    print("Perangkat input:")
    print(sd.query_devices(kind="input"))

    with sd.InputStream(samplerate=config.SAMPLE_RATE, channels=config.CHANNELS,
                        dtype="int16", blocksize=FRAME) as stream:
        input("\nTekan Enter, lalu DIAM saja...")
        quiet = _measure(stream, 3, "Mengukur derau latar")

        input("\nTekan Enter, lalu BICARA normal (misal: 'buka firefox')...")
        speech = _measure(stream, 4, "Mengukur suaramu")

    q90 = np.percentile(quiet, 90)
    s50 = np.percentile(speech, 50)
    print(f"\nHening : rata-rata {quiet.mean():6.0f}  persentil-90 {q90:6.0f}")
    print(f"Bicara : rata-rata {speech.mean():6.0f}  median      {s50:6.0f}")

    if s50 <= q90 * 1.5:
        print("\n[!] Suaramu nyaris tidak berbeda dari derau latar.")
        print("    Naikkan gain mic, dekatkan mic, atau kurangi kebisingan ruangan.")
        return

    suggested = int((q90 * 1.6 + s50 * 0.35) / 2)
    print(f"\nSetel di config.py:  SILENCE_THRESHOLD = {suggested}")
    print(f"(sekarang: {config.SILENCE_THRESHOLD})")


if __name__ == "__main__":
    main()
