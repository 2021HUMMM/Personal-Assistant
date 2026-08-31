"""
Registry perintah lokal.

Pencocokan di sini sengaja TIDAK memakai regex ketat. Untuk bahasa campur
Indonesia + Inggris, whisper akan mengeluarkan puluhan variasi untuk maksud
yang sama - "buka VS Code", "bukain vscode dong", "open visual studio code".
Regex berjangkar (^...$) gagal di hampir semuanya. Jadi: normalisasi teks,
kupas kata pemicu, lalu cocokkan sisanya secara fuzzy.

Menambah aplikasi: tambahkan entri di APP_ALIASES. Itu saja.
"""

import difflib
import json
import os
import re
import shutil
import subprocess
import threading
import time

import aplikasi

import config
import responses

# Nama yang kamu ucapkan -> perintah yang benar-benar dijalankan.
# Kunci boleh lebih dari satu untuk satu aplikasi; semuanya ikut dicocokkan fuzzy.
APP_ALIASES = {
    "firefox": "firefox",
    # Sebutan generik ("buka browser", "buka peramban") default ke Brave -
    # Firefox cuma kalau memang disebut namanya persis.
    "browser": "/usr/bin/brave-browser-stable",
    "peramban": "/usr/bin/brave-browser-stable",
    "chrome": "google-chrome",
    "google chrome": "google-chrome",
    "terminal": "x-terminal-emulator",
    "konsol": "x-terminal-emulator",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "kode": "code",
    "file manager": "nautilus",
    "berkas": "nautilus",
    "spotify": "spotify",
    "extension manager": "extension-manager",
    "ekstensi": "extension-manager",
    "discord": "discord",
    "kalkulator": "gnome-calculator",
    "calculator": "gnome-calculator",
    "pengaturan": "gnome-control-center",
    "settings": "gnome-control-center",
}

# Folder proyek yang sering dibuka di editor. Beda dari APP_ALIASES: yang
# dicari di sini bukan nama aplikasi, tapi nama proyek - dan hasilnya butuh
# ARGUMEN (path folder), bukan cuma nama binary. "buka project jarvis" ->
# `code ~/Documents/jarvis/files`.
#
# Tambah proyek baru: satu baris, key = nama yang mau diucapkan.
PROJECT_ALIASES = {
    # ~/Documents/jarvis/files, BUKAN ~/Documents/jarvis - VS Code (dan
    # extension Claude Code-nya) menyimpan riwayat sesi per FOLDER WORKSPACE
    # PERSIS. Folder induk vs subfolder dianggap dua workspace yang beda
    # sama sekali walau "proyek yang sama" buat manusia - riwayat sesi yang
    # sedang jalan di files/ tidak akan kelihatan kalau yang dibuka cuma
    # folder induknya.
    "project jarvis": os.path.expanduser("~/Documents/jarvis/files"),
    "jarvis": os.path.expanduser("~/Documents/jarvis/files"),
}
PROJECT_EDITOR = "code"  # binary yang dipakai membuka semua PROJECT_ALIASES
# Tanpa -n, `code <folder>` bisa MEMAKAI ULANG jendela yang sedang aktif,
# bukan buka yang baru - default persis begini: "-n --new-window  Force to
# open a new window" (baca: tanpa flag ini, tidak dipaksa). Kejadian nyata:
# "buka project jarvis" mengganti workspace jendela yang lagi dipakai (yang
# lagi menjalankan percakapan dengan Claude Code ini sendiri), bukan buka
# jendela terpisah - percakapannya kelihatan hilang karena jendelanya
# reload ke workspace baru. Voice command buat "buka proyek" seharusnya
# tidak pernah mengganggu jendela yang sedang dipakai.
PROJECT_FLAGS = ["-n"]

# Website yang bukan aplikasi terpasang, jadi tidak akan pernah ketemu lewat
# aplikasi.cari() atau APP_ALIASES apa pun - "buka youtube"/"buka email" itu
# maksudnya buka BROWSER ke alamat tertentu, bukan mencari binary bernama
# "youtube". Dibuka lewat xdg-open (pembuka URL bawaan sistem, pakai browser
# default) - ini juga kenapa tool LLM `buka_website` di tools.py ada, buat
# alamat apa pun yang tidak masuk daftar kurasi kecil ini.
WEB_ALIASES = {
    "youtube": "https://youtube.com",
    "email": "https://mail.google.com",
    "gmail": "https://mail.google.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "whatsapp web": "https://web.whatsapp.com",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
    "kalender": "https://calendar.google.com",
    "calendar": "https://calendar.google.com",
    "github": "https://github.com",
}

