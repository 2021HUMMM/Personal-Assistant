"""
Speech-to-text lokal via faster-whisper. Model dimuat sekali, tetap di memori.

Dikonfigurasi untuk bahasa campur Indonesia + Inggris: model multilingual,
bahasa dikunci ke "id" (bahasa matriks), dan decoder dibiaskan dengan
initial_prompt berisi kosakata perintah kita.
"""

import ctypes
import glob
import os

import numpy as np

from jarvis import config

_model = None


def _preload_lib_cuda():
    """
    ctranslate2 (dipakai faster-whisper) butuh libcublas/libcudnn tapi TIDAK
    membawanya sendiri - beda dari torch (dipakai Chatterbox) yang otomatis
    membawa itu semua - dan sistem ini juga tidak punya cuBLAS di jalur
    linker bawaan. Kejadian nyata: transkripsi audio DIAM/nyaris-diam
    "sukses" (VAD men-skip GPU sama sekali di kasus itu), tapi audio yang
    beneran ada suara memicu forward pass GPU dan meledak "libcublas.so.12
    is not found".

    Set LD_LIBRARY_PATH dari dalam Python TIDAK CUKUP - sudah dicoba dan
    terbukti tidak berpengaruh, karena glibc mengunci daftar jalur pencarian
    dlopen-nya di awal proses, bukan baca ulang os.environ tiap dlopen.
    Yang benar-benar jalan: muat file .so-nya LANGSUNG lewat ctypes SEBELUM
    ctranslate2 sempat dlopen sendiri - begitu sebuah .so sudah ada di
    memori proses, dlopen(nama_yang_sama) berikutnya oleh library lain
    (ctranslate2) otomatis nemu yang sudah dimuat itu, apa pun jalur
    pencariannya.

    Paket pip nvidia-cublas-cu12 & nvidia-cudnn-cu12 (./venv/bin/pip
    install) menaruh .so-nya di dalam venv sendiri.
    """
    if config.WHISPER_DEVICE != "cuda":
        return
    base = os.path.join(config._JARVIS_DIR, "venv", "lib")
    # Urutan penting: cuda_nvrtc dan cublas duluan, cudnn belakangan (cudnn
    # butuh simbol dari cublas yang sudah residen).
    for sub in ("cuda_nvrtc", "cublas", "cudnn"):
        for so in sorted(glob.glob(os.path.join(base, "python3.*", "site-packages",
                                                  "nvidia", sub, "lib", "*.so*"))):
            try:
                ctypes.CDLL(so, mode=ctypes.RTLD_GLOBAL)
            except OSError as e:
                print(f"[stt] peringatan: gagal preload {so}: {e}")


def load():
    """Muat model di awal supaya perintah pertama tidak kena jeda kejut."""
    global _model
    if _model is None:
        _preload_lib_cuda()
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
