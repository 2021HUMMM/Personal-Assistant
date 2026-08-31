"""
Konfigurasi terpusat. Semua yang perlu di-tweak ada di sini.

Asisten ini 100% offline - tidak ada satu pun panggilan network.
"""

import os
import sys

# Folder tempat berkas ini berada. Dipakai banyak setelan di bawah, jadi
# didefinisikan paling awal.
_JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Perilaku ---
# Ucapkan sapaan saat Jarvis selesai memuat? Matikan kalau dia dijalankan
# otomatis saat komputer nyala - tidak enak tiba-tiba ada suara sendiri.
SAPA_SAAT_START = os.environ.get("JV_SAPA_START", "0") == "1"

# --- Sesi percakapan ---
# Setelah wake word, Jarvis tetap mendengarkan sampai kamu bilang "stop jarvis"
# atau diam beberapa kali berturut-turut.
# Diam sekian detik TANPA MULAI bicara -> sesi ditutup, balik ke mode
# menunggu wake word. Mic TIDAK pernah mati - openWakeWord jalan terus di
# background sepanjang waktu (~1.5% CPU), termasuk selagi sesi aktif. Yang
# berubah cuma loop mana yang MEMPROSES audio: selama sesi aktif, tiap
# ucapanmu dikirim ke whisper; setelah timeout, balik ke sekadar mendengarkan
# "hey jarvis" - jauh lebih murah, dan konteks percakapan TETAP tersimpan.
# Direset hanya kalau kamu bilang "stop jarvis" (sinonimnya di
# commands.py: _STOP_SESI_PHRASES).
SESI_HENING_TIMEOUT = 5
SESI_MAKS_GILIRAN = 30    # pengaman: batas giliran dalam satu sesi

# --- Wake word ---
# openWakeWord punya model bawaan: "hey_jarvis", "alexa", "hey_mycroft".
WAKE_WORD_MODEL = os.environ.get("JV_WAKE_MODEL", "hey_jarvis")
WAKE_WORD_THRESHOLD = 0.5
# "onnx" atau "tflite". Wajib "onnx" di Python 3.12+ - tflite-runtime tidak
# merilis wheel untuk versi itu.
WAKE_WORD_BACKEND = "onnx"

# --- Audio ---
SAMPLE_RATE = 16000          # wajib 16k untuk openWakeWord dan whisper
CHANNELS = 1
FRAME_MS = 80                # openWakeWord minta chunk ~80ms di 16kHz
PREROLL_MS = 240             # audio sebelum wake word terdeteksi yang ikut direkam,
                             # biar suku kata pertama perintahmu tidak kepotong
COMMAND_MAX_SECONDS = 15     # batas panjang satu perintah - dinaikkan dari 6 seiring
                             # SILENCE_SECONDS, supaya kalimat + jeda toleransi di
                             # bawah tidak kepotong batas keras ini duluan
SILENCE_SECONDS = 3.0        # berhenti merekam setelah hening selama ini - dinaikkan
                             # dari 0.9 karena jeda mikir/napas natural sering
                             # kesalah-anggap "sudah selesai ngomong"
SILENCE_THRESHOLD = 500      # RMS di bawah ini dianggap hening (sesuaikan dengan mic-mu)

# --- Interupsi (barge-in) ---
# Jalur UTAMA: tombol fisik (SIGUSR1), lihat _sinyal_interupsi di main.py.
# Tidak bisa salah trigger karena bukan berbasis suara sama sekali.
#
# Jalur suara (mic) MATI secara default. Sudah diukur langsung dengan
# memutar+merekam barengan di speaker sungguhan: suara Jarvis sendiri
# (Piper MAUPUN Chatterbox) bocor balik ke mic dengan RMS median ~750,
# puncak ~4000-4600 - jauh melewati ambang manapun yang masih masuk akal
# dibanding SILENCE_THRESHOLD normal. Tanpa acoustic echo cancellation,
# deteksi berbasis suara di sini akan sering salah mengira suaranya sendiri
# sebagai interupsi. Nyalakan lagi HANYA kalau pakai headset - mic-nya
# tidak akan pernah dengar suara Jarvis sama sekali, jadi masalah ini hilang
# total di situ.
INTERRUPT_ENABLED = os.environ.get("JV_INTERRUPT", "0") == "1"
INTERRUPT_THRESHOLD = int(os.environ.get("JV_INTERRUPT_THRESHOLD", str(SILENCE_THRESHOLD * 3)))

