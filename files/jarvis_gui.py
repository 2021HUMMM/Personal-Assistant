#!/usr/bin/env python3
"""
Antarmuka sederhana buat menyalakan/mematikan Jarvis dan memilih percakapan.

Jalan pakai python3 SISTEM, bukan venv proyek - GTK (PyGObject) itu paket
sistem, hampir tidak pernah ada di venv terisolasi, dan GUI ini tidak butuh
whisper/torch/piper/dkk sama sekali. Cuma butuh: baca folder percakapan/,
dan panggil systemctl.

Kenapa dibutuhkan: sebelum ini, satu-satunya cara menyalakan Jarvis lagi
setelah kamu bilang "keluar" adalah lewat terminal (`systemctl --user start
jarvis`). Ini kasih tombol buat itu, plus cara memilih mau mulai percakapan
baru atau menyambung salah satu yang sudah tersimpan.

Auto-spawn saat login: lewat entri XDG autostart. Pasang semuanya (autostart
+ shortcut aplikasi + shortcut Desktop) dengan:
    ./pasang-gui.sh

Menutup jendela ini TIDAK mematikan Jarvis - dua hal yang independen. Buka
lagi lewat shortcut yang sama kapan saja.
"""

import os
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)
import riwayat as riwayat_mod  # noqa: E402  (butuh sys.path di atas dulu)

_RESUME_MARKER = os.path.expanduser("~/.jarvis/resume_target")


