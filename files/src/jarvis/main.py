"""
Jarvis - asisten suara lokal.

Sepenuhnya offline. Tidak ada panggilan network sama sekali.

    wake word -> rekam perintah -> speech-to-text -> cocokkan maksud -> jalankan

Jalankan:
    python -m jarvis.main
"""

import atexit
import fcntl
import os
import signal
import sys
import threading

from jarvis import audio
from jarvis import bunyi
from jarvis import commands
from jarvis import config
from jarvis import otak as otak_mod
from jarvis import responses
from jarvis import riwayat as riwayat_mod
from jarvis import speech_to_text
from jarvis import text_to_speech

_LOCK_PATH = os.path.expanduser("~/.jarvis/jarvis.lock")
_lock_file = None  # dipegang terus selama proses hidup - simpan di variabel
                   # modul supaya tidak digarbage-collect (yang otomatis
                   # melepas lock-nya).

# Ditulis jarvis_gui.py sebelum restart service: path ke satu berkas
# percakapan (files/percakapan/*.md) kalau kamu pilih "lanjutkan", atau
# tidak ditulis sama sekali / kosong kalau "percakapan baru". Dibaca dan
# DIHAPUS sekali di awal main() - lihat _ambil_target_resume().
_RESUME_MARKER = os.path.expanduser("~/.jarvis/resume_target")


def _cegah_instance_ganda():
    """
    Jarvis di systemd service DAN dijalankan manual barengan itu bahaya nyata,
    bukan cuma rebutan mic - dua-duanya bakal coba bicara lewat PipeWire, yang
    MENCAMPUR semua audio yang jalan bersamaan. Hasilnya suara ketumpuk-tumpuk,
    bukan error yang jelas.

    File lock ini bikin instance kedua gagal dalam hitungan milidetik, SEBELUM
    sempat memuat model apa pun - bukan nyala dulu baru ketauan belakangan.
    """
    global _lock_file
    os.makedirs(os.path.dirname(_LOCK_PATH), exist_ok=True)
    _lock_file = open(_LOCK_PATH, "w")
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"[main] Jarvis sudah jalan di proses lain (mungkin lewat systemd).")
        print("       Cek dengan:   systemctl --user status jarvis")
        print("       Kalau mau jalankan manual, matikan dulu:")
        print("         systemctl --user stop jarvis")
        sys.exit(1)
    _lock_file.write(str(os.getpid()))
    _lock_file.flush()

# Di-set oleh tombol interupsi fisik (SIGUSR1), dibaca text_to_speech selagi
# Jarvis bicara. Kenapa bukan mic: sudah diukur langsung - suara Jarvis
# sendiri (Piper maupun Chatterbox) bocor ke mic melewati ambang manapun yang
# masuk akal tanpa headset, jadi deteksi berbasis suara sering salah trigger
# ke suaranya sendiri. Tombol fisik tidak bisa salah begitu.
#
# Bind ke tombol lewat GNOME: Settings -> Keyboard -> Keyboard Shortcuts ->
# Custom Shortcuts -> tambah baru, command:
#   systemctl --user kill --kill-whom=main -s SIGUSR1 jarvis.service
# lalu tekan tombol yang mau dipakai (kami pakai Home).
#
# PENTING: --kill-whom=main wajib ada. Tanpanya, `systemctl kill` mengirim
# sinyal ke SELURUH proses anak di cgroup service ini (Chatterbox, claude CLI)
# - yang defaultnya MATI kena SIGUSR1 karena mereka tidak mendaftarkan
# handler untuk itu. Sudah kejadian sekali saat development: proses
# Chatterbox mati zombie, baru ketahuan dari /proc/<pid>/status.
_sinyal_interupsi = threading.Event()


def _pada_sinyal_interupsi(_signum, _frame):
    _sinyal_interupsi.set()