# Kata kerja pembuka. Yang tersisa setelah kata ini dianggap nama aplikasi.
_OPEN_TRIGGERS = (
    "bukakan", "bukain", "buka", "jalankan", "jalanin", "nyalain",
    "hidupkan", "launch", "open", "start", "run",
    # "main"/"mainin" khusus buat game - "main cyberpunk" lebih natural
    # diucapkan daripada "buka cyberpunk", walau dua-duanya jalan.
    "main", "mainin", "maen", "maenin", "play",
)

# Kata pengisi yang tidak membawa makna - dibuang sebelum pencocokan.
_FILLERS = {
    "hey", "hei", "dong", "ya", "yah", "deh", "tolong", "coba",
    "please", "the", "app", "aplikasi", "program", "gue", "aku", "saya",
    "punya", "itu", "ini", "nya", "aja", "saja", "sih", "kamu", "kau", "lu",
}

# "jarvis" dibuang cuma kalau posisinya di AWAL kalimat - itu artinya kamu
# menyapa ("Jarvis, buka firefox" -> "buka firefox"). Kalau diperlakukan
# sebagai kata pengisi biasa (dibuang di mana pun ia muncul), "buka project
# jarvis" ikut kepotong jadi "buka project" - proyek bernama "jarvis" jadi
# mustahil dibuka. Lihat PROJECT_ALIASES di bawah.
_ALAMAT_DEPAN = {"jarvis"}

_AFFIRMATIVE = {"ya", "iya", "yes", "yoi", "betul", "benar", "bener", "lanjut",
                "oke", "ok", "okay", "gas", "sip", "yup", "yoi"}

_CANCEL = {"batal", "batalkan", "cancel", "jangan", "tidak", "ga", "gak",
           "nggak", "engga", "enggak", "stop", "no", "gajadi"}

# Frasa untuk mematikan komputer. Harus mengandung salah satu kata sasaran
# di _SHUTDOWN_OBJECTS supaya "matikan musik" tidak pernah mematikan PC.
_SHUTDOWN_PHRASES = (
    "matikan komputer", "matiin komputer", "matikan laptop", "matiin laptop",
    "matikan pc", "shutdown", "shut down", "power off", "poweroff",
)
_SHUTDOWN_OBJECTS = ("komputer", "laptop", "pc", "shutdown", "shut", "power", "poweroff")

# Menutup SESI percakapan - Jarvis balik tidur, tapi programnya tetap jalan.
# Ini yang paling sering diucapkan, jadi variasinya banyak.
_STOP_SESI_PHRASES = ("stop jarvis", "stop", "udah", "udahan", "sudah",
                      "cukup", "udah cukup", "sudah cukup", "selesai",
                      "makasih", "terima kasih", "thanks", "oke makasih",
                      "berhenti", "sampai jumpa", "dadah", "bye", "diam dulu")

# Mematikan PROGRAM Jarvis sepenuhnya. Sengaja dibedakan tegas dari stop sesi -
# ini butuh dijalankan ulang lewat systemctl, jadi tidak boleh kepencet
# tidak sengaja.
_QUIT_PHRASES = ("keluar", "matikan asisten", "matiin asisten",
                 "matikan jarvis", "matiin jarvis", "exit", "quit")

# Model yang bisa dipilih lewat suara. Kunci = yang kamu ucapkan.
MODEL_ALIASES = {
    "haiku": "haiku",
    "haik": "haiku",
    "sonet": "sonnet",
    "sonnet": "sonnet",
    "sonnet 5": "sonnet",
    "opus": "opus",
    "opas": "opus",
}

# Mendaftar frasa satu per satu tidak ada habisnya - "ganti model ke X",
# "ubah model kamu jadi X", "pindah ke X"... Jadi dideteksi dari unsurnya:
# kata kerja ganti + kata "model" + nama model, bukan dari urutan katanya.
_VERBA_GANTI = ("ganti", "ubah", "pindah", "pakai", "pake", "gunakan",
                "tukar", "switch", "set", "rubah")
_KATA_TANYA = ("apa", "apaan", "mana", "berapa")

# Kata sambung yang menandakan ada aksi KEDUA dalam satu kalimat. Jalur cepat
# cuma bisa satu aksi, jadi kalimat begini harus diserahkan ke LLM - kalau tidak,
# aksi keduanya hilang diam-diam.
_KATA_SAMBUNG = ("terus", "lalu", "kemudian", "abis itu", "habis itu",
                 "sekalian", "sambil", "then", "dan juga", "trus")