def _systemctl(*args, timeout=8):
    try:
        return subprocess.run(["systemctl", "--user", *args],
                              capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def _status_jarvis() -> str:
    """'active', 'inactive', atau 'failed'/dll - apa pun kata systemctl."""
    return _systemctl("is-active", "jarvis").stdout.strip() or "unknown"


def _tulis_resume(path: str | None):
    """
    path=None berarti "percakapan baru" - hapus markernya kalau ada, supaya
    main.py tidak diam-diam menyambung yang lama.
    """
    os.makedirs(os.path.dirname(_RESUME_MARKER), exist_ok=True)
    if path is None:
        try:
            os.remove(_RESUME_MARKER)
        except OSError:
            pass
    else:
        with open(_RESUME_MARKER, "w") as f:
            f.write(path)


def _format_waktu(dt):
    if dt is None:
        return "?"
    return dt.strftime("%d %b, %H:%M")


class JendelaJarvis(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Jarvis")
        self.set_default_size(440, 560)
        self.set_border_width(16)

        akar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(akar)

        # --- Status + kontrol nyala/mati ---
        baris_status = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        akar.pack_start(baris_status, False, False, 0)

        self.label_status = Gtk.Label(label="●  Memeriksa...")
        self.label_status.set_xalign(0)
        baris_status.pack_start(self.label_status, True, True, 0)

        self.tombol_daya = Gtk.Button(label="…")
        self.tombol_daya.connect("clicked", self._pada_tombol_daya)
        baris_status.pack_start(self.tombol_daya, False, False, 0)

        tombol_segarkan = Gtk.Button(label="⟳")
        tombol_segarkan.set_tooltip_text("Segarkan status dan daftar percakapan")
        tombol_segarkan.connect("clicked", lambda _b: self._segarkan())
        baris_status.pack_start(tombol_segarkan, False, False, 0)

        akar.pack_start(Gtk.Separator(), False, False, 4)

        # --- Percakapan baru ---
        tombol_baru = Gtk.Button(label="＋  Percakapan Baru")
        tombol_baru.get_style_context().add_class("suggested-action")
        tombol_baru.connect("clicked", self._pada_percakapan_baru)
        akar.pack_start(tombol_baru, False, False, 0)

        label_lama = Gtk.Label(label="Atau lanjutkan percakapan sebelumnya:")
        label_lama.set_xalign(0)
        label_lama.set_margin_top(8)
        akar.pack_start(label_lama, False, False, 0)

        # --- Daftar percakapan lama ---
        gulir = Gtk.ScrolledWindow()
        gulir.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        akar.pack_start(gulir, True, True, 0)

        self.daftar = Gtk.ListBox()
        self.daftar.set_selection_mode(Gtk.SelectionMode.NONE)
        self.daftar.connect("row-activated", self._pada_pilih_percakapan)
        gulir.add(self.daftar)

        self.label_kosong = Gtk.Label(label="Belum ada percakapan tersimpan.")
        self.label_kosong.set_margin_top(24)

        self.show_all()
        self._segarkan()

    # --- status & kontrol ---

    def _segarkan(self):
        status = _status_jarvis()
        aktif = status == "active"
        ikon = "🟢" if aktif else ("🔴" if status in ("inactive", "failed") else "⚪")
        self.label_status.set_text(f"{ikon}  Jarvis: {status}")
        self.tombol_daya.set_label("Matikan" if aktif else "Nyalakan")
        self._muat_daftar_percakapan()

    def _pada_tombol_daya(self, _btn):
        aktif = _status_jarvis() == "active"
        self.tombol_daya.set_sensitive(False)
        self.label_status.set_text("●  " + ("Mematikan..." if aktif else "Menyalakan..."))

        def kerjakan():
            _systemctl("stop" if aktif else "start", "jarvis")
            GLib.idle_add(self._setelah_aksi_daya)

        threading_run(kerjakan)

    def _setelah_aksi_daya(self):
        self.tombol_daya.set_sensitive(True)
        self._segarkan()

    # --- percakapan baru / lanjutkan ---

    def _pada_percakapan_baru(self, _btn):
        _tulis_resume(None)
        self._restart_dengan_pesan("Memulai percakapan baru...")

    def _pada_pilih_percakapan(self, _listbox, row):
        path = getattr(row, "jarvis_path", None)
        if not path:
            return
        _tulis_resume(path)
        self._restart_dengan_pesan(f"Melanjutkan {os.path.basename(path)}...")

    def _restart_dengan_pesan(self, pesan):
        self.label_status.set_text("●  " + pesan)
        self.tombol_daya.set_sensitive(False)

        def kerjakan():
            _systemctl("restart", "jarvis")
            GLib.idle_add(self._setelah_aksi_daya)

        threading_run(kerjakan)

    # --- daftar percakapan ---

    def _muat_daftar_percakapan(self):
        for anak in list(self.daftar.get_children()):
            self.daftar.remove(anak)

        percakapan = riwayat_mod.daftar_percakapan()
        if not percakapan:
            self.daftar.add(self.label_kosong)
            self.daftar.show_all()
            return

        for p in percakapan:
            self.daftar.add(self._baris_percakapan(p))
        self.daftar.show_all()

    def _baris_percakapan(self, p):
        row = Gtk.ListBoxRow()
        row.jarvis_path = p["path"]

        isi = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        isi.set_border_width(8)
        row.add(isi)

        atas = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        isi.pack_start(atas, False, False, 0)

        label_waktu = Gtk.Label(label=_format_waktu(p["mulai"]))
        label_waktu.set_xalign(0)
        label_waktu.get_style_context().add_class("dim-label")
        atas.pack_start(label_waktu, True, True, 0)

        label_giliran = Gtk.Label(label=f"{p['giliran']} giliran")
        label_giliran.get_style_context().add_class("dim-label")
        atas.pack_start(label_giliran, False, False, 0)

        if not p["session_id"]:
            # Transkrip dari sebelum fitur resume ada - klik tetap boleh,
            # tapi hasilnya mulai percakapan baru (lihat main.py:_muat_resume).
            label_lama = Gtk.Label(label="lama")
            label_lama.set_tooltip_text(
                "Percakapan ini disimpan sebelum fitur 'lanjutkan' ada, "
                "jadi tidak bisa disambung - memilihnya akan mulai baru.")
            label_lama.get_style_context().add_class("dim-label")
            atas.pack_start(label_lama, False, False, 0)

        label_preview = Gtk.Label(label=p["preview"])
        label_preview.set_xalign(0)
        label_preview.set_line_wrap(True)
        isi.pack_start(label_preview, False, False, 0)

        return row


def threading_run(fn):
    import threading
    threading.Thread(target=fn, daemon=True).start()


class AplikasiJarvis(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="com.jarvis.gui")
        self.jendela = None

    def do_activate(self):
        # Kalau jendela sudah ada (mis. dipanggil lagi lewat shortcut selagi
        # sudah jalan dari autostart), angkat ke depan - jangan buka jendela
        # baru yang kedua.
        if self.jendela is None:
            self.jendela = JendelaJarvis(self)
        self.jendela.present()


def main():
    app = AplikasiJarvis()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