class Context:
    """
    Yang diberikan ke setiap handler: kemampuan bicara, dan kemampuan
    mendengarkan jawaban balik (dipakai alur konfirmasi shutdown).
    """

    def __init__(self, listener, otak=None):
        self._listener = listener
        # Handler ganti_model perlu menyentuh otak lewat ctx.
        self.otak = otak

    def speak(self, text: str) -> bool:
        """
        Ucapkan teks. Kembalikan True kalau pengguna memotong di tengah
        (barge-in, lewat tombol fisik) - ucapannya sudah mulai kerekam di
        preroll lewat text_to_speech, siap dilanjutkan otomatis di
        record_command berikutnya tanpa jeda.
        """
        diinterupsi = text_to_speech.speak(text, listener=self._listener,
                                           sinyal_interupsi=_sinyal_interupsi)
        if diinterupsi:
            print("[interupsi] tombol dipencet - langsung dengerin lanjutannya")
        else:
            # Buang audio yang masuk selagi kita bicara, kalau tidak asisten
            # akan mendengar suaranya sendiri di putaran berikutnya.
            self._listener.drain()
        return diinterupsi

    def listen(self, seconds: float) -> str:
        # Bunyi dulu supaya jelas kapan giliranmu menjawab - ini dipakai alur
        # konfirmasi shutdown, di mana salah timing berarti salah jawab.
        bunyi.rekam()
        self._listener.drain()
        return speech_to_text.transcribe(self._listener.record_fixed(seconds))


def proses_perintah(text, ctx, otak, riwayat=None) -> str:
    """
    Jalankan satu perintah. Kembalikan salah satu:
      "lanjut"     - sesi diteruskan, tunggu ucapan berikutnya
      "tutup_sesi" - sesi ditutup, balik menunggu wake word
      "keluar"     - matikan program

    Tiap giliran dicatat ke `riwayat` supaya bisa disimpan kalau percakapan
    ini nanti selesai. Dicatat di sini, bukan di otak.py, karena perintah
    jalur cepat tidak pernah lewat LLM sama sekali - cuma fungsi ini yang
    melihat SEMUA giliran.
    """
    def jawab(teks):
        if riwayat is not None:
            riwayat.catat(text, teks)
        return ctx.speak(teks)
    # Jalur cepat: perintah yang paling sering, ~0 ms, tanpa network.
    matched = commands.match(text)
    if matched is not None:
        name, handler, arg = matched
        print(f"[cepat] {name}" + (f" -> {arg!r}" if arg else ""))
        response = handler(ctx, arg)

        # Handler mengembalikan None = "tidak bisa kutangani". Kalau otak aktif,
        # serahkan ke sana - dia mungkin bisa menebak maksudnya.
        if response is None and otak is not None:
            print("[cepat] tidak tertangani, diserahkan ke LLM")
        elif response is None:
            jawab(responses.pick("app_gaada", app=arg or "itu"))
            return "lanjut"
        else:
            jawab(response)
            if name == "quit":
                return "keluar"
            if name == "stop_sesi":
                return "tutup_sesi"
            return "lanjut"

    # Tidak cocok -> serahkan ke LLM, yang bisa memanggil tool sendiri.
    if otak is None:
        jawab(responses.pick("gangerti"))
        return "lanjut"

    # Denyut pelan selagi menunggu - lewat rute claudecode ini 2,5-3 detik,
    # cukup lama untuk bikin ragu apakah perintahnya kedengeran atau tidak.
    # Dihentikan di finally supaya tidak terus berdenyut kalau LLM-nya error.
    bunyi.mulai_tunggu()
    try:
        jawaban = otak.tanya(text, ctx)
    except Exception as e:
        print(f"[otak] gagal: {type(e).__name__}: {e}")
        jawab("Maaf, otaknya lagi nggak bisa dihubungi.")
        return "lanjut"
    finally:
        bunyi.stop_tunggu()

    jawab(jawaban or responses.pick("gangerti"))
    return "lanjut"