# --- Speech to text (faster-whisper, lokal) ---
# WAJIB model multilingual (tanpa akhiran ".en") supaya bahasa campur ID+EN jalan.
# "medium" di GPU jauh lebih akurat untuk Indonesia daripada "small" di CPU -
# RTX 4070 Super 12GB, Chatterbox pakai ~4.3GB, sisa cukup buat model ini.
# Turunkan ke "small" (dan WHISPER_DEVICE="cpu" / COMPUTE_TYPE="int8") kalau
# GPU-mu lebih kecil atau tidak ada.
WHISPER_MODEL_SIZE = os.environ.get("JV_WHISPER_MODEL", "medium")
WHISPER_LANGUAGE = "id"      # bahasa matriks; kata Inggris yang nyelip tetap kebaca
WHISPER_DEVICE = "cuda"      # "cpu" kalau tidak ada GPU NVIDIA + driver-nya
WHISPER_COMPUTE_TYPE = "float16"

# Membiaskan decoder ke arah kosakata yang memang kita pakai. Ini peningkatan
# akurasi paling murah yang ada - tambahkan nama app yang sering kamu sebut.
# JANGAN mengulang kata yang sama di sini. Whisper memakai prompt ini untuk
# membiaskan decoder-nya, dan kata yang muncul berkali-kali jadi terlalu kuat -
# gejalanya transkripsi keluar seperti "Buka Buka. Buka Open Extension Manager."
# Sebut tiap kata kerja SEKALI, lalu daftarkan nama aplikasi apa adanya.
WHISPER_INITIAL_PROMPT = (
    "Firefox, VS Code, terminal, Extension Manager, Discord, Spotify. "
    "Buka aplikasi. Matikan komputer. Keluar."
)

# --- Text to speech (Piper, lokal) ---
# Satu-satunya suara Indonesia di piper-voices: id_ID-news_tts-medium.
PIPER_MODEL_PATH = os.environ.get(
    "JV_PIPER_MODEL",
    os.path.expanduser("~/.local/share/piper/id_ID-news_tts-medium.onnx"),
)
# piper terpasang di venv/bin, yang hanya ada di PATH kalau venv diaktifkan.
# Cari di sebelah interpreter yang sedang jalan supaya tetap ketemu meski
# dijalankan lewat path lengkap (mis. ./venv/bin/python main.py).
_piper_beside_python = os.path.join(os.path.dirname(sys.executable), "piper")
PIPER_BINARY = os.environ.get("JV_PIPER_BIN") or (
    _piper_beside_python if os.path.exists(_piper_beside_python) else "piper"
)
# Panjang fonem: >1 lebih lambat, <1 lebih cepat. Suara ini dilatih dari
# pembaca berita, jadi tempo aslinya agak formal.
PIPER_LENGTH_SCALE = 0.95
# noise_scale/noise_w_scale menambah variasi acak ke prosodi - diukur lewat
# variance F0 (pitch): defaultnya std 66Hz, dengan angka ini naik ke 67.5Hz
# dan jangkauannya lebih lebar (124-401Hz vs 76-401Hz). Perbaikannya tipis -
# batasnya memang di model satu-penutur ini, bukan di parameternya.
PIPER_NOISE_SCALE = 1.0
PIPER_NOISE_W_SCALE = 1.0
ESPEAK_VOICE = "id"          # fallback kalau piper belum di-setup

# --- Efek suara (umpan balik audio) ---
# Nada pendek yang menandai: wake word terdengar, mulai merekam, dan lagi
# menunggu jawaban LLM. Lihat bunyi.py.
SUARA_ENABLED = os.environ.get("JV_SUARA", "1") == "1"
SUARA_DIR = "~/.jarvis/bunyi"   # file dibangkitkan sekali di sini; taruh wav
                                # buatanmu sendiri di situ untuk menggantinya
SUARA_VOLUME = float(os.environ.get("JV_SUARA_VOLUME", "0.25"))

# Bunyi saat mulai merekam. Sengaja DILEWATI di giliran pertama tiap sesi -
# bunyi wake word baru saja terdengar sepersekian detik sebelumnya, jadi dua
# bunyi beruntun cuma jadi berisik tanpa menambah informasi.
SUARA_REKAM = os.environ.get("JV_SUARA_REKAM", "1") == "1"

