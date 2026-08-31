"""
Efek suara pendek sebagai umpan balik audio.

Momen yang ditandai:
  bangun()  - wake word terdengar, giliranmu bicara
  rekam()   - giliranmu bicara lagi (bunyi SAMA dengan bangun, sengaja)
  tunggu()  - Claude lagi mikir (berdenyut pelan sampai jawabannya datang)
  jeda()    - sesi berhenti karena diam, balik menunggu wake word
  pamit()   - program benar-benar berhenti

Pola nadanya konsisten dan sengaja: NAIK berarti mulai/perhatian, TURUN
berarti berhenti. Jadi arahnya kebaca tanpa perlu menghafal bunyinya satu
per satu.

Kenapa nada dibangkitkan sendiri, bukan file wav dari luar: tidak ada aset
tambahan yang perlu diunduh atau di-commit, dan gampang disetel (frekuensi,
durasi, volume) tanpa ganti file. File hasilnya disimpan di ~/.jarvis/bunyi/
dan TIDAK ditimpa kalau sudah ada - jadi kamu bisa menaruh wav buatanmu
sendiri di situ untuk mengganti bunyinya.

Semua bunyi sengaja SANGAT pendek (<200ms). Ini terdengar puluhan kali
sehari; bunyi yang kepanjangan atau terlalu keras cepat bikin kesal, dan
menambah latensi ke tiap giliran.
"""

import os
import shutil
import struct
import subprocess
import threading
import wave

import numpy as np

import config

SR = 22050  # sample rate untuk file bunyi (bukan mic, ini output saja)

_dir = None
_path = {}
_tunggu_stop = None
_tunggu_thread = None


def _nada(frekuensi, durasi, volume, fade=0.012):
    """
    Satu nada sinus dengan fade in/out. Fade-nya wajib - tanpa itu gelombang
    terpotong mendadak di awal/akhir dan terdengar sebagai 'klik' yang tajam.
    """
    t = np.linspace(0, durasi, int(SR * durasi), endpoint=False)
    gel = np.sin(2 * np.pi * frekuensi * t)
    n_fade = min(int(SR * fade), len(gel) // 2)
    if n_fade > 0:
        gel[:n_fade] *= np.linspace(0, 1, n_fade)
        gel[-n_fade:] *= np.linspace(1, 0, n_fade)
    return gel * volume


def _hening(durasi):
    return np.zeros(int(SR * durasi))


def _tulis_wav(path, gel):
    data = np.clip(gel, -1.0, 1.0)
    pcm = (data * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def siapkan():
    """
    Bangkitkan file bunyi kalau belum ada. Dipanggil sekali saat start.
    File yang sudah ada TIDAK ditimpa - itu yang bikin kamu bisa mengganti
    bunyinya dengan wav sendiri.
    """
    global _dir
    _dir = os.path.expanduser(config.SUARA_DIR)
    try:
        os.makedirs(_dir, exist_ok=True)
    except OSError as e:
        print(f"[bunyi] tidak bisa bikin folder bunyi: {e}")
        return False

    v = config.SUARA_VOLUME

    # Naik dua nada - terdengar seperti "siap, silakan".
    giliranmu = np.concatenate([
        _nada(587, 0.075, v),
        _nada(880, 0.095, v),
    ])

    resep = {
        # "bangun" dan "rekam" sengaja BUNYINYA SAMA. Dua-duanya artinya
        # persis satu hal buat kamu: giliranmu bicara sekarang. Sempat dibikin
        # beda (blip pendek untuk rekam), tapi terasa tidak konsisten - kamu
        # jadi ragu apakah keduanya menandakan hal yang berbeda.
        #
        # Tetap dua file terpisah supaya kamu masih bisa membedakannya nanti
        # kalau memang mau: timpa salah satunya dengan wav sendiri.
        "bangun": giliranmu,
        "rekam": giliranmu,
        # Nada rendah pelan, dipakai berulang selagi menunggu.
        "tunggu": _nada(392, 0.065, v * 0.45),
        # TURUN dua nada - kebalikan dari "giliranmu". Polanya sengaja
        # konsisten: naik = mulai/perhatian, turun = berhenti. Jadi tanpa
        # menghafal bunyinya pun arahnya sudah kebaca.
        "jeda": np.concatenate([
            _nada(880, 0.070, v * 0.6),
            _nada(587, 0.090, v * 0.6),
        ]),
        # Turun TIGA nada - lebih final daripada jeda, karena ini memang
        # penutup: prosesnya benar-benar berhenti setelah ini.
        "pamit": np.concatenate([
            _nada(880, 0.075, v),
            _nada(660, 0.075, v),
            _nada(440, 0.130, v),
        ]),
    }

    for nama, gel in resep.items():
        path = os.path.join(_dir, f"{nama}.wav")
        _path[nama] = path
        if not os.path.exists(path):
            try:
                _tulis_wav(path, gel)
            except OSError as e:
                print(f"[bunyi] gagal menulis {path}: {e}")
                return False
    return True


def _putar(nama, tunggu=True):
    if not config.SUARA_ENABLED:
        return
    path = _path.get(nama)
    if not path or not os.path.exists(path) or not shutil.which("aplay"):
        return
    try:
        if tunggu:
            subprocess.run(["aplay", "-q", path], timeout=3,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["aplay", "-q", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (subprocess.TimeoutExpired, OSError):
        pass


def bangun():
    """Wake word terdengar. Ditunggu sampai selesai - ini penanda utama."""
    _putar("bangun", tunggu=True)


def rekam():
    """Mulai merekam. Ditunggu sampai selesai supaya tidak ikut kerekam."""
    if config.SUARA_REKAM:
        _putar("rekam", tunggu=True)


def jeda():
    """Sesi berhenti karena kamu diam - balik menunggu wake word."""
    _putar("jeda", tunggu=True)


def pamit():
    """Program benar-benar berhenti. Ditunggu sampai selesai - kalau tidak,
    prosesnya keburu mati sebelum bunyinya sempat terdengar."""
    _putar("pamit", tunggu=True)


def mulai_tunggu():
    """
    Mulai berdenyut pelan, menandakan Jarvis lagi menunggu jawaban LLM.
    Aman dipanggil berkali-kali; yang lama dihentikan dulu.
    """
    global _tunggu_stop, _tunggu_thread
    if not config.SUARA_ENABLED or not config.SUARA_TUNGGU:
        return
    stop_tunggu()
    _tunggu_stop = threading.Event()
    _tunggu_thread = threading.Thread(target=_loop_tunggu, args=(_tunggu_stop,),
                                      daemon=True)
    _tunggu_thread.start()


def _loop_tunggu(stop):
    # Jeda dulu sebelum bunyi pertama. Kalau jawabannya datang cepat, tidak
    # ada bunyi sama sekali - percuma memberi tahu "tunggu ya" untuk sesuatu
    # yang sudah selesai duluan.
    if stop.wait(config.SUARA_TUNGGU_JEDA_AWAL):
        return
    while not stop.is_set():
        _putar("tunggu", tunggu=False)
        if stop.wait(config.SUARA_TUNGGU_INTERVAL):
            return


def stop_tunggu():
    """Hentikan denyut tunggu. Aman dipanggil walau tidak sedang berdenyut."""
    global _tunggu_stop, _tunggu_thread
    if _tunggu_stop is not None:
        _tunggu_stop.set()
    if _tunggu_thread is not None:
        _tunggu_thread.join(timeout=1)
    _tunggu_stop = None
    _tunggu_thread = None