def jalankan_sesi(listener, ctx, otak, riwayat=None) -> bool:
    """
    Satu sesi percakapan: setelah wake word, terus mendengarkan tanpa perlu
    wake word lagi. Kembalikan False kalau program harus berhenti.

    PENTING: mic TIDAK pernah mati. Satu InputStream dibuka sekali (lihat
    audio.py) dan openWakeWord jalan terus di background sepanjang waktu,
    termasuk selagi sesi ini aktif - jadi "hey jarvis" selalu bisa dideteksi
    kapan saja, tidak ada jeda. Yang berubah cuma loop mana yang MEMPROSES
    audio itu:

      - SESI AKTIF berhenti kalau kamu diam SESI_HENING_TIMEOUT detik - bukan
        mic berhenti dengar, tapi loop ini nyerah dan balik ke
        wait_for_wake_word() (yang sudah selalu jalan). Ini murni soal biaya:
        supaya tiap suara sekilas tidak terus dikirim ke whisper.
      - KONTEKS PERCAKAPAN cuma direset kalau kamu bilang "stop jarvis" (atau
        sinonimnya) secara eksplisit lewat commands.stop_sesi(). Diam saja
        TIDAK mereset apa pun - panggil lagi nanti, Jarvis masih nyambung.
    """
    for giliran in range(config.SESI_MAKS_GILIRAN):
        # Giliran pertama dilewati: bunyi wake word baru saja terdengar
        # sepersekian detik lalu, dua bunyi beruntun cuma jadi berisik.
        if giliran > 0:
            bunyi.rekam()
        # Buang audio bunyi tadi dari buffer, kalau tidak ikut kerekam dan
        # dikirim ke whisper sebagai "ucapan".
        listener.drain()

        audio_rekam = listener.record_command(maks_tunggu_bicara=config.SESI_HENING_TIMEOUT)
        # Durasi rekam BENERAN (bukan cuma selisih timestamp log, yang ikut
        # kehitung waktu transkripsi whisper) - bukti buat lacak "kepotong":
        # mentok di COMMAND_MAX_SECONDS (batas keras total), atau berhenti
        # duluan karena SILENCE_SECONDS/SILENCE_THRESHOLD mendeteksi hening.
        detik_rekam = len(audio_rekam) / config.SAMPLE_RATE
        print(f"[rec] durasi {detik_rekam:.2f}s"
              f" (batas keras {config.COMMAND_MAX_SECONDS}s)")
        text = speech_to_text.transcribe(audio_rekam)

        if not text:
            print(f"[sesi] {config.SESI_HENING_TIMEOUT}s tanpa suara - balik ke mode "
                  "wake word (mic tetap dengar terus), konteks tetap tersimpan")
            # Nada TURUN - tanpa ini kamu tidak tahu sesinya sudah berhenti,
            # dan baru sadar pas ngomong lagi tapi tidak ada yang menanggapi.
            bunyi.jeda()
            return True

        print(f"[kamu] {text}")

        hasil = proses_perintah(text, ctx, otak, riwayat)
        if hasil == "keluar":
            return False
        if hasil == "tutup_sesi":
            print("[sesi] ditutup dan konteks direset - diminta eksplisit")
            # Percakapan dinyatakan selesai di sini, jadi ini saatnya disimpan.
            _simpan_riwayat(riwayat, otak)
            return True

    print(f"[sesi] ditutup - batas {config.SESI_MAKS_GILIRAN} giliran")
    return True


