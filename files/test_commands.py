"""
Uji logika pencocokan dan alur shutdown - tanpa mic, tanpa model.

    python test_commands.py

Jalankan ini setiap kali menyentuh commands.py. Jalur shutdown yang salah
berarti kerjaan yang belum tersimpan hilang.
"""

import time

import commands
import responses

INTENT_CASES = [
    ("Buka Firefox",              "open_app", "firefox"),
    ("bukain vscode dong",        "open_app", "vscode"),
    ("Buka VS Code.",             "open_app", "vs code"),
    ("open visual studio code",   "open_app", "visual studio code"),
    ("Jarvis, buka terminal ya",  "open_app", "terminal"),
    ("nyalain spotify",           "open_app", "spotify"),
    ("buka google chrome tolong", "open_app", "google chrome"),
    # Whisper kadang tergagap dan mengulang kata kerjanya - kasus nyata dari log.
    ("Buka Buka. Buka Open Extension Manager.", "open_app", "extension manager"),
    ("buka buka firefox",         "open_app", "firefox"),
    ("buka open discord",         "open_app", "discord"),
    ("bukain bukain vs code",     "open_app", "vs code"),
    # Tapi jangan mengupas sampai habis kalau tidak ada sisa.
    ("buka run",                  "open_app", "run"),
    # Ganti model lewat suara.
    ("ganti model ke haiku",      "ganti_model", "haiku"),
    ("pakai sonnet",              "ganti_model", "sonnet"),
    ("pake opus aja",             "ganti_model", "opus"),
    # Salah dengar sudah diresolusi di tahap pencocokan, bukan di handler.
    ("ganti model ke sonet",      "ganti_model", "sonnet"),
    # Frasa dari pemakaian nyata yang sempat lolos ke LLM.
    ("Ubah model kamu ke haiku aja.", "ganti_model", "haiku"),
    ("rubah model jadi sonnet",   "ganti_model", "sonnet"),
    ("pindah ke haiku",           "ganti_model", "haiku"),
    ("model apa yang kamu pakai", "ganti_model", "?"),
    # Yang TIDAK boleh dianggap ganti model.
    ("buka model 3d",             "open_app",    "model 3d"),
    ("ganti volume",              None,          None),
    # Dua aksi dalam satu kalimat harus ke LLM - jalur cepat cuma bisa satu,
    # dan diam-diam membuang aksi kedua.
    ("buka firefox terus matiin spotify", None, None),
    ("buka firefox lalu buka discord",    None, None),
    ("buka vscode sekalian terminal",     None, None),
    # "jarvis" cuma dibuang sebagai sapaan kalau di AWAL kalimat - kalau di
    # tengah/ekor kalimat "buka X", itu ISI (nama proyek), bukan sapaan.
    ("buka project jarvis",       "open_app",  "project jarvis"),
    ("buka jarvis",               "open_app",  "jarvis"),
    ("jarvis, buka firefox",      "open_app",  "firefox"),
    # Tapi tetap tersapa dengan benar di frasa perpisahan/sesi.
    ("sampai jumpa jarvis",       "stop_sesi", None),
    ("stop jarvis",               "stop_sesi", None),
    ("matikan jarvis",            "quit",      None),
    # "main"/"mainin" khusus buat game - lebih natural daripada "buka".
    ("main cyberpunk",            "open_app",  "cyberpunk"),
    ("mainin hogwarts legacy",    "open_app",  "hogwarts legacy"),
    # "pakai X" hanya ditangkap kalau X memang nama model.
    ("pakai firefox",             None,       None),
    ("Matikan komputer",          "shutdown", None),
    ("matiin komputer dong",      "shutdown", None),
    ("shut down",                 "shutdown", None),
    ("matikan laptop",            "shutdown", None),
    # Tutup SESI (Jarvis balik menunggu wake word, program tetap jalan).
    ("stop jarvis",               "stop_sesi", None),
    ("stop",                      "stop_sesi", None),
    ("udah cukup",                "stop_sesi", None),
    ("makasih",                   "stop_sesi", None),
    ("sampai jumpa jarvis",       "stop_sesi", None),
    # Matikan PROGRAM (butuh systemctl untuk menyalakan lagi).
    ("Keluar",                    "quit",     None),
    ("matikan jarvis",            "quit",     None),
    ("matikan asisten",           "quit",     None),
    # Tidak boleh salah tangkap.
    ("stop musiknya",             None,       None),
    # Yang tidak boleh mematikan komputer:
    ("matikan musik",             None,       None),
    ("matikan lampu",             None,       None),
    ("cuaca hari ini gimana",     None,       None),
    ("",                          None,       None),
]

SHUTDOWN_CASES = [
    ("ya",            "",               True),
    ("iya dong",      "",               True),
    ("oke gas",       "",               True),
    ("ya",            "batal",          False),
    ("iya",           "eh jangan deh",  False),
    ("kucing",        "",               False),
    ("",              "",               False),
    ("jangan",        "",               False),
    ("nggak jadi",    "",               False),
]


class _FakeCtx:
    def __init__(self, replies):
        self._replies = list(replies)

    def speak(self, _text):
        pass

    def listen(self, _seconds):
        return self._replies.pop(0) if self._replies else ""


