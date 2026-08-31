"""
Menemukan aplikasi yang terpasang di komputer ini, di luar APP_ALIASES yang
dikurasi manual di commands.py - supaya "buka semua aplikasi yang ada"
beneran berarti semua, bukan cuma yang sempat didaftarkan.

Dua sumber, dua indeks terpisah:

  - Aplikasi desktop biasa: baca SEMUA file .desktop di sistem - cara yang
    sama dipakai GNOME Shell/launcher lain untuk mengisi menu aplikasi.
    Ini mencakup Flatpak dan sebagian besar aplikasi terpasang lewat apt.

  - Game Steam: baca libraryfolders.vdf milik Steam SENDIRI untuk menemukan
    semua library folder (termasuk drive eksternal yang mungkin tidak
    kepikiran), lalu appmanifest_*.acf di tiap folder untuk daftar
    nama -> appid. Steam TIDAK membuat file .desktop per game secara
    otomatis, jadi game tidak akan pernah ketemu lewat indeks desktop -
    ini kenapa perlu jalur terpisah.

Kedua indeks dibangun SEKALI dan disimpan di memori, bukan tiap kali
open_app dipanggil - supaya jalur cepat tetap cepat. Restart Jarvis kalau
baru pasang aplikasi/game baru dan mau langsung dikenali.
"""

import difflib
import glob
import os
import re
import shlex
import shutil

_indeks_desktop = None  # {nama_lower: (command_list, nama_asli)}
_indeks_steam = None    # {nama_lower: (command_list, nama_asli)}

_DIR_DESKTOP = (
    "/usr/share/applications",
    "/usr/local/share/applications",
    os.path.expanduser("~/.local/share/applications"),
    os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
    "/var/lib/flatpak/exports/share/applications",
)

# Placeholder freedesktop di baris Exec= - %f %F %u %U %i %c %k dst.
# Bukan bagian dari perintah sungguhan, harus dibuang.
_KODE_MEDAN = re.compile(r"%[a-zA-Z]")

# appmanifest_*.acf tidak cuma berisi game - juga komponen internal (Proton,
# runtime kompatibilitas, redistributable) yang tidak pernah ingin kamu
# luncurkan langsung. Tanpa filter ini, "buka steam" bisa nyasar ke "Steam
# Linux Runtime 3.0 (sniper)" - sudah kejadian pas dites.
_STEAM_BUKAN_GAME = re.compile(
    r"\b(proton|steam linux runtime|steamworks common redistributables|"
    r"steamvr|steam controller configs)\b", re.IGNORECASE)


def _parse_desktop(path):
    """
    Baca satu file .desktop, kembalikan (nama, command_list) atau None kalau
    bukan aplikasi yang layak ditampilkan (NoDisplay, bukan Type=Application,
    dsb - sama seperti yang disaring launcher aplikasi pada umumnya).
    """
    nama, exec_line, disembunyikan, tipe = None, None, False, "Application"
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            di_bagian_utama = False
            for baris in f:
                baris = baris.strip()
                if baris == "[Desktop Entry]":
                    di_bagian_utama = True
                    continue
                if baris.startswith("["):
                    di_bagian_utama = False  # [Desktop Action ...] dst - lewati
                    continue
                if not di_bagian_utama or "=" not in baris:
                    continue
                kunci, _, nilai = baris.partition("=")
                kunci, nilai = kunci.strip(), nilai.strip()
                if kunci == "Name" and nama is None:
                    nama = nilai  # ambil Name= default pertama, bukan terjemahan
                elif kunci == "Exec":
                    exec_line = nilai
                elif kunci in ("NoDisplay", "Hidden") and nilai.lower() == "true":
                    disembunyikan = True
                elif kunci == "Type":
                    tipe = nilai
    except OSError:
        return None

    if not nama or not exec_line or disembunyikan or tipe != "Application":
        return None

    try:
        command = shlex.split(_KODE_MEDAN.sub("", exec_line))
    except ValueError:
        return None
    return (nama, command) if command else None


