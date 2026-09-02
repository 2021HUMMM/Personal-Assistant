"""
Text-to-speech lokal, tiga lapis:

  1. Chatterbox (neural, GPU) - jauh lebih natural, dipilih setelah A/B
     langsung dengan Piper. Jalan di subprocess terpisah lewat
     venv-chatterbox (chatterbox-tts butuh numpy<2.0, bentrok dengan venv
     utama), dibiarkan HIDUP dan dipakai ulang - proses baru = model dimuat
     ulang ke GPU dan voice conditioning disiapkan lagi, ~11 detik.
  2. Piper (neural, CPU) - fallback kalau Chatterbox gagal/nonaktif/GPU sibuk.
  3. espeak - jaring pengaman terakhir kalau Piper juga tidak ada.

Mendukung interupsi (barge-in): kalau `listener` diberikan ke speak(), mic
dipantau tiap ~80ms selagi audio diputar - begitu terdengar suara di atas
INTERRUPT_THRESHOLD, pemutaran langsung dihentikan dan speak() kembali True.

PENTING - tidak ada acoustic echo cancellation di sini. Deteksinya cuma
membandingkan RMS mic terhadap satu ambang tetap. Di setup speaker & mic yang
berdekatan/keras, suara Jarvis sendiri bisa memicu ini secara salah - itu
sebabnya INTERRUPT_THRESHOLD dibuat jauh lebih tinggi dari SILENCE_THRESHOLD.
Kalau masih sering salah trigger, pakai headset - mic-nya tidak akan pernah
dengar suara Jarvis sama sekali, jadi masalah ini hilang total.
"""

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import wave

from jarvis import config

_voice = None
_syn_config = None

# --- state Chatterbox (subprocess persisten) ---
_cb_proc = None
_cb_antrian = None
_cb_siap = False
_cb_gagal_permanen = False


def load():
    """
    Muat model Piper di awal supaya ucapan pertama tidak kena jeda.
    Kembalikan False kalau Piper tidak tersedia (nanti jatuh ke espeak).
    """
    global _voice, _syn_config
    if _voice is not None:
        return True
    if not os.path.exists(config.PIPER_MODEL_PATH):
        return False
    try:
        from piper import PiperVoice, SynthesisConfig
    except ImportError:
        return False

    print("[tts] memuat suara Piper (fallback)...")
    _voice = PiperVoice.load(config.PIPER_MODEL_PATH)
    _syn_config = SynthesisConfig(
        length_scale=config.PIPER_LENGTH_SCALE,
        noise_scale=config.PIPER_NOISE_SCALE,
        noise_w_scale=config.PIPER_NOISE_W_SCALE,
    )
    return True


def load_chatterbox():
    """
    Nyalakan subprocess Chatterbox dan tunggu sampai siap. Dipanggil sekali
    di awal (main.py) supaya ucapan pertama tidak kena jeda ~11 detik.
    Kembalikan False kalau gagal - Chatterbox dinonaktifkan PERMANEN untuk
    sisa umur proses (bukan dicoba ulang tiap ucapan, yang masing-masing
    kena jeda startup ~11 detik kalau memang rusak).
    """
    if not config.CHATTERBOX_ENABLED:
        return False
    return _cb_pastikan_siap()


