"""
Catatan percakapan yang sudah selesai, disimpan ke disk - dan dibaca lagi
kalau kamu mau melanjutkannya lewat jarvis_gui.py.

Kenapa dicatat sendiri di sini, bukan diambil dari otak: riwayat rute
claudecode dipegang oleh proses `claude` itu sendiri (lihat otak.py), tidak
ada di Python. Dan perintah jalur cepat ("buka firefox") tidak pernah lewat
LLM sama sekali. Jadi satu-satunya tempat yang melihat SELURUH percakapan
adalah loop sesi di main.py - di situlah pencatatannya.

Umurnya mengikuti konteks percakapan, bukan sesi:
  - diam lalu balik ke wake word  -> TIDAK disimpan, percakapan belum selesai
  - "stop jarvis"                 -> disimpan lalu dikosongkan
  - "keluar" / SIGTERM / Ctrl+C   -> disimpan lalu proses berhenti

Jadi satu berkas = satu percakapan utuh, walau di tengahnya sempat berhenti
beberapa kali karena kamu diam.

Session ID (rute claudecode): Claude Code sendiri sudah menyimpan riwayat
percakapan tiap sesi print-mode ke disk dan bisa dilanjutkan lewat
`claude --resume <session_id>` - diverifikasi langsung, proses BARU dengan
--resume beneran mengingat percakapan dari proses lama. Jadi "lanjutkan
percakapan" TIDAK perlu memutar ulang tiap giliran lama (yang berarti biaya
generasi ulang) - cukup titipkan session_id-nya. ID itu disimpan sebagai
metadata di kepala berkas markdown.
"""

import glob
import os
import re
from datetime import datetime

from jarvis import config

# Baris metadata "- Session ID: <uuid>" di kepala berkas. Dipisah dari baris
# metadata lain (Mulai/Selesai/Model) karena cuma ini yang perlu di-parse
# balik oleh program, sisanya murni buat dibaca manusia.
_POLA_SESSION_ID = re.compile(r"^- Session ID\s*:\s*(\S+)\s*$", re.MULTILINE)

# Header tiap blok: "### HH:MM:SS — kamu" atau "### HH:MM:SS — jarvis". Isinya
# adalah SEMUA teks sampai header berikutnya (atau akhir berkas) - bukan
# sampai "\n\n" literal, karena giliran TERAKHIR di berkas cuma diakhiri satu
# newline (bukan dua), jadi pola yang mensyaratkan "\n\n" di ekor akan
# kehilangan giliran terakhir. Ketahuan lewat pengujian round-trip.
_POLA_HEADER = re.compile(r"### \d{2}:\d{2}:\d{2} — (kamu|jarvis)\n\n", re.MULTILINE)


class Riwayat:
    def __init__(self, folder=None):
        self.folder = os.path.expanduser(folder or config.RIWAYAT_DIR)
        self._giliran = []
        self._mulai = None

    def catat(self, ucapan: str, jawaban: str):
        if self._mulai is None:
            self._mulai = datetime.now()
        self._giliran.append((datetime.now(), ucapan, jawaban))

    def kosong(self) -> bool:
        return not self._giliran

    def reset(self):
        self._giliran = []
        self._mulai = None

    def simpan(self, model=None, session_id=None):
        """
        Tulis percakapan ke berkas markdown, lalu kosongkan.
        Kembalikan path berkasnya, atau None kalau tidak ada yang disimpan.

        Markdown, bukan JSON: ini buat DIBACA manusia nanti. Kalau perlu
        diolah program, formatnya masih gampang di-parse - lihat
        muat_dari_berkas() di bawah.
        """
        if self.kosong():
            return None

        selesai = datetime.now()
        try:
            os.makedirs(self.folder, exist_ok=True)
        except OSError as e:
            print(f"[riwayat] gagal bikin folder: {e}")
            return None

        # Nama dari waktu MULAI supaya urut secara alfabet. Tambah akhiran
        # kalau bentrok: dua percakapan bisa mulai di detik yang sama (mis.
        # "stop jarvis" lalu langsung "hey jarvis" lagi), dan tanpa ini yang
        # kedua menimpa yang pertama tanpa peringatan apa pun.
        dasar = self._mulai.strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(self.folder, f"{dasar}.md")
        n = 2
        while os.path.exists(path):
            path = os.path.join(self.folder, f"{dasar}_{n}.md")
            n += 1

        baris = [
            f"# Percakapan {self._mulai.strftime('%Y-%m-%d %H:%M')}",
            "",
            f"- Mulai   : {self._mulai.strftime('%H:%M:%S')}",
            f"- Selesai : {selesai.strftime('%H:%M:%S')}",
            f"- Giliran : {len(self._giliran)}",
        ]
        if model:
            baris.append(f"- Model   : {model}")
        if session_id:
            baris.append(f"- Session ID: {session_id}")
        baris += ["", "---", ""]

        for waktu, ucapan, jawaban in self._giliran:
            jam = waktu.strftime("%H:%M:%S")
            baris.append(f"### {jam} — kamu")
            baris.append("")
            baris.append(ucapan.strip() or "_(kosong)_")
            baris.append("")
            baris.append(f"### {jam} — jarvis")
            baris.append("")
            baris.append((jawaban or "").strip() or "_(diam)_")
            baris.append("")

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(baris))
        except OSError as e:
            print(f"[riwayat] gagal menyimpan: {e}")
            return None

        print(f"[riwayat] {len(self._giliran)} giliran disimpan ke {path}")
        self.reset()
        return path