def _bangun_indeks_desktop():
    indeks = {}
    for d in _DIR_DESKTOP:
        for path in glob.glob(os.path.join(d, "*.desktop")):
            hasil = _parse_desktop(path)
            if hasil is None:
                continue
            nama, command = hasil
            indeks[nama.lower()] = (command, nama)
    return indeks


def _cari_baris_path_vdf(path):
    """
    Parser sangat sederhana untuk libraryfolders.vdf - cuma ambil nilai
    baris `"path"  "..."`. Formatnya VDF (punya Valve), bukan JSON, tapi
    untuk kebutuhan ini regex saja cukup - tidak perlu library VDF penuh.
    """
    hasil = []
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for baris in f:
                m = re.match(r'\s*"path"\s*"(.+)"\s*$', baris)
                if m:
                    hasil.append(m.group(1))
    except OSError:
        pass
    return hasil


def _bangun_indeks_steam():
    indeks = {}
    steam_bin = shutil.which("steam") or "/usr/games/steam"
    if not (shutil.which("steam") or os.path.exists(steam_bin)):
        return indeks  # steam tidak terpasang, tidak ada yang perlu dicari

    # Root instalasi Steam bisa beda-beda nama tergantung distro/cara pasang.
    kandidat_root = [
        os.path.expanduser("~/.steam/debian-installation"),
        os.path.expanduser("~/.steam/steam"),
        os.path.expanduser("~/.local/share/Steam"),
    ]
    library_folders = set(kandidat_root)
    for root in kandidat_root:
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        library_folders.update(_cari_baris_path_vdf(vdf))

    for lib in library_folders:
        for manifest in glob.glob(os.path.join(lib, "steamapps", "appmanifest_*.acf")):
            try:
                isi = open(manifest, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            m_id = re.search(r'"appid"\s*"(\d+)"', isi)
            m_nama = re.search(r'"name"\s*"([^"]+)"', isi)
            if not (m_id and m_nama):
                continue
            nama = m_nama.group(1)
            if _STEAM_BUKAN_GAME.search(nama):
                continue
            indeks[nama.lower()] = ([steam_bin, "-applaunch", m_id.group(1)], nama)
    return indeks


def _pastikan_termuat():
    global _indeks_desktop, _indeks_steam
    if _indeks_desktop is None:
        _indeks_desktop = _bangun_indeks_desktop()
    if _indeks_steam is None:
        _indeks_steam = _bangun_indeks_steam()


def _cocokkan(nama_ucapan, indeks, ambang):
    if nama_ucapan in indeks:
        return indeks[nama_ucapan]
    terbaik, skor_terbaik = None, 0.0
    for key, val in indeks.items():
        skor = difflib.SequenceMatcher(None, nama_ucapan, key).ratio()
        if key in nama_ucapan or nama_ucapan in key:
            skor = max(skor, 0.9)
        if skor > skor_terbaik:
            terbaik, skor_terbaik = val, skor
    return terbaik if skor_terbaik >= ambang else None


def cari(nama_ucapan: str, ambang: float = 0.72):
    """
    Cari aplikasi/game terpasang yang cocok dengan nama_ucapan. Kembalikan
    (command_list, nama_asli) atau None kalau tidak ketemu di kedua indeks.

    Steam dicari duluan - nama game biasanya khas ("Cyberpunk 2077",
    "Hogwarts Legacy") dan jarang bentrok dengan nama aplikasi biasa.
    """
    _pastikan_termuat()
    hasil = _cocokkan(nama_ucapan, _indeks_steam, ambang)
    if hasil is not None:
        return hasil
    return _cocokkan(nama_ucapan, _indeks_desktop, ambang)


def jumlah_terindeks():
    """Buat cek.py - berapa banyak yang berhasil diindeks."""
    _pastikan_termuat()
    return len(_indeks_desktop), len(_indeks_steam)