def main():
    _cegah_instance_ganda()
    signal.signal(signal.SIGUSR1, _pada_sinyal_interupsi)
    _ensure_wake_word_models()
    # Muat semua model di awal, jangan saat perintah pertama datang.
    speech_to_text.load()
    # Chatterbox dulu (suara utama) - kalau gagal/nonaktif, load() di bawah
    # menyiapkan Piper sebagai fallback yang tetap dipanggil setiap kali.
    text_to_speech.load_chatterbox()
    if not text_to_speech.load():
        print("[tts] model Piper tidak ada - memakai espeak (suara robotik). "
              "Lihat README bagian 3.")
    bunyi.siapkan()

    otak = _siapkan_otak()
    riwayat = riwayat_mod.Riwayat()
    atexit.register(_bersihkan, otak)

    # Dihentikan lewat `systemctl stop/restart` itu sering - tanpa handler ini
    # SIGTERM membunuh proses langsung dan percakapan yang belum sempat
    # disimpan hilang begitu saja.
    def _pada_sigterm(_signum, _frame):
        print("\n[main] SIGTERM - menyimpan percakapan sebelum berhenti.")
        _simpan_riwayat(riwayat, otak)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _pada_sigterm)

    with audio.Listener() as listener:
        ctx = Context(listener, otak)
        if config.SAPA_SAAT_START:
            ctx.speak(responses.pick("siap"))
        else:
            # Diam saat start - tapi buang audio yang sempat masuk selagi
            # model dimuat, supaya tidak langsung salah trigger.
            listener.drain()
        print("[main] siap. Ucapkan wake word.")
        try:
            while True:
                listener.wait_for_wake_word()
                # Bunyi DULU sebelum apa pun - ini yang memberi tahu kamu
                # bahwa wake word kedengeran dan ucapanmu mulai direkam.
                bunyi.bangun()
                print("[sesi] dibuka - ngomong aja, nggak usah bilang wake word lagi")
                if not jalankan_sesi(listener, ctx, otak, riwayat):
                    # "keluar" - percakapan selesai untuk selamanya, simpan
                    # dulu sebelum proses benar-benar berhenti.
                    _simpan_riwayat(riwayat, otak)
                    bunyi.pamit()
                    break
        except KeyboardInterrupt:
            print("\n[main] dihentikan.")
            _simpan_riwayat(riwayat, otak)
            sys.exit(0)


def _bersihkan(otak=None):
    """
    Matikan semua subprocess sebelum keluar: Chatterbox (TTS) dan proses
    `claude` (otak). Keduanya subprocess yang HIDUP TERUS - kalau ditinggal,
    systemd menganggap service belum berhenti dan menunggu 90 detik sampai
    TimeoutStopSec, lalu menandainya GAGAL dan menyalakan Jarvis lagi karena
    Restart=on-failure.

    Dipasang lewat atexit supaya ikut jalan di semua jalur keluar - "keluar",
    Ctrl+C, maupun sys.exit dari handler SIGTERM.
    """
    try:
        text_to_speech.matikan()
    except Exception as e:
        print(f"[main] gagal menghentikan chatterbox: {e}")
    if otak is not None and hasattr(otak, "matikan"):
        try:
            otak.matikan()
        except Exception as e:
            print(f"[main] gagal menghentikan proses otak: {e}")


def _simpan_riwayat(riwayat, otak):
    """
    Simpan percakapan kalau ada isinya. Aman dipanggil kapan saja.

    session_id (kalau ada, rute claudecode) dicatat ke berkas supaya nanti
    bisa disambung lagi lewat jarvis_gui.py - lihat _muat_resume() di atas
    dan otak.OtakClaudeCode.session_id.
    """
    if riwayat is None or not config.RIWAYAT_ENABLED:
        return
    model = None
    session_id = None
    if otak is not None:
        model = f"{config.LLM_PROVIDER} ({getattr(otak, 'model', '?')})"
        session_id = getattr(otak, "session_id", None)
    riwayat.simpan(model=model, session_id=session_id)


def _ambil_target_resume():
    """
    Baca berkas penanda yang ditulis jarvis_gui.py, lalu HAPUS - supaya
    restart berikutnya (mis. gara-gara crash, bukan pilihan eksplisit dari
    GUI) tidak diam-diam balik ke percakapan lama yang sama terus-menerus.
    Kembalikan path berkas percakapan, atau None kalau tidak ada/kosong.
    """
    try:
        with open(_RESUME_MARKER) as f:
            path = f.read().strip()
    except OSError:
        return None
    try:
        os.remove(_RESUME_MARKER)
    except OSError:
        pass
    return path or None