# --------------------------------------------------------------------------
# Normalisasi
# --------------------------------------------------------------------------

def normalize(text: str, strip_fillers: bool = True) -> str:
    """
    strip_fillers=False dipakai saat membaca jawaban konfirmasi: di sana "ya"
    adalah jawabannya, bukan kata pengisi.
    """
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    words = text.split()
    if strip_fillers:
        words = [w for w in words if w not in _FILLERS]
        while words and words[0] in _ALAMAT_DEPAN:
            words.pop(0)
    return " ".join(words)


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _contains_any(text: str, phrases) -> bool:
    return any(p in text for p in phrases)


# --------------------------------------------------------------------------
# Handler
# --------------------------------------------------------------------------

def open_app(ctx, spoken_name: str) -> str:
    """Luncurkan aplikasi berdasarkan nama yang diucapkan."""
    if not spoken_name:
        return responses.pick("app_mana")

    command, matched = _resolve_app(spoken_name)
    label = matched or spoken_name

    if shutil.which(command[0]):
        _luncurkan(command)
        return responses.pick("membuka", app=label)

    # Banyak aplikasi hanya punya file .desktop, bukan binary di PATH. Ini
    # jaring pengaman terakhir - aplikasi.cari() sudah membaca .desktop
    # secara langsung, jadi jarang sampai ke sini kecuali file-nya di luar
    # folder yang kita telusuri.
    if len(command) == 1 and shutil.which("gtk-launch"):
        _luncurkan(["gtk-launch", command[0]])
        return responses.pick("membuka", app=label)

    # Tidak ketemu. Kembalikan None, bukan pesan error - biar pemanggil yang
    # memutuskan. Kalau LLM aktif, permintaan seperti "buka yang buat edit foto"
    # lebih baik diserahkan ke sana daripada dijawab "nggak nemu".
    print(f"[hint] {command!r} tidak ada di PATH dan tidak punya .desktop.")
    return None


def _luncurkan(command):
    """
    Jalankan `command` di luar cgroup Jarvis sendiri, lewat
    `systemd-run --user --scope`.

    Kenapa ini wajib, bukan sekadar subprocess.Popen() biasa: proses yang
    dibuat lewat Popen() dari dalam jarvis.service otomatis ikut masuk cgroup
    MILIK jarvis.service. Unit-nya diset KillMode=control-group (perlu, biar
    subprocess internal semacam Chatterbox ikut bersih saat Jarvis berhenti) -
    tapi itu juga berarti APLIKASI YANG KAMU BUKA lewat suara ikut kena
    SIGTERM kalau Jarvis restart atau di-stop.

    Ini bukan teori - kejadian nyata: Steam yang lagi update diri sendiri
    kena bunuh gara-gara Jarvis restart di tengah jalan, bikin state Steam
    rusak ("didn't shutdown cleanly") dan siklusnya berulang tiap kali dicoba
    lagi. systemd-run --scope menaruh proses baru ke SCOPE UNIT-nya SENDIRI,
    lepas total dari cgroup Jarvis - restart/stop Jarvis tidak akan pernah
    menyentuhnya lagi.
    """
    if shutil.which("systemd-run"):
        subprocess.Popen(
            ["systemd-run", "--user", "--scope", "--collect", "--", *command],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        # Jaring pengaman kalau systemd-run entah kenapa tidak ada. Tetap
        # detach dari process GROUP kita - tidak selengkap systemd-run
        # (cgroup tetap ikut), tapi lebih baik daripada tidak sama sekali.
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)


