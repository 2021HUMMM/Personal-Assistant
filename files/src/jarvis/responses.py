"""
Bank kalimat yang diucapkan Jarvis.

Semua teks yang keluar dari mulut Jarvis ada di file ini - terpisah dari
logikanya, jadi mengubah gaya bicara tidak perlu menyentuh commands.py.

Kenapa daftar acak, bukan LLM: yang bikin terdengar seperti bot itu bukan
pilihan katanya, tapi mengucapkan kalimat yang PERSIS SAMA setiap kali.
LLM kecil yang diuji untuk tugas sependek ini justru kurang bervariasi
(kolaps ke satu jawaban favorit) dan kadang mengarang - bilang "Sip." untuk
perintah yang tidak dia mengerti. Daftar acak menyelesaikan masalahnya dengan
nol milidetik dan tidak pernah bohong.

Menambah varian: tambahkan saja string ke daftarnya. Placeholder {app} dan
{detik} diisi otomatis; pastikan varian baru memakai placeholder yang sama
dengan tetangganya - test_responses.py akan menangkap kalau tidak.
"""

import random
import time

# Diambil acak, tapi tidak pernah sama dengan yang barusan dipakai.
BANK = {
    # --- saat start ---
    "siap": [
        "{sapaan}. Jarvis siap.",
        "{sapaan}.",
        "Jarvis siap.",
        "Siap. Ada apa?",
        "{sapaan}, ada yang bisa dibantu?",
    ],

    # --- buka aplikasi, berhasil ---
    # Sebagian menyebut nama aplikasi (berguna sebagai konfirmasi kalau salah
    # dengar), sebagian tidak (jendelanya toh sudah muncul sendiri).
    "membuka": [
        "Oke, {app}.",
        "Siap, {app}.",
        "{app}, bentar ya.",
        "Bentar, {app}.",
        "Oke.",
        "Siap.",
        "Sip, bentar.",
    ],

    # --- buka aplikasi, nama tidak disebut ---
    "app_mana": [
        "Aplikasi apa?",
        "Mau buka apa?",
        "Buka apa nih?",
        "Aplikasi apa yang mau dibuka?",
    ],

    # --- buka aplikasi, tidak ketemu ---
    "app_gaada": [
        "Nggak nemu {app}.",
        "{app} nggak ada di sini.",
        "Nggak ketemu {app}-nya.",
        "Kayaknya {app} belum terpasang.",
    ],

    # --- perintah tidak dikenali ---
    "gangerti": [
        "Hmm, nggak nangkep.",
        "Maaf, apa tadi?",
        "Kurang jelas nih.",
        "Nggak ngerti maksudnya.",
        "Coba ulangi?",
        "Apa tadi?",
    ],

    # --- konfirmasi shutdown ---
    # Sengaja variasinya sedikit dan semuanya menyebut aksi + cara menyetujui.
    # Untuk aksi berbahaya, bisa ditebak lebih penting daripada terdengar segar.
    "shutdown_yakin": [
        "Yakin mau matikan komputer? Bilang ya untuk lanjut.",
        "Matikan komputer, yakin? Bilang ya untuk lanjut.",
        "Beneran mau dimatiin? Bilang ya untuk lanjut.",
    ],
    "shutdown_jeda": [
        "Oke. Mati dalam {detik} detik, bilang batal kalau berubah pikiran.",
        "Siap. {detik} detik lagi mati, bilang batal untuk membatalkan.",
    ],
    "shutdown_gagal": [
        "Nggak berhasil matiin komputernya.",
        "Gagal - nggak ada perintah shutdown yang bisa dipakai.",
    ],

    # --- pembatalan ---
    "batal": [
        "Oke, batal.",
        "Sip, nggak jadi.",
        "Batal.",
        "Oke, nggak jadi.",
    ],

    # --- ganti model ---
    "model_diganti": [
        "Oke, sekarang pakai {model}.",
        "Siap, ganti ke {model}.",
        "{model} ya, sip.",
    ],

    # --- tutup sesi percakapan (bukan matikan program) ---
    "sesi_selesai": [
        "Oke.",
        "Siap.",
        "Sip.",
        "Oke, panggil lagi kalau butuh.",
        "Sama-sama.",
    ],

    # --- keluar ---
    "dadah": [
        "Sampai jumpa.",
        "Dadah.",
        "Oke, sampai nanti.",
        "Sip, dadah.",
    ],
}

_terakhir = {}


def pick(key: str, **fmt) -> str:
    """
    Ambil satu varian acak untuk `key`, tidak pernah mengulang varian yang
    barusan dipakai. Pengulangan berturut-turut itu justru yang paling
    terdengar seperti bot, jadi acak murni saja tidak cukup.
    """
    opsi = BANK[key]
    kandidat = [o for o in opsi if o != _terakhir.get(key)] or opsi
    dipilih = random.choice(kandidat)
    _terakhir[key] = dipilih
    return dipilih.format(**fmt, sapaan=_sapaan()) if "{sapaan}" in dipilih \
        else dipilih.format(**fmt)


def _sapaan() -> str:
    jam = time.localtime().tm_hour
    if 5 <= jam < 11:
        return "Pagi"
    if 11 <= jam < 15:
        return "Siang"
    if 15 <= jam < 18:
        return "Sore"
    return "Malam"
