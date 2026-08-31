"""
Uji siklus hidup riwayat percakapan - tanpa mic, tanpa LLM, tanpa suara.

    python test_riwayat.py

Yang diuji itu ATURAN KAPAN disimpan, bukan sekadar bisa nulis file:
  - diam lalu balik ke wake word  -> TIDAK disimpan (percakapan belum selesai)
  - "stop jarvis"                 -> disimpan lalu dikosongkan
  - "keluar"                      -> disimpan juga
  - dua percakapan di detik sama  -> tidak saling menimpa

Juga menguji jarvis_gui.py "lanjutkan percakapan": parsing berkas markdown
balik ke giliran (muat_dari_berkas), dan alur resume di main.py - mana yang
sambung lewat --resume <session_id> (claudecode), mana yang replay langsung
(gemini), dan mana yang jatuh ke percakapan baru (transkrip lama tanpa
session_id, atau otak tidak aktif).
"""

import glob
import os
import shutil
import tempfile

import bunyi
import main
import riwayat as riwayat_mod
import speech_to_text


class _ListenerPalsu:
    def __init__(self, ucapan):
        self.antre = list(ucapan)

    def record_command(self, maks_tunggu_bicara=None):
        return self.antre.pop(0) if self.antre else ""

    def drain(self):
        pass


class _OtakPalsu:
    model = "haiku"

    def reset_percakapan(self):
        pass

    def tanya(self, _teks, _ctx):
        return "jawaban llm"


class _CtxPalsu:
    def __init__(self, otak):
        self.otak = otak

    def speak(self, _teks):
        return False

    def listen(self, _detik):
        return ""


def _bisukan_bunyi():
    """Uji ini soal logika, bukan audio - jangan bunyi-bunyi saat dijalankan."""
    for nama in ("bangun", "rekam", "jeda", "pamit", "mulai_tunggu", "stop_tunggu"):
        setattr(bunyi, nama, lambda *a, **k: None)
    main.bunyi = bunyi


