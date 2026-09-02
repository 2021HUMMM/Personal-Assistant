"""
Tool yang boleh dipanggil LLM.

Ini "tombol" yang kita kasih ke model. Model sendiri tidak bisa apa-apa - dia
cuma bisa minta salah satu fungsi di sini dijalankan, dan kode kitalah yang
benar-benar menjalankannya.

Docstring dan type hint di tiap fungsi DIKIRIM ke model sebagai deskripsi tool.
Jadi tulis yang jelas - itu satu-satunya petunjuk yang dia punya soal kapan
tool ini dipakai dan apa isi argumennya.
"""

import shlex
import subprocess

from jarvis import commands
from jarvis import config

# Perintah shell yang boleh jalan tanpa konfirmasi: hanya yang MEMBACA.
# Daftar putih, bukan daftar hitam - menyebut apa yang boleh selalu lebih aman
# daripada mencoba menebak semua yang berbahaya.
SHELL_AMAN = {
    "ls", "cat", "head", "tail", "wc", "grep", "find", "file", "stat",
    "df", "du", "free", "uptime", "date", "whoami", "uname", "hostname",
    "ps", "pgrep", "top", "id", "which", "echo", "pwd", "env",
    "nvidia-smi", "lscpu", "lsblk", "ip", "sensors",
}

# Karakter yang membuka jalan ke perintah lain - ditolak apa pun isinya.
SHELL_TERLARANG = (";", "&&", "||", "|", ">", "<", "`", "$(", "\n")


def buat_tools(ctx):
    """
    Bangun daftar tool dengan `ctx` terikat di dalamnya.

    ctx dibutuhkan tool yang harus bicara atau bertanya balik ke pengguna
    (matikan_komputer). Dipakai closure, bukan variabel global, supaya tidak
    ada state yang bocor antar permintaan.
    """

    def buka_aplikasi(nama: str) -> str:
        """Luncurkan aplikasi desktop di komputer pengguna.

        Args:
            nama: Nama aplikasi seperti diucapkan pengguna, misalnya 'firefox',
                'vs code', 'discord'. Tidak perlu nama binary yang persis -
                akan dicocokkan otomatis.
        """
        hasil = commands.open_app(ctx, nama)
        if hasil is not None:
            return hasil
        # Kejadian nyata: fungsi ini mengembalikan None kalau bukan aplikasi
        # terpasang, dan tanpa pesan sejelas ini, model sempat menyerah lalu
        # asal buka browser kosong ("buka wikipedia" -> Firefox tanpa alamat)
        # alih-alih mencoba buka_website dengan URL yang benar.
        return (f"'{nama}' bukan aplikasi yang terpasang di komputer ini. "
                f"Kalau ini nama website (bukan aplikasi desktop), panggil "
                f"buka_website dengan URL-nya - JANGAN cuma buka browser kosong.")

    def buka_website(url: str) -> str:
        """Buka alamat website tertentu di browser default pengguna.

        Pakai ini untuk situs APA PUN yang diminta pengguna tapi bukan
        aplikasi terpasang di komputer - "buka wikipedia", "buka situs
        detik.com", dst. Untuk situs umum yang sudah punya alias cepat
        (youtube, gmail/email, maps, whatsapp, drive, calendar, github),
        buka_aplikasi juga bisa menemukannya tanpa lewat sini.

        Args:
            url: Alamat website. Boleh tanpa skema (mis. 'wikipedia.org') -
                akan ditambahkan https:// otomatis kalau belum ada.
        """
        return commands.buka_website(url)

    def jalankan_perintah(perintah: str) -> str:
        """Jalankan perintah shell yang HANYA MEMBACA, lalu kembalikan keluarannya.

        Pakai untuk memeriksa keadaan komputer: sisa disk, penggunaan memori,
        daftar proses, mencari file, membaca isi file.

        Hanya perintah baca yang diizinkan. Perintah yang mengubah atau menghapus
        akan ditolak - jangan coba pakai tool ini untuk itu.

        Args:
            perintah: Satu perintah shell, misalnya 'df -h' atau 'free -m'.
                Tidak boleh mengandung pipe, redirect, atau titik koma.
        """
        return _jalankan_aman(perintah)

    def matikan_komputer() -> str:
        """Matikan komputer pengguna.

        Akan meminta konfirmasi suara ke pengguna dulu, dan pengguna masih bisa
        membatalkan. Jangan panggil ini kecuali pengguna jelas memintanya.
        """
        return commands.shutdown(ctx, None)

    return [buka_aplikasi, buka_website, jalankan_perintah, matikan_komputer]


def _jalankan_aman(perintah: str) -> str:
    for c in SHELL_TERLARANG:
        if c in perintah:
            return f"Ditolak: perintah tidak boleh mengandung {c!r}."

    try:
        bagian = shlex.split(perintah)
    except ValueError as e:
        return f"Ditolak: perintah tidak bisa dibaca ({e})."

    if not bagian:
        return "Ditolak: perintah kosong."
    if bagian[0] not in SHELL_AMAN:
        return (f"Ditolak: '{bagian[0]}' tidak ada di daftar perintah aman. "
                f"Yang diizinkan hanya perintah yang membaca, bukan mengubah.")

    try:
        hasil = subprocess.run(bagian, capture_output=True, text=True,
                               timeout=config.SHELL_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"Perintah kehabisan waktu setelah {config.SHELL_TIMEOUT} detik."
    except FileNotFoundError:
        return f"Perintah '{bagian[0]}' tidak ada di sistem ini."

    keluaran = (hasil.stdout or hasil.stderr).strip()
    if not keluaran:
        return "(tidak ada keluaran)"
    # Potong supaya keluaran panjang tidak membanjiri konteks dan biaya.
    if len(keluaran) > config.SHELL_MAX_OUTPUT:
        keluaran = keluaran[:config.SHELL_MAX_OUTPUT] + "\n...(dipotong)"
    return keluaran