def _muat_resume(otak, target):
    """
    Kalau jarvis_gui.py minta lanjutkan percakapan tertentu, muat ke `otak`.
    `target` sudah dibaca DAN dihapus dari disk oleh pemanggil - lihat
    _ambil_target_resume(), dipanggil sekali saja di _siapkan_otak() supaya
    marker-nya tetap terhapus walau otak ternyata tidak siap.

    Rute claudecode: sambung lewat --resume <session_id> (lihat
    otak.muat_riwayat_id) - Claude Code sendiri yang mengingat isinya, tidak
    perlu replay giliran satu-satu.
    Rute gemini: replay langsung ke list Percakapan kita sendiri (lihat
    otak.muat_riwayat) - di situ "sesi" memang cuma list Python, jadi murah.
    Transkrip LAMA tanpa session_id (dibuat sebelum fitur ini ada) tidak bisa
    disambung lewat rute claudecode - itu berarti replay manual yang berarti
    membayar generasi ulang tiap giliran, sengaja tidak dilakukan. Mulai
    percakapan baru saja untuk transkrip itu, dicatat jelas di log.
    """
    if target is None:
        return
    if otak is None:
        print(f"[main] target resume {target!r} diabaikan - otak LLM tidak aktif.")
        return
    if not os.path.exists(target):
        print(f"[main] target resume {target!r} tidak ditemukan - mulai percakapan baru.")
        return

    data = riwayat_mod.muat_dari_berkas(target)
    if not data or not data["giliran"]:
        print(f"[main] {target!r} tidak bisa dibaca/kosong - mulai percakapan baru.")
        return

    nama = os.path.basename(target)
    if data["session_id"] and hasattr(otak, "muat_riwayat_id"):
        otak.muat_riwayat_id(data["session_id"])
        print(f"[main] melanjutkan percakapan dari {nama} (sesi {data['session_id'][:8]}...)")
    elif hasattr(otak, "muat_riwayat"):
        otak.muat_riwayat(data["giliran"])
        print(f"[main] memuat {len(data['giliran'])} giliran dari {nama}")
    else:
        print(f"[main] {nama} tidak punya session_id dan provider "
              f"{config.LLM_PROVIDER} tidak dukung replay - mulai percakapan baru.")


def _siapkan_otak():
    """
    Bikin otak LLM kalau kuncinya ada. Kalau tidak, Jarvis tetap jalan -
    cuma terbatas ke 3 perintah bawaan. Tidak ada alasan program mati
    cuma karena API key belum diset.
    """
    # Dibaca (dan dihapus dari disk) SEKALI di sini, di awal - baik otak
    # ternyata siap maupun tidak, supaya markernya tidak nyangkut.
    target_resume = _ambil_target_resume()

    try:
        otak = otak_mod.buat_otak()
    except ValueError as e:
        print(f"[otak] {e}")
        return None
    if not otak.siap():
        print(f"[otak] {config.LLM_PROVIDER} tidak aktif. "
              "Jarvis jalan dengan perintah bawaan saja.")
        if target_resume:
            print(f"[main] target resume {target_resume!r} diabaikan - otak tidak aktif.")
        return None

    # Pakai model yang terakhir dipilih lewat suara, kalau ada.
    tersimpan = commands.muat_pilihan_model()
    if tersimpan and hasattr(otak, "model") and tersimpan != otak.model:
        otak.model = tersimpan
        print(f"[otak] memakai model tersimpan: {tersimpan}")

    model = getattr(otak, "model", getattr(config, "GEMINI_MODEL", "?"))
    print(f"[otak] {config.LLM_PROVIDER} aktif ({model})")

    _muat_resume(otak, target_resume)
    return otak


def _ensure_wake_word_models():
    """openWakeWord butuh model bawaan diunduh sekali di pemakaian pertama."""
    try:
        import openwakeword.utils

        openwakeword.utils.download_models(model_names=[config.WAKE_WORD_MODEL])
    except Exception as e:
        print(f"[warn] gagal memeriksa model wake word: {e}")


if __name__ == "__main__":
    main()