def run() -> int:
    gagal = 0
    _bisukan_bunyi()
    speech_to_text.transcribe = lambda x: x

    folder = tempfile.mkdtemp(prefix="jarvis_riwayat_uji_")
    try:
        otak = _OtakPalsu()
        r = riwayat_mod.Riwayat(folder=folder)

        def berkas():
            return sorted(glob.glob(os.path.join(folder, "*.md")))

        # 1. Diam -> belum selesai, tidak boleh disimpan, tapi tetap diingat.
        main.jalankan_sesi(_ListenerPalsu(["buka firefox", ""]), _CtxPalsu(otak), otak, r)
        ok = len(berkas()) == 0 and len(r._giliran) == 1
        gagal += not ok
        print(f"{'ok  ' if ok else 'GAGAL'} diam -> {len(berkas())} berkas (harus 0), "
              f"{len(r._giliran)} giliran diingat (harus 1)")

        # 2. Lanjut lalu stop -> disimpan, dan isinya termasuk giliran dari
        #    sesi sebelum jeda (satu percakapan utuh, bukan dua potong).
        main.jalankan_sesi(_ListenerPalsu(["jelaskan fotosintesis", "stop jarvis"]),
                           _CtxPalsu(otak), otak, r)
        ok = len(berkas()) == 1 and len(r._giliran) == 0
        gagal += not ok
        print(f"{'ok  ' if ok else 'GAGAL'} stop jarvis -> {len(berkas())} berkas (harus 1), "
              f"{len(r._giliran)} sisa (harus 0)")

        if berkas():
            isi = open(berkas()[0], encoding="utf-8").read()
            ok = "buka firefox" in isi and "jelaskan fotosintesis" in isi
            gagal += not ok
            print(f"{'ok  ' if ok else 'GAGAL'} berkas memuat giliran dari SEBELUM jeda "
                  "(satu percakapan utuh)")

        # 3. Keluar -> disimpan juga, dan program berhenti.
        lanjut = main.jalankan_sesi(_ListenerPalsu(["buka discord", "keluar"]),
                                    _CtxPalsu(otak), otak, r)
        r.simpan(model="uji")
        ok = lanjut is False and len(berkas()) == 2
        gagal += not ok
        print(f"{'ok  ' if ok else 'GAGAL'} keluar -> lanjut={lanjut} (harus False), "
              f"{len(berkas())} berkas (harus 2)")

        # 4. Nama berkas tidak boleh bentrok walau di detik yang sama.
        ok = len(set(berkas())) == len(berkas()) == 2
        gagal += not ok
        print(f"{'ok  ' if ok else 'GAGAL'} dua percakapan di detik sama -> nama berkas unik")

        # 5. Riwayat kosong tidak menghasilkan berkas sampah.
        sebelum = len(berkas())
        hasil = riwayat_mod.Riwayat(folder=folder).simpan()
        ok = hasil is None and len(berkas()) == sebelum
        gagal += not ok
        print(f"{'ok  ' if ok else 'GAGAL'} riwayat kosong -> tidak bikin berkas")

        # 6. Parsing balik: session_id dan SEMUA giliran (termasuk yang
        #    TERAKHIR - ini yang sempat bug, ekor berkas cuma satu newline
        #    bukan dua, jadi pola regex naif kehilangan giliran terakhir).
        r6 = riwayat_mod.Riwayat(folder=folder)
        r6.catat("giliran satu", "jawaban satu")
        r6.catat("giliran dua", "jawaban dua")
        r6.catat("giliran tiga - yang ini paling gampang hilang", "jawaban tiga")
        path6 = r6.simpan(model="uji", session_id="sesi-uji-xyz")
        data6 = riwayat_mod.muat_dari_berkas(path6)
        ok = (data6 is not None and data6["session_id"] == "sesi-uji-xyz"
              and len(data6["giliran"]) == 3
              and data6["giliran"][-1] == ("giliran tiga - yang ini paling gampang hilang",
                                           "jawaban tiga"))
        gagal += not ok
        print(f"{'ok  ' if ok else 'GAGAL'} muat_dari_berkas -> session_id + "
              f"semua {len(data6['giliran']) if data6 else 0}/3 giliran (termasuk yang terakhir)")

        # 7. Berkas tanpa session_id (transkrip lama) -> None, bukan error.
        r7 = riwayat_mod.Riwayat(folder=folder)
        r7.catat("halo", "hai")
        path7 = r7.simpan()
        data7 = riwayat_mod.muat_dari_berkas(path7)
        ok = data7 is not None and data7["session_id"] is None
        gagal += not ok
        print(f"{'ok  ' if ok else 'GAGAL'} muat_dari_berkas tanpa session_id -> None, tidak error")

        # 8. daftar_percakapan: urutan terbaru dulu, preview terpotong benar.
        entri = riwayat_mod.daftar_percakapan(folder)
        ok = (len(entri) >= 2
              and entri[0]["mulai"] >= entri[-1]["mulai"]
              and entri[0]["preview"])
        gagal += not ok
        print(f"{'ok  ' if ok else 'GAGAL'} daftar_percakapan -> {len(entri)} entri, "
              "terbaru dulu, ada preview")

    finally:
        shutil.rmtree(folder, ignore_errors=True)

    gagal += _uji_resume()

    total = 12
    print(f"\n{total - gagal}/{total} lolos")
    return 1 if gagal else 0