def _resolve_app(spoken_name: str):
    """
    Kembalikan (command_list, nama_yang_cocok). Urutan pencarian:

      1. APP_ALIASES, HANYA cocok PERSIS - kurasi manual eksplisit
         ("peramban" -> firefox) menang mutlak kalau memang itu yang diucapkan
         apa adanya.
      2. PROJECT_ALIASES - daftar KECIL yang sengaja kamu kurasi sendiri buat
         buka folder proyek ("buka project jarvis" -> `code ~/Documents/jarvis`).
         Dicek SEBELUM aplikasi.cari() - lihat alasan di bawah.
      3. WEB_ALIASES - sama-sama daftar kurasi eksplisit, tapi buat WEBSITE
         ("buka youtube" -> browser ke youtube.com). Ini TIDAK PERNAH bisa
         ketemu lewat aplikasi.cari() (bukan aplikasi terpasang) atau
         APP_ALIASES (bukan nama binary), jadi urutannya di sini tidak
         sebentrok PROJECT_ALIASES - tetap dicek di tingkat yang sama biar
         konsisten sebagai "kurasi eksplisit".
      4. aplikasi.cari() - baca LANGSUNG dari sistem: semua .desktop yang
         terpasang, plus game Steam lewat libraryfolders.vdf.
      5. APP_ALIASES yang fuzzy - jaring pengaman buat salah dengar ringan
         dari alias yang memang terdaftar ("vs kod" -> "vs code").
      6. Tebakan terakhir: nama mentahnya sebagai binary. Cukup sering
         berhasil untuk aplikasi command-line sederhana.

    Dua kejadian nyata yang bentrok dan kenapa urutannya begini:

    - "open brave browser" dibuka jadi Firefox: kata "browser" (alias
      generik -> firefox) SUBSTRING dari yang diucapkan, bonus substring
      kasih skor tinggi ke alias generik itu. Makanya aplikasi.cari() (nama
      SPESIFIK apa pun yang ada di sistem) dicek sebelum APP_ALIASES fuzzy.

    - "buka project jarvis" malah membuka jarvis_gui.py: setelah perbaikan di
      atas, aplikasi.cari('jarvis') kebetulan nemu .desktop milik jarvis_gui.py
      SENDIRI (Name=Jarvis, dipasang pasang-gui.sh) - menang atas
      PROJECT_ALIASES yang justru itu yang kamu maksud. PROJECT_ALIASES itu
      daftar kecil yang kamu kurasi SENGAJA, beda konteks dari aplikasi.cari()
      yang menemukan sesuatu secara KEBETULAN - jadi kurasi eksplisit menang.
    """
    if spoken_name in APP_ALIASES:
        return [APP_ALIASES[spoken_name]], spoken_name

    key_proyek, skor_proyek = _cocokkan_dict(spoken_name, PROJECT_ALIASES)
    if skor_proyek >= 0.72:
        return [PROJECT_EDITOR, *PROJECT_FLAGS, PROJECT_ALIASES[key_proyek]], key_proyek

    key_web, skor_web = _cocokkan_dict(spoken_name, WEB_ALIASES)
    if skor_web >= 0.72:
        return ["xdg-open", WEB_ALIASES[key_web]], key_web

    ditemukan = aplikasi.cari(spoken_name)
    if ditemukan is not None:
        return ditemukan

    best_key, best_score = _cocokkan_dict(spoken_name, APP_ALIASES)
    if best_score >= 0.72:
        return [APP_ALIASES[best_key]], best_key

    # Terakhir: coba nama mentahnya sebagai binary. Cukup sering berhasil.
    return [spoken_name.replace(" ", "-")], None


def _cocokkan_dict(spoken_name: str, kamus: dict):
    """Fuzzy match nama_ucapan ke key kamus. Kembalikan (key_terbaik, skor)."""
    best_key, best_score = None, 0.0
    for key in kamus:
        score = _similar(spoken_name, key)
        # Substring dianggap cocok kuat: "visual studio" -> "visual studio code"
        if key in spoken_name or spoken_name in key:
            score = max(score, 0.9)
        if score > best_score:
            best_key, best_score = key, score
    return best_key, best_score


def shutdown(ctx, _arg=None) -> str:
    """
    Matikan komputer - dengan dua lapis pengaman.

    Salah dengar yang berujung PC mati itu kehilangan kerjaan yang belum
    tersimpan. Butuh konfirmasi eksplisit, lalu masih ada jeda untuk membatalkan.
    Kalau jawabannya tidak jelas, defaultnya selalu BATAL.
    """
    ctx.speak(responses.pick("shutdown_yakin"))
    reply = normalize(ctx.listen(config.SHUTDOWN_CONFIRM_SECONDS), strip_fillers=False)
    print(f"[konfirmasi] {reply!r}")

    if not reply or not (set(reply.split()) & _AFFIRMATIVE):
        return responses.pick("batal")

    ctx.speak(responses.pick("shutdown_jeda", detik=config.SHUTDOWN_GRACE_SECONDS))
    grace = normalize(ctx.listen(config.SHUTDOWN_GRACE_SECONDS), strip_fillers=False)
    print(f"[jeda] {grace!r}")

    if set(grace.split()) & _CANCEL:
        return responses.pick("batal")

    ctx.speak(responses.pick("dadah"))
    time.sleep(0.5)   # beri waktu TTS selesai sebelum sesi dimatikan
    return _poweroff()


