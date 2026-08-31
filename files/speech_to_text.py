"""
Speech-to-text lokal via faster-whisper. Model dimuat sekali, tetap di memori.

Dikonfigurasi untuk bahasa campur Indonesia + Inggris: model multilingual,
bahasa dikunci ke "id" (bahasa matriks), dan decoder dibiaskan dengan
initial_prompt berisi kosakata perintah kita.
"""

import numpy as np

import config

_model = None


def load():
    """Muat model di awal supaya perintah pertama tidak kena jeda kejut."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        if config.WHISPER_MODEL_SIZE.endswith(".en"):
            raise ValueError(
                f"WHISPER_MODEL_SIZE={config.WHISPER_MODEL_SIZE!r} itu model khusus "
                "bahasa Inggris dan tidak bisa memahami bahasa Indonesia. "
                "Pakai 'small', 'base', atau 'medium' tanpa akhiran '.en'."
            )
        print(f"[stt] memuat whisper '{config.WHISPER_MODEL_SIZE}'...")
        _model = WhisperModel(
            config.WHISPER_MODEL_SIZE,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )
    return _model


def transcribe(audio: np.ndarray) -> str:
    """audio: float32 mono di config.SAMPLE_RATE, rentang [-1, 1]."""
    if audio.size == 0:
        return ""
    segments, _info = load().transcribe(
        audio,
        language=config.WHISPER_LANGUAGE,
        initial_prompt=config.WHISPER_INITIAL_PROMPT,
        beam_size=1,
        vad_filter=True,
        # Cegah decoder terkunci di putaran pengulangan pada audio pendek.
        condition_on_previous_text=False,
    )
    hasil = " ".join(seg.text.strip() for seg in segments).strip()
    # Dicatat apa adanya (termasuk kalau kosong) - satu-satunya cara melacak
    # salah dengar itu dengan bukti nyata, bukan nebak. `journalctl --user -u
    # jarvis | grep stt-hasil` untuk lihat riwayatnya.
    print(f"[stt-hasil] {hasil!r}")
    return hasil
