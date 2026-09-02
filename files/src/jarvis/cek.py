"""
Periksa semua yang dibutuhkan Jarvis sebelum dijalankan.

    python -m jarvis.cek

Menandai apa yang siap, apa yang kurang, dan apa yang perlu disetel.
"""

import os
import shutil
import subprocess
import sys

from jarvis import config

OK, WARN, BAD = "  ok  ", " perlu", " KURANG"
_gagal = 0
_warn = 0


def lapor(status, nama, detail=""):
    global _gagal, _warn
    if status == BAD:
        _gagal += 1
    elif status == WARN:
        _warn += 1
    print(f"[{status}] {nama}" + (f"  — {detail}" if detail else ""))


def cek_paket():
    print("\n--- Paket Python ---")
    for modul, nama in [("sounddevice", "sounddevice"), ("numpy", "numpy"),
                        ("openwakeword", "openwakeword"),
                        ("faster_whisper", "faster-whisper"), ("piper", "piper-tts")]:
        try:
            __import__(modul)
            lapor(OK, nama)
        except ImportError:
            lapor(BAD, nama, "jalankan ./scripts/install.sh")


def cek_audio():
    print("\n--- Audio ---")
    try:
        import sounddevice as sd
        dev = sd.query_devices(kind="input")
        lapor(OK, "mikrofon", dev["name"])
    except Exception as e:
        lapor(BAD, "mikrofon", str(e)[:60])

    lapor(OK if shutil.which("aplay") else BAD, "aplay (pemutar suara)")

    if os.path.exists(config.PIPER_MODEL_PATH):
        lapor(OK, "suara Piper (fallback)", os.path.basename(config.PIPER_MODEL_PATH))
    elif shutil.which("espeak"):
        lapor(WARN, "suara", "pakai espeak (robotik) — lihat README bagian 3")
    else:
        lapor(BAD, "suara", "tidak ada piper maupun espeak")

    if not config.CHATTERBOX_ENABLED:
        lapor(WARN, "suara Chatterbox (utama)", "dimatikan (JV_CHATTERBOX=0)")
    elif not os.path.exists(config.CHATTERBOX_PYTHON):
        lapor(WARN, "suara Chatterbox (utama)",
              "belum terpasang — ./scripts/install-chatterbox.sh, jatuh ke Piper untuk sekarang")
    elif not os.path.isdir(config.CHATTERBOX_MODEL_DIR):
        lapor(WARN, "suara Chatterbox (utama)",
              "venv ada tapi model belum diunduh — ./scripts/install-chatterbox.sh")
    else:
        try:
            subprocess.run(["nvidia-smi"], capture_output=True, timeout=5, check=True)
            lapor(OK, "suara Chatterbox (utama)", "terpasang, GPU terdeteksi")
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            lapor(WARN, "suara Chatterbox (utama)",
                  "terpasang tapi GPU NVIDIA tidak terdeteksi — akan jatuh ke Piper")

    if not config.SUARA_ENABLED:
        lapor(WARN, "efek suara", "dimatikan (JV_SUARA=0)")
    else:
        d = os.path.expanduser(config.SUARA_DIR)
        ada = [n for n in ("bangun", "rekam", "tunggu", "jeda", "pamit")
               if os.path.exists(os.path.join(d, f"{n}.wav"))]
        if len(ada) == 5:
            lapor(OK, "efek suara", f"5 bunyi siap di {config.SUARA_DIR}")
        else:
            lapor(WARN, "efek suara",
                  f"{len(ada)}/5 file ada — sisanya dibangkitkan saat Jarvis start")


def cek_isolasi_proses():
    print("\n--- Isolasi aplikasi yang dibuka ---")
    if shutil.which("systemd-run"):
        lapor(OK, "systemd-run", "aplikasi yang dibuka lewat suara TIDAK ikut mati "
                                 "kalau Jarvis di-restart/di-stop")
    else:
        lapor(WARN, "systemd-run", "tidak ada - aplikasi yang dibuka bisa ikut mati "
                                   "kalau Jarvis restart. Jarang terjadi di sistem "
                                   "bersystemd, tapi cek `which systemd-run`")