def _poweroff() -> str:
    for cmd in (["systemctl", "poweroff"], ["shutdown", "-h", "now"], ["loginctl", "poweroff"]):
        try:
            subprocess.run(cmd, check=True)
            return ""
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return responses.pick("shutdown_gagal")


def ganti_model(ctx, nama: str) -> str:
    """Ganti model LLM saat berjalan, tanpa restart Jarvis."""
    otak = getattr(ctx, "otak", None)
    if otak is None:
        return "Otaknya lagi nggak aktif, jadi nggak ada model buat diganti."
    if not hasattr(otak, "ganti_model"):
        return "Provider yang dipakai sekarang nggak bisa ganti model."

    sekarang = getattr(otak, "model", None)
    if nama == "?":
        return f"Sekarang pakai {sekarang}." if sekarang else "Nggak tahu modelnya."

    model = _cocokkan_model(nama) if nama else None
    if model is None:
        pilihan = ", ".join(sorted(set(MODEL_ALIASES.values())))
        return f"Nggak kenal model itu. Yang ada: {pilihan}."
    if model == sekarang:
        return f"Udah pakai {model} kok."

    otak.ganti_model(model)
    _simpan_pilihan_model(model)
    return responses.pick("model_diganti", model=model)


def _cocokkan_model(nama: str, ambang: float = 0.7):
    nama = (nama or "").strip().lower()
    if not nama:
        return None
    if nama in MODEL_ALIASES:
        return MODEL_ALIASES[nama]
    terbaik, skor = None, 0.0
    for k, v in MODEL_ALIASES.items():
        r = _similar(nama, k)
        if r > skor:
            terbaik, skor = v, r
    return terbaik if skor >= ambang else None


def _cari_nama_model(kata):
    """Cari nama model di mana pun dalam kalimat. Ambang ketat supaya kata
    biasa tidak salah dianggap nama model."""
    for w in kata:
        m = _cocokkan_model(w, ambang=0.85)
        if m:
            return m
    return None


def _niat_model(norm: str):
    """
    Kembalikan nama model kalau ini permintaan ganti model,
    "?" kalau ini pertanyaan model apa yang dipakai,
    "" kalau jelas mau ganti tapi modelnya tidak dikenal,
    None kalau bukan soal model sama sekali.
    """
    kata = norm.split()
    if not kata:
        return None

    ada_kata_model = "model" in kata
    ada_verba = kata[0] in _VERBA_GANTI
    ditemukan = _cari_nama_model(kata)

    # "model apa yang dipakai sekarang"
    if ada_kata_model and any(t in kata for t in _KATA_TANYA):
        return "?"
    # "ubah model kamu ke haiku" - kata "model" bikin maksudnya jelas
    if ada_kata_model and (ada_verba or ditemukan):
        return ditemukan if ditemukan else ""
    # "pakai haiku" - tanpa kata "model", jadi butuh nama model yang jelas
    if ada_verba and ditemukan:
        return ditemukan
    return None


def _simpan_pilihan_model(model: str):
    """Ingat pilihannya supaya bertahan setelah Jarvis di-restart."""
    try:
        os.makedirs(os.path.dirname(config.STATE_PATH), exist_ok=True)
        with open(config.STATE_PATH, "w") as f:
            json.dump({"model": model}, f)
    except OSError as e:
        print(f"[warn] gagal menyimpan pilihan model: {e}")


def muat_pilihan_model():
    """Dipakai main.py saat start. Kembalikan None kalau belum pernah diset."""
    try:
        with open(config.STATE_PATH) as f:
            return json.load(f).get("model")
    except (OSError, ValueError):
        return None


def stop_sesi(ctx, _arg=None) -> str:
    """
    Tutup sesi percakapan DAN reset konteksnya.

    Ini satu-satunya jalan konteks di-reset - diam sampai mic nonaktif TIDAK
    mereset apa pun, cuma menghentikan pendengaran aktif. Jadi kalau kamu
    panggil lagi nanti, Jarvis masih ingat obrolan sebelumnya, kecuali kamu
    memang bilang ini.
    """
    otak = getattr(ctx, "otak", None)
    if otak is not None:
        otak.reset_percakapan()
    return responses.pick("sesi_selesai")


def quit_assistant(ctx, _arg=None) -> str:
    return responses.pick("dadah")


# --------------------------------------------------------------------------
# Pencocokan maksud
# --------------------------------------------------------------------------

