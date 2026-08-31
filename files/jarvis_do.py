"""
Satu pintu aman untuk Claude Code menjalankan aksi di komputer ini.

Kenapa lewat skrip, bukan langsung kasih akses Bash penuh: dengan
`--allowedTools "Bash(jarvis-do:*)"`, satu-satunya perintah yang boleh
dijalankan Claude Code adalah skrip ini. Semua aksi harus lewat sini, dan
sini memakai daftar putih yang sama dengan tools.py.

Dipanggil Claude Code sebagai:
    jarvis-do open <nama aplikasi>
    jarvis-do shell <perintah baca-saja>
    jarvis-do cuaca [kota]
    jarvis-do apps
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

import aplikasi
import commands
import config
import tools


class _NullCtx:
    """Handler minta ctx, tapi dari subprocess tidak ada yang bisa diajak bicara."""

    def speak(self, _text):
        pass

    def listen(self, _seconds):
        return ""


def main(argv):
    if len(argv) < 2:
        print("pakai: jarvis-do open|shell|apps [argumen]")
        return 2

    aksi, sisa = argv[1], argv[2:]

    if aksi == "open":
        if not sisa:
            return _err("butuh nama aplikasi")
        nama = " ".join(sisa).lower()
        hasil = commands.open_app(_NullCtx(), nama)
        if hasil is None:
            return _err(f"aplikasi '{nama}' tidak ditemukan. "
                        "Coba 'jarvis-do apps' untuk lihat yang terdaftar, "
                        "atau sebutkan nama binary-nya yang persis.")
        print(hasil)

    elif aksi == "shell":
        if not sisa:
            return _err("butuh perintah")
        print(tools._jalankan_aman(" ".join(sisa)))

    elif aksi == "cuaca":
        kota = " ".join(sisa) or config.KOTA_DEFAULT
        print(_cuaca(kota))

    elif aksi == "apps":
        # Biar Claude tahu apa yang tersedia tanpa menebak-nebak. Alias
        # dicetak lengkap (sedikit); daftar .desktop TIDAK dicetak lengkap -
        # bisa 100+ entri, buang-buang token - cukup bilang bisa dicoba
        # langsung by name, "open" sudah membaca indeks itu sendiri.
        aplikasi._pastikan_termuat()
        n_desktop, _ = aplikasi.jumlah_terindeks()
        game = sorted(nama for _, (_, nama) in aplikasi._indeks_steam.items())

        print("Alias terdaftar: " + ", ".join(sorted(set(commands.APP_ALIASES))))
        print(f"Aplikasi desktop terpasang: {n_desktop} (coba langsung by name, "
              "'jarvis-do open <nama>' mencarinya otomatis)")
        if game:
            print("Game Steam terpasang: " + ", ".join(game))

    else:
        return _err(f"aksi '{aksi}' tidak dikenal. "
                    "Yang ada: open, shell, cuaca, apps")

    return 0


def _cuaca(kota: str) -> str:
    """
    Ambil cuaca dari wttr.in. Dibikin aksi tersendiri, bukan lewat `shell`,
    karena dua alasan:

    1. Keamanan - menambahkan curl/wget ke daftar putih shell berarti membuka
       jalan ke SEMUA alamat, termasuk mengirim data keluar. Aksi ini cuma
       bisa menghubungi satu host, dengan bentuk URL yang sudah ditentukan.
    2. Kecepatan - lewat WebSearch bawaan Claude Code, pertanyaan cuaca makan
       ~15 detik. Lewat sini ~1 detik. Untuk asisten suara, bedanya besar.

    wttr.in tidak butuh API key sama sekali.
    """
    url = (f"https://wttr.in/{urllib.parse.quote(kota)}"
           f"?format=j1&lang=id")
    try:
        with urllib.request.urlopen(url, timeout=config.CUACA_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return f"Gagal ambil cuaca: {e}"
    except json.JSONDecodeError:
        return f"Nama kota '{kota}' tidak dikenali wttr.in."

    try:
        c = data["current_condition"][0]
        hari_ini = data["weather"][0]
        return (
            f"Cuaca {kota} sekarang: {c['weatherDesc'][0]['value']}, "
            f"{c['temp_C']} derajat (terasa {c['FeelsLikeC']}), "
            f"kelembapan {c['humidity']} persen, angin {c['windspeedKmph']} km/jam. "
            f"Hari ini {hari_ini['mintempC']} sampai {hari_ini['maxtempC']} derajat."
        )
    except (KeyError, IndexError) as e:
        return f"Bentuk data cuaca tidak seperti yang diharapkan: {e}"


def _err(pesan):
    print(f"Ditolak: {pesan}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
