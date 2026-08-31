"""
Input audio: deteksi wake word + perekaman perintah.

Satu InputStream dibuka sekali dan dipakai seumur hidup proses. Ini penting:
kalau stream ditutup lalu dibuka lagi di antara wake word dan perekaman, ada
jeda ~200ms yang memakan suku kata pertama perintah - penyebab nomor satu
"kok dia salah dengar terus".
"""

from collections import deque

import numpy as np
import sounddevice as sd

import config

FRAME_SIZE = int(config.SAMPLE_RATE * config.FRAME_MS / 1000)
_PREROLL_FRAMES = max(1, int(config.PREROLL_MS / config.FRAME_MS))


class Listener:
    def __init__(self):
        self._stream = None
        self._oww = None
        # Menyimpan beberapa frame terakhir supaya awal perintah tidak hilang.
        self._preroll = deque(maxlen=_PREROLL_FRAMES)

    # --- lifecycle ---

    def start(self):
        from openwakeword.model import Model

        # Backend ONNX secara eksplisit. Alternatifnya (tflite) tidak punya
        # wheel untuk Python 3.12 ke atas. openWakeWord sebenarnya bisa jatuh
        # sendiri ke ONNX, tapi menyebutkannya bikin perilaku deterministik
        # dan menghilangkan peringatan saat start.
        self._oww = Model(
            wakeword_models=[config.WAKE_WORD_MODEL],
            inference_framework=config.WAKE_WORD_BACKEND,
        )
        self._stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            dtype="int16",
            blocksize=FRAME_SIZE,
        )
        self._stream.start()

    def close(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_exc):
        self.close()

    # --- internals ---

    def _read_frame(self) -> np.ndarray:
        frame, _overflowed = self._stream.read(FRAME_SIZE)
        return frame.flatten()

    def drain(self):
        """
        Buang audio yang menumpuk di buffer selagi kita sibuk (terutama selagi
        TTS bicara). Tanpa ini asisten mendengar suaranya sendiri dan langsung
        salah trigger di putaran berikutnya.
        """
        while self._stream.read_available >= FRAME_SIZE:
            self._read_frame()
        self._preroll.clear()

    # --- public API ---

    def wait_for_wake_word(self):
        """Blok sampai wake word terdengar."""
        print(f"[wake] menunggu '{config.WAKE_WORD_MODEL}'...")
        self._oww.reset()
        while True:
            frame = self._read_frame()
            self._preroll.append(frame)
            score = self._oww.predict(frame).get(config.WAKE_WORD_MODEL, 0.0)
            if score > config.WAKE_WORD_THRESHOLD:
                print(f"[wake] terdeteksi ({score:.2f})")
                # Reset supaya buffer internal yang masih "panas" tidak
                # langsung men-trigger ulang di aktivasi berikutnya.
                self._oww.reset()
                return

    def record_command(self, maks_tunggu_bicara=None) -> np.ndarray:
        """
        Rekam sampai pengguna berhenti bicara, sampai batas waktu total, ATAU -
        kalau `maks_tunggu_bicara` diberi - sampai sekian detik berlalu tanpa
        pengguna MULAI bicara sama sekali. Dua batas yang beda:

          - maks_tunggu_bicara: berapa lama menunggu kamu MULAI ngomong.
            Dipakai mode percakapan supaya mic tidak "aktif mendengarkan"
            tanpa batas kalau kamu diam - default None berarti sama dengan
            COMMAND_MAX_SECONDS (perilaku lama).
          - COMMAND_MAX_SECONDS: batas total SEKALI kamu sudah mulai bicara,
            supaya tidak merekam selamanya kalau kamu terus ngomong.
        """
        print("[rec] mendengarkan perintah...")
        frames = list(self._preroll)
        self._preroll.clear()

        silence_needed = int(config.SILENCE_SECONDS * 1000 / config.FRAME_MS)
        max_frames = int(config.COMMAND_MAX_SECONDS * 1000 / config.FRAME_MS)
        tunggu_frames = min(
            max_frames,
            int(maks_tunggu_bicara * 1000 / config.FRAME_MS)
            if maks_tunggu_bicara is not None else max_frames,
        )
        consecutive_silence = 0
        spoke = False

        for i in range(max_frames):
            frame = self._read_frame()
            frames.append(frame)

            if _rms(frame) < config.SILENCE_THRESHOLD:
                consecutive_silence += 1
                if spoke and consecutive_silence >= silence_needed:
                    break
                if not spoke and i + 1 >= tunggu_frames:
                    break
            else:
                spoke = True
                consecutive_silence = 0

        return _to_float32(frames)

    def terdengar_suara(self, ambang) -> bool:
        """
        Baca satu frame (~80ms) dan bilang apakah RMS-nya melewati `ambang`.
        Dipakai text_to_speech untuk mendeteksi barge-in selagi Jarvis bicara.

        Frame yang dibaca ikut disimpan ke preroll - kalau ini memang awal
        ucapan pengguna yang memotong, rekaman berikutnya (record_command)
        tidak kehilangan suku kata pertamanya.
        """
        frame = self._read_frame()
        self._preroll.append(frame)
        return _rms(frame) >= ambang

    def record_fixed(self, seconds: float) -> np.ndarray:
        """Rekam selama durasi tetap. Dipakai untuk jendela konfirmasi."""
        self.drain()
        frames = [self._read_frame() for _ in range(int(seconds * 1000 / config.FRAME_MS))]
        return _to_float32(frames)


def _rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(frame.astype(np.float64) ** 2)))


def _to_float32(frames) -> np.ndarray:
    if not frames:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(frames).astype(np.float32) / 32768.0