def cek_aplikasi():
    print("\n--- Penemuan aplikasi ---")
    import time
    from jarvis import aplikasi
    t0 = time.time()
    n_desktop, n_steam = aplikasi.jumlah_terindeks()
    detik = time.time() - t0
    lapor(OK, "aplikasi desktop (.desktop)", f"{n_desktop} terindeks ({detik*1000:.0f}ms)")
    if n_steam:
        lapor(OK, "game Steam", f"{n_steam} terindeks lewat libraryfolders.vdf")
    else:
        lapor(WARN, "game Steam", "0 ditemukan — Steam belum terpasang, atau belum ada game")


def cek_model():
    print("\n--- Model ---")
    if config.WHISPER_MODEL_SIZE.endswith(".en"):
        lapor(BAD, "whisper", f"{config.WHISPER_MODEL_SIZE} tidak bisa bahasa Indonesia")
    else:
        lapor(OK, "whisper", f"{config.WHISPER_MODEL_SIZE} di {config.WHISPER_DEVICE}")
        if config.WHISPER_DEVICE == "cpu":
            try:
                subprocess.run(["nvidia-smi"], capture_output=True, timeout=5)
                lapor(WARN, "whisper GPU", "ada GPU tapi masih pakai CPU (~0,75 detik terbuang)")
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        elif config.WHISPER_DEVICE == "cuda":
            # ctranslate2 (faster-whisper) butuh libcublas/libcudnn sendiri,
            # tidak dibawa otomatis kayak torch. Kejadian nyata: model
            # kelihatan "berhasil" dimuat (bobotnya kepindah ke GPU), tapi
            # baru meledak "libcublas.so.12 is not found" pas transkripsi
            # audio yang beneran ada suara (audio nyaris hening lolos dari
            # cek ini karena VAD men-skip forward pass GPU-nya sama sekali).
            import glob
            base = os.path.join(config._JARVIS_DIR, "venv", "lib")
            ada_cublas = glob.glob(os.path.join(base, "python3.*", "site-packages",
                                                  "nvidia", "cublas", "lib", "libcublas.so*"))
            if ada_cublas:
                lapor(OK, "whisper cuBLAS", "paket nvidia-cublas-cu12 terpasang di venv")
            else:
                lapor(BAD, "whisper cuBLAS",
                      "belum ada - transkripsi GPU akan CRASH pas ada suara beneran "
                      "(bukan cuma diam). Jalankan: "
                      "./venv/bin/pip install nvidia-cublas-cu12 nvidia-cudnn-cu12")
    lapor(OK, "wake word", f"{config.WAKE_WORD_MODEL} via {config.WAKE_WORD_BACKEND}")


def cek_otak():
    print("\n--- Otak LLM ---")
    if config.LLM_PROVIDER == "claudecode":
        if shutil.which("claude"):
            lapor(OK, "claude CLI", f"model: {config.CLAUDECODE_MODEL}")
        else:
            lapor(WARN, "claude CLI", "belum terpasang — Jarvis tetap jalan tanpa LLM")
        if os.access(config.JARVIS_DO_PATH, os.X_OK):
            lapor(OK, "jarvis-do", "bisa dieksekusi")
        else:
            lapor(BAD, "jarvis-do", f"tidak executable: chmod +x {config.JARVIS_DO_PATH}")
    elif config.LLM_PROVIDER == "gemini":
        if config.GEMINI_API_KEY:
            lapor(OK, "GEMINI_API_KEY", f"model: {config.GEMINI_MODEL}")
        else:
            lapor(WARN, "GEMINI_API_KEY", "belum diset — Jarvis tetap jalan tanpa LLM")
    else:
        lapor(BAD, "LLM_PROVIDER", f"{config.LLM_PROVIDER!r} tidak dikenal")