def match(text: str):
    """
    Kembalikan (nama_intent, handler, argumen) atau None kalau tidak ada
    yang cocok. Urutan penting: yang paling spesifik lebih dulu.
    """
    norm = normalize(text)
    if not norm:
        return None

    # Versi tanpa kata pengisi dibuang. Dibutuhkan karena "jarvis" itu kata
    # pengisi, padahal "matikan jarvis" maksudnya beda jauh dari "matikan".
    norm_utuh = normalize(text, strip_fillers=False)

    words = norm.split()

    # 1. Matikan komputer. Sengaja ketat - butuh kata sasaran yang eksplisit.
    if any(obj in words or obj in norm for obj in _SHUTDOWN_OBJECTS):
        if _contains_any(norm, _SHUTDOWN_PHRASES):
            return ("shutdown", shutdown, None)
        if max((_similar(norm, p) for p in _SHUTDOWN_PHRASES), default=0.0) >= 0.8:
            return ("shutdown", shutdown, None)

    # 2. Soal model. Dicek sebelum quit supaya "pakai opus" tidak salah tangkap.
    niat = _niat_model(norm)
    if niat is not None:
        return ("ganti_model", ganti_model, niat)

    # 3. Matikan program sepenuhnya. Dicek sebelum stop sesi karena lebih spesifik.
    if _contains_any(norm_utuh, _QUIT_PHRASES):
        return ("quit", quit_assistant, None)

    # 3b. Tutup sesi percakapan saja - Jarvis balik menunggu wake word.
    # "jarvis" di ekor kalimat perpisahan ("sampai jumpa jarvis", "makasih
    # jarvis") itu menyapa, bukan bagian dari maksudnya - beda kasus dari
    # "buka project jarvis" di bawah, di mana "jarvis" memang isi/argumennya.
    # Makanya cuma dilepas di sini, secara lokal, bukan di normalize().
    #
    # Kata terakhir dibandingkan FUZZY ke "jarvis" (bukan persis) - kejadian
    # nyata (dua kali): "stop jarvis" ke-transkrip Whisper jadi "stop
    # jarakis" dan "stop dervis" ("Jarvis" itu nama buatan, gampang salah
    # dengar). Perbandingan persis bikin dua-duanya lolos ke LLM, yang tidak
    # punya cara benerin sesi (cuma bisa saran "keluar", padahal itu MATIKAN
    # program, beda jauh dari maksud "stop jarvis" yang cuma nutup sesi).
    norm_tanpa_sapaan_ekor = norm
    if words and _similar(words[-1], "jarvis") >= 0.6:
        norm_tanpa_sapaan_ekor = " ".join(words[:-1])
    if (norm in _STOP_SESI_PHRASES or norm_tanpa_sapaan_ekor in _STOP_SESI_PHRASES
            or _contains_any(norm, ("stop jarvis", "udah cukup"))):
        return ("stop_sesi", stop_sesi, None)

    # 4. Buka aplikasi - tapi hanya kalau cuma ada SATU aksi. Kalimat dengan
    #    kata sambung ("buka firefox terus matiin spotify") diserahkan ke LLM,
    #    karena jalur cepat akan diam-diam mengerjakan yang pertama saja.
    if _ada_aksi_ganda(norm):
        return None

    for trigger in _OPEN_TRIGGERS:
        if norm.startswith(trigger + " "):
            return ("open_app", open_app, _strip_repeated_triggers(norm[len(trigger):].strip()))
        if norm == trigger:
            return ("open_app", open_app, "")

    return None


def _ada_aksi_ganda(norm: str) -> bool:
    kata = norm.split()
    for sambung in _KATA_SAMBUNG:
        bagian = sambung.split()
        for i in range(len(kata) - len(bagian) + 1):
            # Kata sambung di awal kalimat bukan penanda aksi kedua.
            if i > 0 and kata[i:i + len(bagian)] == bagian:
                return True
    return False


def _strip_repeated_triggers(text: str) -> str:
    """
    Buang kata kerja pembuka yang menempel berulang di depan.

    Whisper kadang tergagap dan mengeluarkan "buka buka open extension manager".
    Tanpa ini, seluruh rangkaian itu dianggap nama aplikasi.

    Hanya mengupas kalau masih ada sisa - supaya "buka run" tetap mencari
    aplikasi bernama "run", bukan jadi string kosong.
    """
    changed = True
    while changed:
        changed = False
        for trigger in _OPEN_TRIGGERS:
            if text.startswith(trigger + " "):
                text = text[len(trigger):].strip()
                changed = True
                break
    return text