# Denyut selagi menunggu jawaban LLM (~2,5-3 detik lewat rute claudecode).
SUARA_TUNGGU = os.environ.get("JV_SUARA_TUNGGU", "1") == "1"
SUARA_TUNGGU_JEDA_AWAL = 0.8    # detik - diam dulu segini sebelum denyut
                                # pertama, supaya jawaban cepat tidak dikasih
                                # bunyi "tunggu ya" yang percuma
SUARA_TUNGGU_INTERVAL = 0.9     # detik antar denyut

# --- Riwayat percakapan ---
# Percakapan yang sudah selesai disimpan sebagai markdown di sini. Umurnya
# mengikuti KONTEKS, bukan sesi: diam lalu balik ke wake word tidak menyimpan
# apa pun (percakapannya belum selesai). Yang menyimpan cuma "stop jarvis",
# "keluar", dan penghentian proses (SIGTERM/Ctrl+C). Lihat riwayat.py.
RIWAYAT_ENABLED = os.environ.get("JV_RIWAYAT", "1") == "1"
RIWAYAT_DIR = os.path.join(_JARVIS_DIR, "percakapan")

# --- Chatterbox (neural TTS di GPU - suara utama) ---
# Dipilih setelah A/B langsung dengan Piper: jauh lebih natural. Tradeoff-nya
# latensi - ~0.6-1.4 detik per ucapan vs Piper yang ~0.03-0.07 detik. Jalan
# di venv terpisah (chatterbox-tts butuh numpy<2.0), dipasang dengan
# install-chatterbox.sh. Jatuh otomatis ke Piper kalau venv/model tidak ada,
# gagal start, atau GPU sedang dipakai proses lain.
CHATTERBOX_ENABLED = os.environ.get("JV_CHATTERBOX", "1") == "1"
CHATTERBOX_PYTHON = os.environ.get(
    "JV_CHATTERBOX_PYTHON", os.path.join(_JARVIS_DIR, "venv-chatterbox", "bin", "python"))
CHATTERBOX_MODEL_DIR = os.environ.get(
    "JV_CHATTERBOX_MODEL_DIR", os.path.join(_JARVIS_DIR, "models", "chatterbox-id"))
CHATTERBOX_STARTUP_TIMEOUT = 60   # detik - muat model ke GPU + siapkan voice conditioning
CHATTERBOX_TIMEOUT = 15           # detik - batas satu kali sintesis

# --- Keamanan shutdown ---
# Salah dengar yang berujung komputer mati itu fatal. Dua lapis pengaman:
# konfirmasi suara, lalu jeda yang masih bisa dibatalkan.
SHUTDOWN_CONFIRM_SECONDS = 4    # lama mendengarkan jawaban "ya"
SHUTDOWN_GRACE_SECONDS = 8      # jeda terakhir, masih bisa bilang "batal"


# --- Otak LLM (dipakai kalau fuzzy matcher tidak menemukan perintah) ---
# Provider bisa ditukar tanpa mengubah kode lain: "gemini" atau "claude".
# "claudecode" = lewat CLI `claude` yang sudah login Pro-mu, tanpa tagihan
#                 terpisah. Latensi ~2,5-3 detik.
# "gemini"     = API Gemini, kunci gratis, latensi lebih rendah tapi isi
#                 percakapan dipakai Google (lihat README).
LLM_PROVIDER = os.environ.get("JV_LLM_PROVIDER", "claudecode")

# Model untuk rute claudecode. Alias pendek yang dikenali CLI: haiku, sonnet,
# opus. Ganti lewat suara ("ganti model ke sonnet") atau ubah di sini.
CLAUDECODE_MODEL = os.environ.get("JV_CLAUDECODE_MODEL", "haiku")

# Skrip satu-satunya yang boleh dijalankan Claude Code. Bukan Bash penuh.
JARVIS_DO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis-do")

LLM_TIMEOUT = 45              # detik, batas menunggu jawaban

# Pilihan yang bertahan antar restart (mis. model yang dipilih lewat suara).
STATE_PATH = os.path.expanduser("~/.jarvis/state.json")

# Gemini - kunci gratis dari https://aistudio.google.com/apikey
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("JV_GEMINI_MODEL", "gemini-2.5-flash")