# Placeholder yang tersedia untuk tiap key. Varian yang memakai placeholder
# di luar daftarnya akan meledak dengan KeyError saat dipakai sungguhan.
RESPONSE_ARGS = {
    "siap": {},
    "membuka": {"app": "Firefox"},
    "app_mana": {},
    "app_gaada": {"app": "Spotify"},
    "gangerti": {},
    "shutdown_yakin": {},
    "shutdown_jeda": {"detik": 8},
    "shutdown_gagal": {},
    "model_diganti": {"model": "haiku"},
    "sesi_selesai": {},
    "batal": {},
    "dadah": {},
}


def _check_responses() -> int:
    """Tiap varian harus bisa diformat, dan pick() tidak boleh mengulang."""
    failures = 0

    belum_diuji = set(responses.BANK) - set(RESPONSE_ARGS)
    if belum_diuji:
        failures += 1
        print(f"GAGAL response key tanpa argumen di RESPONSE_ARGS: {belum_diuji}")

    for key, args in RESPONSE_ARGS.items():
        if key not in responses.BANK:
            failures += 1
            print(f"GAGAL response key {key!r} tidak ada di BANK")
            continue
        for varian in responses.BANK[key]:
            try:
                varian.format(**args, sapaan="Pagi")
            except (KeyError, IndexError) as e:
                failures += 1
                print(f"GAGAL response {key}: {varian!r} -> {type(e).__name__}: {e}")

    # Tidak boleh mengulang varian yang sama dua kali berturut-turut.
    for key, args in RESPONSE_ARGS.items():
        if len(responses.BANK[key]) < 2:
            continue
        sebelumnya = None
        for _ in range(60):
            sekarang = responses.pick(key, **args)
            if sekarang == sebelumnya:
                failures += 1
                print(f"GAGAL response {key}: mengulang {sekarang!r} berturut-turut")
                break
            sebelumnya = sekarang

    if not failures:
        total = sum(len(v) for v in responses.BANK.values())
        print(f"ok   responses {len(responses.BANK)} key, {total} varian, tanpa pengulangan beruntun")
    return failures


def _check_resolve_app() -> int:
    """
    _resolve_app(): nama aplikasi yang SPESIFIK harus menang atas kata
    generik yang kebetulan nempel di ucapan yang sama. Kejadian nyata: "open
    brave browser" dibuka jadi Firefox, karena "browser" (alias generik ->
    firefox) adalah SUBSTRING dari yang diucapkan, jadi aturan bonus
    substring memberi skor tinggi ke alias generik itu duluan.

    aplikasi.cari() DIGANTI TIRUAN di sini, bukan pakai instalasi sungguhan -
    supaya lolos-tidaknya tidak bergantung Brave (atau apa pun) beneran
    terpasang di mesin yang menjalankan tes ini.
    """
    failures = 0
    asli = commands.aplikasi.cari

    def cari_tiruan(nama, ambang=0.72):
        # Meniru perilaku aplikasi.cari() sungguhan: exact/substring match
        # ke satu "aplikasi terpasang" bernama Brave.
        if nama == "brave" or "brave" in nama:
            return (["/usr/bin/brave-browser-stable"], "Brave Web Browser")
        return None

    commands.aplikasi.cari = cari_tiruan
    try:
        kasus = [
            # (ucapan mentah setelah "buka", label yang DIHARAPKAN menang)
            ("brave browser", "Brave Web Browser"),  # kasus nyata yang gagal
            ("brave", "Brave Web Browser"),
            # Alias generik POLOS (tanpa merek lain nempel) tetap harus jalan
            # seperti biasa - regresi yang harus tetap dijaga.
            ("browser", "browser"),
            ("peramban", "peramban"),
        ]
        for arg, label_diharap in kasus:
            _cmd, label = commands._resolve_app(arg)
            ok = label == label_diharap
            failures += not ok
            print(f"{'ok  ' if ok else 'GAGAL'} _resolve_app({arg!r}) -> "
                  f"{label!r} (harus {label_diharap!r})")
    finally:
        commands.aplikasi.cari = asli

    return failures


def run() -> int:
    failures = 0

    for text, want_intent, want_arg in INTENT_CASES:
        got = commands.match(text)
        intent = got[0] if got else None
        arg = got[2] if got else None
        ok = intent == want_intent and (want_arg is None or arg == want_arg)
        failures += not ok
        print(f"{'ok  ' if ok else 'GAGAL'} match {text!r:32} -> {intent} {arg!r}")

    # Cegah shutdown beneran, dan lewati jeda.
    real_poweroff, real_sleep = commands._poweroff, time.sleep
    commands._poweroff = lambda: "POWEROFF"
    time.sleep = lambda _s: None
    try:
        for confirm, grace, should_power_off in SHUTDOWN_CASES:
            result = commands.shutdown(_FakeCtx([confirm, grace]), None)
            powered = "POWEROFF" in (result or "")
            ok = powered == should_power_off
            failures += not ok
            print(f"{'ok  ' if ok else 'GAGAL'} shutdown {confirm!r:14} / {grace!r:16} "
                  f"-> {'MATI' if powered else 'batal'}")
    finally:
        commands._poweroff, time.sleep = real_poweroff, real_sleep

    failures += _check_responses()
    failures += _check_resolve_app()

    total = len(INTENT_CASES) + len(SHUTDOWN_CASES) + 1 + 4
    print(f"\n{total - failures}/{total} lolos")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run())