def muat_dari_berkas(path: str):
    """
    Baca satu berkas percakapan. Kembalikan dict:
        {"session_id": str|None, "giliran": [(ucapan, jawaban), ...]}
    atau None kalau berkasnya tidak bisa dibaca/diparse.

    Parsernya cocok dengan format PERSIS yang ditulis Riwayat.simpan() di
    atas - bukan parser markdown umum. Kalau berkasnya diedit tangan dan
    formatnya berubah, giliran yang tidak cocok pola cuma dilewati, bukan
    bikin keseluruhan gagal.
    """
    try:
        isi = open(path, encoding="utf-8").read()
    except OSError:
        return None

    m = _POLA_SESSION_ID.search(isi)
    session_id = m.group(1) if m else None

    # Potong isi berdasarkan posisi tiap header, bukan berdasarkan "\n\n" di
    # ekor - lihat komentar _POLA_HEADER soal kenapa.
    penanda = list(_POLA_HEADER.finditer(isi))
    blok = []  # [(peran, teks), ...]
    for i, m in enumerate(penanda):
        awal = m.end()
        akhir = penanda[i + 1].start() if i + 1 < len(penanda) else len(isi)
        blok.append((m.group(1), isi[awal:akhir].strip()))

    giliran = []
    i = 0
    while i + 1 < len(blok):
        peran1, teks1 = blok[i]
        peran2, teks2 = blok[i + 1]
        if peran1 == "kamu" and peran2 == "jarvis":
            giliran.append((teks1, teks2))
            i += 2
        else:
            i += 1  # format tidak sesuai urutan yang diharapkan - lewati satu

    return {"session_id": session_id, "giliran": giliran}


def daftar_percakapan(folder=None, batas=50):
    """
    Daftar percakapan tersimpan, TERBARU DULU. Tiap entri:
        {"path", "nama_file", "mulai", "giliran", "preview", "session_id"}
    "preview" = ucapan pertamamu, dipotong - buat ditampilkan di jarvis_gui.py
    tanpa perlu baca+parse seluruh isi berkas satu-satu.
    """
    folder = os.path.expanduser(folder or config.RIWAYAT_DIR)
    hasil = []
    for path in sorted(glob.glob(os.path.join(folder, "*.md")), reverse=True):
        data = muat_dari_berkas(path)
        if not data or not data["giliran"]:
            continue
        ucapan_pertama = data["giliran"][0][0]
        preview = ucapan_pertama[:70] + ("…" if len(ucapan_pertama) > 70 else "")
        hasil.append({
            "path": path,
            "nama_file": os.path.basename(path),
            "mulai": _mulai_dari_nama_file(path),
            "giliran": len(data["giliran"]),
            "preview": preview,
            "session_id": data["session_id"],
        })
        if len(hasil) >= batas:
            break
    return hasil


def _mulai_dari_nama_file(path):
    """'2026-08-30_21-22-34.md' -> datetime. None kalau nama tidak sesuai pola."""
    nama = os.path.basename(path).rsplit(".", 1)[0]
    nama = re.sub(r"_\d+$", "", nama)  # buang akhiran _2, _3 dst kalau ada
    try:
        return datetime.strptime(nama, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None