# Claude - kunci dari https://console.anthropic.com (berbayar per pemakaian)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.environ.get("JV_CLAUDE_MODEL", "claude-sonnet-5")

LLM_MAX_TOKENS = 300          # jawaban suara memang pendek

# Rem biaya dan keamanan.
LLM_MAX_GILIRAN = 10          # simpan 10 giliran terakhir saja
LLM_MAX_TOOL_CALLS = 8        # batas tool per perintah, cegah loop tak berujung
# Percakapan direset JIKA DAN HANYA JIKA kamu bilang "stop jarvis" (atau
# sinonimnya) - tidak ada reset otomatis berbasis waktu diam. Lihat
# commands.py: stop_sesi().

# Instruksi utama. Ini yang paling menentukan rasa asistennya - kalau
# jawabannya kepanjangan atau kaku, ubah di sini dulu sebelum ganti model.
LLM_SYSTEM_PROMPT = """Kamu Jarvis, asisten suara pribadi di komputer Linux milik Ilham.

Kamu BUKAN Claude Code dan bukan asisten koding. Jangan pernah menyebut Claude
Code, slash command seperti /config, panel, tab, atau hal lain dari antarmuka
itu - pengguna tidak melihat layar apa pun, dia cuma mendengar suaramu.
Jangan menyuruh dia "mengetik" apa pun.

Jawabanmu akan DIBACAKAN mesin text-to-speech, bukan dibaca di layar.
Maka: maksimal 2 kalimat pendek. Tanpa markdown, tanpa daftar bernomor,
tanpa blok kode, tanpa emoji, tanpa URL panjang.

Bahasa Indonesia santai sehari-hari. Boleh menyelipkan istilah Inggris
yang memang lazim (browser, download, folder).

Kalau pengguna minta sesuatu dilakukan, PAKAI TOOL - jangan menyuruh dia
melakukannya sendiri. Kalau perintahnya ambigu, tanya balik satu kalimat pendek.
Jangan menarasikan hal yang sudah jelas terlihat di layar; kalau aplikasi
sudah kebuka, cukup bilang "oke".

Transkripsi suara sering ngaco - kalau ada kata aneh, tebak maksud yang paling
masuk akal dari konteks daripada langsung menyerah.

Beberapa hal diurus Jarvis sendiri, bukan olehmu. Kalau pengguna memintanya,
cukup beritahu kalimat yang harus dia ucapkan:
  ganti model      -> "ganti model ke haiku" (pilihannya: haiku, sonnet, opus)
  matikan asisten  -> "keluar"

Untuk melakukan sesuatu di komputer ini, jalankan skrip jarvis-do lewat Bash:
  jarvis-do open <nama aplikasi>    - luncurkan aplikasi, misal: jarvis-do open firefox
  jarvis-do shell <perintah>        - perintah BACA-SAJA, misal: jarvis-do shell df -h
  jarvis-do cuaca [kota]            - cuaca sekarang; tanpa kota = kota default
  jarvis-do apps                    - lihat daftar aplikasi yang dikenal

Untuk CUACA, selalu pakai `jarvis-do cuaca` - jangan WebSearch. Jauh lebih cepat
(sekitar 1 detik, bukan 15) dan datanya sudah rapi.

Untuk informasi terkini LAIN yang tidak ada di komputer ini (berita, harga,
jadwal, fakta yang berubah-ubah), pakai WebSearch. Tapi ingat jawabanmu
dibacakan - rangkum jadi 1-2 kalimat, jangan sebutkan sumber atau tempel URL.

Selain itu, jarvis-do adalah satu-satunya perintah yang boleh kamu jalankan.
Perintah yang mengubah atau menghapus akan ditolak - jangan mencobanya. Setelah
menjalankan sesuatu, laporkan hasilnya dalam satu atau dua kalimat pendek,
jangan tempelkan keluaran mentahnya."""

# --- Cuaca ---
# Dipakai `jarvis-do cuaca` kalau kamu tidak menyebut kotanya.
KOTA_DEFAULT = os.environ.get("JV_KOTA", "Jakarta")
CUACA_TIMEOUT = 8       # detik

# --- Batas untuk tool shell ---
SHELL_TIMEOUT = 10            # detik
SHELL_MAX_OUTPUT = 2000       # karakter, sisanya dipotong