def _cb_pastikan_siap() -> bool:
    global _cb_proc, _cb_antrian, _cb_siap, _cb_gagal_permanen

    if _cb_gagal_permanen:
        return False
    if _cb_proc is not None and _cb_proc.poll() is None and _cb_siap:
        return True

    if not os.path.exists(config.CHATTERBOX_PYTHON):
        print(f"[tts] chatterbox: venv tidak ada di {config.CHATTERBOX_PYTHON} - "
              "pakai piper. Jalankan install-chatterbox.sh kalau mau mencobanya.")
        _cb_gagal_permanen = True
        return False
    if not os.path.isdir(config.CHATTERBOX_MODEL_DIR):
        print(f"[tts] chatterbox: model tidak ada di {config.CHATTERBOX_MODEL_DIR} - pakai piper.")
        _cb_gagal_permanen = True
        return False

    print("[tts] menyalakan chatterbox (GPU, muat model + siapkan suara)...")
    t0 = time.time()
    direktori = os.path.dirname(os.path.abspath(__file__))
    # chatterbox_server.py punya fallback path MODEL_DIR relatif ke lokasinya
    # SENDIRI (dipakai kalau JV_CHATTERBOX_MODEL_DIR tidak diset) - itu cuma
    # kebetulan benar selama dia ada di folder yang sama dengan models/.
    # Sejak dipindah ke src/jarvis/ (models/ tetap di root proyek), fallback
    # itu tidak lagi benar - jadi diteruskan eksplisit di sini, bukan
    # dibiarkan tebak sendiri.
    env = dict(os.environ, JV_CHATTERBOX_MODEL_DIR=config.CHATTERBOX_MODEL_DIR)
    _cb_proc = subprocess.Popen(
        [config.CHATTERBOX_PYTHON, "chatterbox_server.py"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, bufsize=1, cwd=direktori, env=env,
    )
    _cb_antrian = queue.Queue()
    threading.Thread(target=_cb_pembaca, args=(_cb_proc, _cb_antrian), daemon=True).start()

    try:
        baris = _cb_antrian.get(timeout=config.CHATTERBOX_STARTUP_TIMEOUT)
    except queue.Empty:
        print(f"[tts] chatterbox: tidak siap dalam {config.CHATTERBOX_STARTUP_TIMEOUT}s - "
              "dinonaktifkan, pakai piper.")
        _cb_matikan()
        _cb_gagal_permanen = True
        return False

    if baris is None or json.loads(baris).get("type") != "ready":
        print(f"[tts] chatterbox: gagal start ({baris!r}) - dinonaktifkan, pakai piper.")
        _cb_matikan()
        _cb_gagal_permanen = True
        return False

    _cb_siap = True
    print(f"[tts] chatterbox siap dalam {time.time()-t0:.1f}s")
    return True


def matikan():
    """
    Hentikan subprocess Chatterbox. WAJIB dipanggil sebelum proses induk
    keluar.

    Kalau tidak: prosesnya jadi yatim tapi masih ada di cgroup service.
    systemd menganggap service belum berhenti, menunggu sampai
    TimeoutStopSec (90 detik default), lalu membunuh paksa dan menandai
    'Failed with result timeout' - dan karena unit-nya Restart=on-failure,
    Jarvis menyala lagi sendiri padahal kamu baru saja bilang "keluar".
    Persis itu yang sempat terjadi.
    """
    _cb_matikan()


def _cb_pembaca(proc, antrian):
    for baris in proc.stdout:
        antrian.put(baris)
    antrian.put(None)


def _cb_matikan():
    global _cb_proc, _cb_antrian, _cb_siap
    if _cb_proc is not None:
        try:
            _cb_proc.stdin.close()
            _cb_proc.terminate()
            _cb_proc.wait(timeout=5)
        except Exception:
            pass
    _cb_proc = None
    _cb_antrian = None
    _cb_siap = False


def _cb_sintesis(text: str):
    """
    Minta Chatterbox mensintesis teks. Kembalikan path wav, atau None kalau
    gagal (proses lain yang memanggil akan jatuh ke Piper). Kegagalan
    sintesis tunggal (mis. GPU lagi dipakai proses lain, OOM sesaat) TIDAK
    menonaktifkan Chatterbox - percobaan berikutnya tetap dicoba. Proses yang
    benar-benar mati baru memicu satu kali percobaan nyalakan ulang.
    """
    if not _cb_pastikan_siap():
        return None

    try:
        _cb_proc.stdin.write(json.dumps({"text": text}) + "\n")
        _cb_proc.stdin.flush()
    except (BrokenPipeError, ValueError):
        print("[tts] chatterbox: proses mati, mencoba nyalakan ulang sekali")
        _cb_matikan()
        if not _cb_pastikan_siap():
            return None
        _cb_proc.stdin.write(json.dumps({"text": text}) + "\n")
        _cb_proc.stdin.flush()

    try:
        baris = _cb_antrian.get(timeout=config.CHATTERBOX_TIMEOUT)
    except queue.Empty:
        print(f"[tts] chatterbox: tidak menjawab dalam {config.CHATTERBOX_TIMEOUT}s - pakai piper kali ini")
        return None

    if baris is None:
        print("[tts] chatterbox: proses mati di tengah sintesis - pakai piper kali ini")
        _cb_matikan()
        return None

    d = json.loads(baris)
    if d.get("type") == "error":
        print(f"[tts] chatterbox gagal sintesis: {d.get('message')} - pakai piper kali ini")
        return None
    return d.get("wav_path")


def _sintesis_ke_wav(text: str):
    """
    Ubah teks jadi file wav. Urutan: Chatterbox -> Piper -> espeak.
    Kembalikan path file-nya, atau None kalau tidak ada mesin TTS sama sekali.
    Pemanggil bertanggung jawab menghapus file-nya sendiri.
    """
    if config.CHATTERBOX_ENABLED:
        path = _cb_sintesis(text)
        if path is not None:
            return path

    if load():
        path = tempfile.mktemp(suffix=".wav")
        try:
            with wave.open(path, "wb") as wav_file:
                _voice.synthesize_wav(text, wav_file, syn_config=_syn_config)
            return path
        except Exception as e:
            print(f"[tts] piper gagal sintesis: {e}")
            if os.path.exists(path):
                os.remove(path)

    if shutil.which("espeak"):
        path = tempfile.mktemp(suffix=".wav")
        try:
            subprocess.run(
                ["espeak", "-v", config.ESPEAK_VOICE, "-w", path, text],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return path
        except subprocess.CalledProcessError as e:
            print(f"[tts] espeak gagal sintesis: {e}")

    return None


def _putar(wav_path: str, listener=None, sinyal_interupsi=None) -> bool:
    """
    Putar file wav lewat aplay. Dihentikan lebih awal kalau:
      - `sinyal_interupsi` (threading.Event) di-set - dari tombol fisik,
        lihat modul docstring. Ini yang diandalkan; tidak bisa salah trigger
        karena bukan berbasis suara sama sekali.
      - `listener` diberi, INTERRUPT_ENABLED nyala, dan mic mendengar suara
        di atas ambang - MATI secara default karena diukur langsung suara
        Jarvis sendiri (Piper maupun Chatterbox) bocor ke mic melewati
        ambang manapun yang masuk akal tanpa headset. Nyalakan lagi kalau
        pakai headset (lihat README).

    Kembalikan True kalau dihentikan lebih awal, False kalau selesai normal.
    """
    # Buang sinyal BASI dari sebelum playback ini mulai - kalau tombol
    # dipencet selagi Jarvis diam (tidak ada yang diputar), tanpa ini
    # playback BERIKUTNYA langsung terpotong dari frame pertama, hampir tanpa
    # suara. Cuma sinyal yang datang SELAGI playback ini berjalan yang valid.
    if sinyal_interupsi is not None:
        sinyal_interupsi.clear()

    proc = subprocess.Popen(["aplay", "-q", wav_path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    pantau_suara = listener is not None and config.INTERRUPT_ENABLED
    if sinyal_interupsi is None and not pantau_suara:
        proc.wait()
        return False

    diinterupsi = False
    while proc.poll() is None:
        if sinyal_interupsi is not None and sinyal_interupsi.is_set():
            diinterupsi = True
            break
        if pantau_suara and listener.terdengar_suara(config.INTERRUPT_THRESHOLD):
            diinterupsi = True
            break
        if sinyal_interupsi is not None and not pantau_suara:
            # Tidak ada pemantauan mic yang jadi jam denyut alami (biasanya
            # dari listener.terdengar_suara() yang blocking ~80ms), jadi beri
            # jeda kecil sendiri supaya loop ini tidak menghajar CPU.
            time.sleep(0.05)

    if diinterupsi:
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()

    if sinyal_interupsi is not None:
        sinyal_interupsi.clear()

    return diinterupsi


def speak(text: str, listener=None, sinyal_interupsi=None) -> bool:
    """
    Ucapkan teks. Kembalikan True kalau pengguna memotong sebelum selesai
    (barge-in), False kalau selesai normal atau tidak ada TTS yang tersedia.
    """
    if not text:
        return False
    print(f"[jarvis] {text}")

    wav_path = _sintesis_ke_wav(text)
    if wav_path is None:
        print("[warn] tidak ada TTS engine - pasang piper atau espeak. Balasan hanya dicetak.")
        return False

    try:
        return _putar(wav_path, listener, sinyal_interupsi)
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)