def _uji_resume() -> int:
    """
    4 skenario alur "lanjutkan percakapan" di main.py: mana yang sambung
    lewat --resume, mana yang replay, mana yang jatuh ke percakapan baru.
    Otak dan commands DIGANTI SEMENTARA dengan tiruan, dikembalikan lagi di
    akhir - supaya tidak bocor ke modul main yang dipakai file uji lain.
    """
    gagal = 0
    otak_mod_asli, commands_asli = main.otak_mod, main.commands
    folder = tempfile.mkdtemp(prefix="jarvis_resume_uji_")
    try:
        class _CommandsPalsu:
            @staticmethod
            def muat_pilihan_model():
                return None

        main.commands = _CommandsPalsu()

        def _tulis_marker(path):
            os.makedirs(os.path.dirname(main._RESUME_MARKER), exist_ok=True)
            with open(main._RESUME_MARKER, "w") as f:
                f.write(path or "")

        # --- A: claudecode + session_id -> sambung lewat --resume ---
        r = riwayat_mod.Riwayat(folder=folder)
        r.catat("nama aku ilham", "siap dicatat")
        path_a = r.simpan(session_id="sesi-abc-123")
        _tulis_marker(path_a)

        class _OtakClaudeA:
            model = "haiku"
            dipanggil = []
            def siap(self): return True
            def muat_riwayat_id(self, sid): self.dipanggil.append(("id", sid))

        otak_a = _OtakClaudeA()
        main.otak_mod = type("M", (), {"buat_otak": staticmethod(lambda: otak_a)})()
        main._siapkan_otak()
        ok = otak_a.dipanggil == [("id", "sesi-abc-123")]
        gagal += not ok
        print(f"{'ok  ' if ok else 'GAGAL'} resume A: claudecode+session_id -> muat_riwayat_id dipanggil")

        # --- B: gemini -> replay giliran langsung, tanpa perlu session_id ---
        r = riwayat_mod.Riwayat(folder=folder)
        r.catat("halo", "hai juga")
        r.catat("siapa kamu", "aku jarvis")
        path_b = r.simpan()
        _tulis_marker(path_b)

        class _OtakGeminiB:
            model = "gemini-2.5-flash"
            dipanggil = []
            def siap(self): return True
            def muat_riwayat(self, giliran): self.dipanggil.append(giliran)

        otak_b = _OtakGeminiB()
        main.otak_mod = type("M", (), {"buat_otak": staticmethod(lambda: otak_b)})()
        main._siapkan_otak()
        ok = otak_b.dipanggil == [[("halo", "hai juga"), ("siapa kamu", "aku jarvis")]]
        gagal += not ok
        print(f"{'ok  ' if ok else 'GAGAL'} resume B: gemini -> muat_riwayat dengan giliran lengkap")

        # --- C: claudecode, transkrip LAMA tanpa session_id -> percakapan baru ---
        r = riwayat_mod.Riwayat(folder=folder)
        r.catat("test lama", "jawaban lama")
        path_c = r.simpan()
        _tulis_marker(path_c)

        class _OtakClaudeC:
            model = "haiku"
            dipanggil = []
            def siap(self): return True
            def muat_riwayat_id(self, sid): self.dipanggil.append(sid)
            # SENGAJA tidak ada muat_riwayat() - meniru OtakClaudeCode asli.

        otak_c = _OtakClaudeC()
        main.otak_mod = type("M", (), {"buat_otak": staticmethod(lambda: otak_c)})()
        main._siapkan_otak()
        ok = otak_c.dipanggil == []
        gagal += not ok
        print(f"{'ok  ' if ok else 'GAGAL'} resume C: transkrip lama tanpa session_id -> "
              "TIDAK dipaksa resume (mulai baru)")

        # --- D: otak tidak siap -> marker tetap harus kehapus, tidak nyangkut ---
        _tulis_marker(path_c)

        class _OtakTidakSiap:
            def siap(self): return False

        main.otak_mod = type("M", (), {"buat_otak": staticmethod(lambda: _OtakTidakSiap())})()
        hasil_d = main._siapkan_otak()
        ok = hasil_d is None and not os.path.exists(main._RESUME_MARKER)
        gagal += not ok
        print(f"{'ok  ' if ok else 'GAGAL'} resume D: otak tidak siap -> marker tetap terhapus")

    finally:
        main.otak_mod, main.commands = otak_mod_asli, commands_asli
        shutil.rmtree(folder, ignore_errors=True)
        try:
            os.remove(main._RESUME_MARKER)
        except OSError:
            pass

    return gagal


if __name__ == "__main__":
    raise SystemExit(run())