def cek_layanan():
    print("\n--- Layanan otomatis ---")
    try:
        aktif = subprocess.run(["systemctl", "--user", "is-active", "jarvis"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
        nyala = subprocess.run(["systemctl", "--user", "is-enabled", "jarvis"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        lapor(WARN, "systemd", "tidak tersedia")
        return

    if nyala == "enabled":
        lapor(OK, "nyala saat login", f"status sekarang: {aktif}")
        if aktif == "active":
            lapor(OK, "instance ganda",
                  "dicegah otomatis (file lock) - aman coba `python -m jarvis.main` manual, "
                  "akan ditolak cepat kalau service masih hidup")
    else:
        lapor(WARN, "nyala saat login", "belum dipasang — ./scripts/pasang-layanan.sh")


def cek_riwayat():
    print("\n--- Riwayat percakapan ---")
    if not config.RIWAYAT_ENABLED:
        lapor(WARN, "pencatatan", "dimatikan (JV_RIWAYAT=0)")
        return
    d = config.RIWAYAT_DIR
    if os.path.isdir(d):
        n = len([f for f in os.listdir(d) if f.endswith(".md")])
        lapor(OK, "pencatatan", f"{n} percakapan tersimpan di {os.path.basename(d)}/")
    else:
        lapor(OK, "pencatatan", f"aktif — folder {os.path.basename(d)}/ dibuat saat "
                                "percakapan pertama selesai")


def cek_gui():
    print("\n--- Antarmuka (jarvis_gui.py) ---")
    try:
        hasil = subprocess.run(
            ["python3", "-c", "import gi; gi.require_version('Gtk','3.0'); "
             "from gi.repository import Gtk"],
            capture_output=True, timeout=8)
        if hasil.returncode == 0:
            lapor(OK, "GTK (PyGObject)", "tersedia di python3 sistem")
        else:
            lapor(WARN, "GTK (PyGObject)", "tidak ada — "
                  "sudo apt install python3-gi gir1.2-gtk-3.0")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        lapor(WARN, "GTK (PyGObject)", str(e)[:60])

    autostart = os.path.expanduser("~/.config/autostart/jarvis-gui.desktop")
    if os.path.exists(autostart):
        lapor(OK, "auto-nyala saat login", "terpasang")
    else:
        lapor(WARN, "auto-nyala saat login", "belum dipasang — ./scripts/pasang-gui.sh")


def cek_setelan():
    print("\n--- Setelan yang perlu disesuaikan ---")
    if config.SILENCE_THRESHOLD == 500:
        lapor(WARN, "SILENCE_THRESHOLD",
              "masih nilai bawaan — jalankan `python -m jarvis.miccheck` dulu")
    else:
        lapor(OK, "SILENCE_THRESHOLD", str(config.SILENCE_THRESHOLD))

    # Jalur utama interupsi itu tombol fisik (SIGUSR1), selalu aktif.
    # INTERRUPT_ENABLED cuma mengatur jalur SUARA, yang sengaja mati default.
    lapor(OK, "interupsi tombol", "tekan Home — selalu aktif, lihat README")
    if config.INTERRUPT_ENABLED:
        lapor(WARN, "interupsi via suara",
              f"NYALA (ambang {config.INTERRUPT_THRESHOLD}) — tanpa AEC ini sering "
              "salah trigger ke suara Jarvis sendiri, kecuali kamu pakai headset")


def main():
    print(f"Jarvis — pemeriksaan\npython {sys.version.split()[0]}")
    cek_paket()
    cek_audio()
    cek_isolasi_proses()
    cek_aplikasi()
    cek_model()
    cek_otak()
    cek_layanan()
    cek_riwayat()
    cek_gui()
    cek_setelan()

    print()
    if _gagal:
        print(f"{_gagal} hal KURANG — perbaiki dulu sebelum `python -m jarvis.main`")
        return 1
    if _warn:
        print(f"Siap jalan, tapi {_warn} hal sebaiknya dibereskan dulu.")
    else:
        print("Semua siap. Jalankan: python -m jarvis.main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
