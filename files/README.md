# Jarvis

Asisten suara lokal untuk Linux. Wake word, speech-to-text, dan text-to-speech
semuanya jalan **di mesin sendiri** — suaramu tidak pernah dikirim ke mana pun.
Yang keluar cuma teks hasil transkripsi, itu pun hanya kalau perintahnya tidak
dikenali jalur cepat lokal (lihat [Otak LLM](#otak-llm)).

```
Mic → wake word (lokal) → speech-to-text (lokal) → cocokkan maksud → jalankan
```

| Perintah | Contoh ucapan |
|---|---|
| Buka aplikasi | "buka firefox", "bukain vscode dong", "nyalain spotify" |
| Cuaca | "cuaca hari ini gimana", "cuaca di Bandung" |
| Buka proyek di editor | "buka project jarvis" |
| Matikan komputer | "matikan komputer", "matiin laptop", "shut down" |
| Ganti model | "ganti model ke sonnet", "pakai haiku" |
| Tutup sesi | "stop jarvis", "udah", "cukup", "makasih" |
| Matikan program | "matikan jarvis", "keluar", "exit" |

## Mode percakapan

Wake word cukup **sekali**. Setelah itu Jarvis terus mendengarkan sampai kamu
menutup sesinya:

```
kamu    : "hey jarvis"
kamu    : "buka firefox"
jarvis  : "Oke."
kamu    : "sekalian discord"        ← tanpa wake word lagi
jarvis  : "Siap."
kamu    : "sisa disk berapa?"
jarvis  : "Masih 123 giga."
kamu    : "udah, makasih"
jarvis  : "Sip."                    ← sesi ditutup, balik menunggu wake word
```

**Penting: mic tidak pernah mati.** Satu stream audio dibuka sekali dan tetap
hidup selama Jarvis berjalan; wake word ("hey jarvis") selalu bisa dideteksi
kapan saja, termasuk selagi sesi sedang berlangsung. Yang berubah cuma loop
mana yang MEMPROSES suara itu — selama sesi aktif, tiap ucapanmu dikirim ke
whisper untuk ditranskripsi; setelah diam terlalu lama, itu berhenti dan
balik ke sekadar mendengarkan wake word, jauh lebih murah.

**Dua hal yang beda dan sengaja dipisah:**

| | Sesi (kirim ke whisper) berhenti | Konteks percakapan direset |
|---|---|---|
| Diam `SESI_HENING_TIMEOUT` detik (default 5) | ya — balik ke mode wake word | **tidak** |
| Bilang "stop jarvis" / "udah" / "cukup" / "makasih" / "sampai jumpa" | ya | **ya** |
| Batas 30 giliran (pengaman) | ya | tidak |

Diam saja **tidak pernah** menghapus apa yang sudah kamu obrolkan — itu cuma
menghentikan pengiriman tiap suara sekilas ke whisper. Panggil lagi
"hey jarvis" lima menit kemudian, obrolannya masih nyambung. Konteks
**hanya** direset kalau kamu bilang stop secara eksplisit — itu jalan satu-satunya, tidak ada reset otomatis berbasis
waktu diam.

Atur di `config.py`: `SESI_HENING_TIMEOUT` dan `SESI_MAKS_GILIRAN`.

**"Stop jarvis" ≠ "matikan jarvis".** Yang pertama menutup sesi dan mereset
konteks; yang kedua mematikan programnya dan butuh
`systemctl --user start jarvis` untuk hidup lagi.

## Efek suara (umpan balik audio)

Tiga nada pendek supaya kamu tahu Jarvis lagi di tahap apa — tanpa perlu
lihat layar:

| Bunyi | Kapan | Kenapa |
|---|---|---|
| **Naik** dua nada | setelah wake word, **dan** tiap giliran berikutnya | **giliranmu bicara**, ucapanmu mulai direkam |
| Denyut rendah berulang | menunggu jawaban LLM | perintahmu **sedang diproses**, bukan diabaikan |
| **Turun** dua nada | diam 5 detik, sesi berhenti | balik menunggu wake word — tanpa ini kamu baru sadar pas ngomong lagi tapi tidak ditanggapi |
| **Turun** tiga nada | setelah "keluar" | program benar-benar berhenti |

Pola nadanya sengaja konsisten: **naik = mulai**, **turun = berhenti**. Jadi
arahnya kebaca tanpa perlu menghafal bunyinya satu per satu. Turun tiga nada
terdengar lebih final daripada dua — karena memang lebih final.

Bunyi "giliranmu bicara" **sama persis** di kedua momen itu — baik setelah
"hey jarvis" maupun setelah Jarvis selesai menjawab. Sempat dibikin beda
(blip pendek untuk giliran lanjutan), tapi terasa tidak konsisten: bunyi yang
berbeda bikin ragu apakah artinya berbeda juga, padahal buat kamu artinya
sama saja — silakan bicara sekarang.

Bunyinya **dilewati di giliran pertama** tiap sesi, karena bunyi wake word
baru saja terdengar sepersekian detik sebelumnya — dua bunyi beruntun cuma
jadi berisik tanpa menambah informasi.

Denyut tunggu baru mulai setelah **0,8 detik** — kalau jawabannya datang
cepat (jalur lokal, ~0 ms), tidak ada bunyi sama sekali. Percuma bilang
"tunggu ya" untuk sesuatu yang sudah selesai duluan.

### Ganti bunyinya

File dibangkitkan sekali di `~/.jarvis/bunyi/` (`bangun.wav`, `rekam.wav`,
`tunggu.wav`) dan **tidak pernah ditimpa** kalau sudah ada. Jadi taruh wav
buatanmu sendiri dengan nama yang sama untuk menggantinya — atau hapus
file-nya untuk membangkitkan ulang yang bawaan.

`bangun.wav` dan `rekam.wav` isinya identik secara default, tapi tetap dua
file terpisah — jadi kalau nanti kamu memang ingin membedakan "wake word
terdengar" dari "giliran lanjutan", tinggal timpa salah satunya saja.

Setelan di `config.py`: `SUARA_VOLUME` (default 0.25), `SUARA_TUNGGU_INTERVAL`,
`SUARA_TUNGGU_JEDA_AWAL`. Matikan per bagian dengan `JV_SUARA_REKAM=0` /
`JV_SUARA_TUNGGU=0`, atau semuanya dengan `JV_SUARA=0`.

## Riwayat percakapan

Percakapan yang sudah selesai disimpan sebagai markdown di `files/percakapan/`,
satu berkas per percakapan, dinamai dari waktu mulainya
(`2026-08-30_21-22-34.md`) supaya urut sendiri.

**Kapan disimpan** — mengikuti umur KONTEKS, bukan sesi:

| Kejadian | Disimpan? |
|---|---|
| Diam 5 detik, balik ke wake word | **tidak** — percakapannya belum selesai |
| "stop jarvis" / "udah" / "cukup" | **ya**, lalu dikosongkan |
| "keluar" / "matikan jarvis" | **ya**, sebelum proses berhenti |
| `systemctl stop/restart`, Ctrl+C | **ya** — ditangani lewat SIGTERM |

Karena diam tidak menyimpan apa pun, percakapan yang sempat berhenti beberapa
kali tetap jadi **satu berkas utuh**. Kamu bisa bilang "hey jarvis", ngobrol,
diam lima menit, lalu lanjut lagi — semuanya masuk satu berkas, sama seperti
konteksnya yang juga tidak direset.

Isinya termasuk perintah jalur cepat ("buka firefox"), bukan cuma yang lewat
LLM — dicatat di loop sesi `main.py`, satu-satunya tempat yang melihat semua
giliran.

Folder ini **di-gitignore** karena isinya apa pun yang kamu ucapkan ke Jarvis.
Hapus barisnya di `.gitignore` kalau memang mau ikut ter-commit. Matikan
pencatatannya sepenuhnya dengan `JV_RIWAYAT=0`.

## Antarmuka — nyalakan Jarvis & pilih percakapan

Sebelum ini, satu-satunya cara menyalakan Jarvis lagi setelah bilang "keluar"
adalah lewat terminal (`systemctl --user start jarvis`). `jarvis_gui.py`
kasih jendela kecil buat itu, plus tempat memilih mau mulai **percakapan
baru** atau **melanjutkan** salah satu yang sudah tersimpan.

```bash
./scripts/pasang-gui.sh
```

Ini memasang tiga hal:

- **Auto-nyala saat login** (`~/.config/autostart/`) — jendelanya langsung
  ada begitu kamu login, tidak perlu dicari-cari.
- **Shortcut di menu aplikasi** (`~/.local/share/applications/`).
- **Shortcut di Desktop** — kalau jendelanya kamu tutup, tinggal dobel-klik
  lagi kapan saja. Menutup jendela **tidak mematikan Jarvis** — dua hal yang
  independen.

Jalan pakai `python3` **sistem**, bukan `venv/` proyek — PyGObject (GTK) itu
paket sistem, dan jendela ini tidak butuh whisper/torch/piper sama sekali,
cuma baca folder `percakapan/` dan memanggil `systemctl`.

### Cara "lanjutkan percakapan" bekerja

Pilih satu dari daftar → Jarvis **restart** dengan konteks itu sudah dimuat,
tanpa perlu mengucapkan ulang apa pun. Cara sambungnya beda per provider:

- **Rute claudecode (default):** Claude Code sendiri menyimpan tiap sesi
  print-mode ke disk dan bisa disambung lewat `claude --resume <session_id>` —
  sudah diverifikasi langsung, proses yang BENAR-BENAR baru dengan `--resume`
  beneran mengingat percakapan dari proses lama. Jadi "lanjutkan" **tidak**
  memutar ulang giliran lama satu-satu (yang berarti membayar generasi ulang
  tiap giliran) — cukup titipkan `session_id`-nya, dicatat sebagai metadata
  di kepala berkas markdown.
- **Rute gemini:** "sesi" di situ cuma list Python kita sendiri (lihat
  `otak.Percakapan`), jadi "lanjutkan" cukup mengisi ulang list itu langsung
  dari isi berkas — tidak perlu ID apa pun.
- **Transkrip lama** (disimpan sebelum fitur ini ada, tidak punya
  `session_id`) — lewat rute claudecode tidak bisa disambung (replay manual
  berarti membayar generasi ulang), jadi Jarvis mulai percakapan baru untuk
  itu. Ditandai "lama" di daftar GUI-nya.

Alur teknisnya: GUI menulis path berkas yang dipilih ke `~/.jarvis/resume_target`,
lalu `systemctl --user restart jarvis`. `main.py` membaca (dan menghapus)
berkas itu sekali di awal `_siapkan_otak()` — dihapus SELALU, baik otak
ternyata siap maupun tidak, supaya markernya tidak nyangkut dan diam-diam
menyambung ulang di restart berikutnya yang tidak diminta.

## Interupsi (barge-in)

Selagi Jarvis bicara, tekan **Home** untuk langsung memotong pemutarannya
— tidak perlu menunggu dia selesai:

```
jarvis  : "Sisa disk kamu masih banyak, sekitar seratus dua puluh tiga g—"
kamu    : *tekan Home*          ← motong, pemutaran berhenti di 0,4 detik
kamu    : "oke makasih"
jarvis  : "Sip."
```

### Kenapa tombol, bukan suara

Awalnya interupsi dibuat berbasis suara (mic mendengar kamu mulai bicara).
**Sudah diukur langsung** — memutar Piper maupun Chatterbox ke speaker
sungguhan sambil merekam mic barengan: suara Jarvis sendiri bocor balik ke
mic dengan RMS median ~750, puncak ~4000-4600. Itu jauh melewati ambang
manapun yang masih masuk akal, jadi Jarvis sering "menyela dirinya sendiri".
Tanpa acoustic echo cancellation, masalah ini tidak bisa diperbaiki dengan
menyetel angka - tombol fisik sepenuhnya menghindarinya karena bukan
berbasis suara sama sekali.

### Cara pasang tombolnya (GNOME)

Jalur sinyalnya sudah aktif di kode, tinggal dibind ke tombol:

1. **Settings → Keyboard → Keyboard Shortcuts → Custom Shortcuts → +**
2. Name: `Interupsi Jarvis`
3. Command:
   ```
   systemctl --user kill --kill-whom=main -s SIGUSR1 jarvis.service
   ```
4. Tekan tombol yang mau dipakai (kami pakai **Home**) saat diminta.

**`--kill-whom=main` wajib ada.** Tanpanya, `systemctl kill` mengirim sinyal
ke *seluruh* proses anak di cgroup service ini - termasuk subprocess
Chatterbox dan `claude` CLI, yang keduanya defaultnya **mati** kena SIGUSR1
karena tidak mendaftarkan handler untuk itu. Ini bukan teori - kejadian
sekali waktu development, Chatterbox mati jadi zombie proses dan ketahuan
lewat `ps` menunjukkan `<defunct>`.

Bukan GNOME? Bind kombinasi tombol apa pun di desktop environment-mu ke
perintah `systemctl --user kill --kill-whom=main -s SIGUSR1 jarvis.service`
yang sama.

### Interupsi berbasis suara (opsional, butuh headset)

Kodenya masih ada, cuma **mati secara default**. Kalau pakai headset — mic-nya
tidak akan pernah dengar suara Jarvis sama sekali, jadi masalah bocor di atas
hilang total — nyalakan dengan `JV_INTERRUPT=1`. Ambangnya diatur lewat
`INTERRUPT_THRESHOLD` (default 3× `SILENCE_THRESHOLD`) di `config.py`.

Bahasa: campur Indonesia + Inggris. Pencocokan bersifat fuzzy, jadi kamu tidak
perlu menghafal kalimat persis.

## 1. Dependensi sistem

```bash
sudo apt install portaudio19-dev alsa-utils pulseaudio-utils
sudo apt install espeak                      # TTS fallback, langsung jalan
sudo apt install python3-pip python3-venv
```

## 2. Lingkungan Python

```bash
cd files
python3 -m venv venv
source venv/bin/activate
./scripts/install.sh
```

**Pakai `./scripts/install.sh`, bukan `pip install -r requirements.txt` langsung.**
Metadata `openwakeword` mewajibkan `tflite-runtime`, sementara `tflite-runtime`
tidak merilis wheel untuk Python 3.12 ke atas — `pip` akan berhenti dengan
`ResolutionImpossible`. Kita memakai backend ONNX openWakeWord, jadi tflite
memang tidak dibutuhkan; `install.sh` memasang openwakeword dengan `--no-deps`
lalu menambahkan dependensi aslinya satu per satu.

Peringatan `pip` bahwa "openwakeword requires tflite-runtime, which is not
installed" itu wajar dan bisa diabaikan.

Model whisper (~460 MB untuk `small`) dan model wake word (~5 MB) terunduh
otomatis saat pertama kali dijalankan.

## 3. Suara Indonesia

Tiga lapis, dari yang paling enak didengar ke jaring pengaman terakhir:

```
Chatterbox (neural, GPU)  ->  Piper (neural, CPU)  ->  espeak (jaring pengaman)
```

### Chatterbox — suara utama (opsional, butuh GPU NVIDIA)

Jauh lebih natural dari Piper - dipilih setelah A/B langsung, dengar sendiri
dua-duanya mengucapkan kalimat yang sama. Tradeoff-nya latensi: ~0,6-1,4 detik
per ucapan (VRAM ~3,9 GB), dibanding Piper yang ~0,03-0,07 detik.

```bash
./scripts/install-chatterbox.sh      # ~11GB unduhan (venv 6,3GB + model 5GB), beberapa menit
python -m jarvis.cek                # pastikan terdeteksi
```

Terpasang di **venv terpisah** (`venv-chatterbox/`) — `chatterbox-tts` butuh
`numpy<2.0`, bentrok dengan venv utama. Jalan sebagai subprocess yang
dibiarkan hidup (model dimuat sekali ke GPU, ~9-11 detik saat Jarvis start),
bukan dipanggil ulang tiap ucapan.

Chatterbox itu **voice-cloning TTS** — butuh referensi audio, tidak otomatis
punya "suara bawaan". `install-chatterbox.sh` memakai contoh resmi dari model
card sebagai default (`models/chatterbox-id/reference.wav`). Ganti suaranya
dengan menimpa file itu, atau set `JV_CHATTERBOX_REFERENCE=/path/lain.wav`.

**Jatuh otomatis ke Piper** kalau: venv/model tidak ada, gagal start dalam
`CHATTERBOX_STARTUP_TIMEOUT` (60s), atau GPU sedang dipakai proses lain saat
sintesis. Kegagalan sintesis tunggal tidak mematikan Chatterbox permanen -
percobaan berikutnya tetap dicoba; cuma kegagalan **start** yang membuatnya
nonaktif untuk sisa umur proses (supaya tidak mencoba ulang ~10 detik tiap
ucapan kalau memang rusak). Matikan sepenuhnya dengan `JV_CHATTERBOX=0`.

### Piper — fallback

`install.sh` sudah memasang `piper-tts`; tinggal unduh modelnya:

```bash
mkdir -p ~/.local/share/piper && cd ~/.local/share/piper
BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main/id/id_ID/news_tts/medium
wget $BASE/id_ID-news_tts-medium.onnx        # 61 MB
wget $BASE/id_ID-news_tts-medium.onnx.json
```

`id_ID-news_tts-medium` adalah satu-satunya suara Indonesia yang tersedia di
piper-voices. Dilatih dari pembaca berita, jadi intonasinya agak formal —
atur temponya lewat `PIPER_LENGTH_SCALE` di `config.py` (lebih kecil = lebih
cepat). Sintesisnya sekitar 50x realtime, jadi tidak menambah jeda terasa -
inilah kenapa dia tetap dipakai sebagai fallback, bukan dibuang.

### espeak — jaring pengaman terakhir

Kalau Piper juga tidak ada, otomatis jatuh ke `espeak -v id`. Robotik, tapi
memastikan Jarvis selalu bisa bicara.

## 4. Jalankan

```bash
python -m jarvis.cek      # periksa semuanya dulu
python -m jarvis.main
```

Ucapkan "Hey Jarvis", lalu perintahmu.

## 5. Nyala otomatis saat komputer nyala

```bash
./scripts/pasang-layanan.sh
```

Memasang systemd user service yang nyala tiap kali kamu login. Butuh ~2 detik
dari nyala sampai siap mendengar.

```bash
systemctl --user status jarvis      # keadaannya
journalctl --user -u jarvis -f      # log langsung — di sini muncul [kamu] ...
systemctl --user restart jarvis     # setelah mengubah kode
systemctl --user stop jarvis        # matikan sementara
./scripts/pasang-layanan.sh copot           # copot sepenuhnya
```

**Menjalankan `python -m jarvis.main` manual selagi layanannya aktif dicegah otomatis**
lewat file lock (`~/.jarvis/jarvis.lock`) — instance kedua langsung ditolak
dalam hitungan milidetik, sebelum sempat memuat model apa pun. Bukan cuma
soal rebutan mic: dua-duanya bakal coba bicara lewat PipeWire, yang
**mencampur** semua audio yang jalan bersamaan — hasilnya suara ketumpuk-tumpuk,
bukan error yang jelas. Kalau memang mau jalankan manual (misal buat debug),
matikan layanannya dulu: `systemctl --user stop jarvis`.

Kalau perlu variabel rahasia (mis. `GEMINI_API_KEY`), taruh di `~/.jarvis/env`
dengan format `NAMA=nilai` per baris — systemd tidak membaca `~/.bashrc`.

Sapaan awal sengaja dimatikan supaya tidak ada suara tiba-tiba saat login.
Nyalakan lagi dengan `JV_SAPA_START=1` kalau mau.

## Otak LLM

Tanpa ini Jarvis cuma paham perintah bawaan. Dengan ini dia paham apa pun, dan
bisa menjalankan aksi sendiri.

Alurnya bertingkat:

```
suara → whisper → jalur cepat (fuzzy)
                    ├─ cocok & bisa ditangani → jalan lokal, gratis, ~0 ms
                    └─ tidak                  → LLM → jalankan lewat jarvis-do
```

Jalur cepat sengaja didahulukan: "buka firefox" tidak pernah menyentuh network.
Kalau jalur cepat tidak bisa menangani (mis. "buka yang buat edit foto"),
permintaannya diteruskan ke LLM yang bisa menebak maksudnya.

### Rute default: `claudecode` — pakai langganan Pro, tanpa tagihan terpisah

Memakai CLI `claude` yang sudah login di mesinmu. Tidak perlu API key.

```bash
claude --version      # pastikan sudah terpasang & login
python -m jarvis.try_text    # uji dengan mengetik, tanpa mic
```

Prosesnya dibiarkan hidup, tidak di-spawn tiap perintah — jadi riwayat
percakapan diurus Claude Code sendiri.

**Tradeoff yang harus disadari:** latensinya ~2,5–3 detik, versus ~0,8 detik
kalau lewat API langsung. Itu sebabnya jalur cepat penting — perintah
sehari-hari tidak boleh lewat sini.

### Ganti model

Lewat suara, tanpa restart:

```
"ganti model ke sonnet"    "pakai haiku"    "pake opus aja"
```

Pilihannya disimpan di `~/.jarvis/state.json` dan dipakai lagi setelah restart.
Default `haiku` — paling ringan terhadap jatah Pro-mu.

Bisa juga lewat config atau environment:

```bash
JV_CLAUDECODE_MODEL=sonnet python -m jarvis.main
```

### Rute alternatif: `gemini` — API terpisah, kunci gratis

```bash
echo 'export GEMINI_API_KEY="..."' >> ~/.bashrc   # https://aistudio.google.com/apikey
JV_LLM_PROVIDER=gemini python -m jarvis.cek_model        # cek nama model yang tersedia
```

Latensinya lebih rendah, tapi dua hal perlu diketahui soal tier gratisnya:
Google memakai isi percakapanmu untuk mengembangkan produknya dan
*"human reviewers may read, annotate, and process your API input and output"*;
dan batas hariannya tidak dipublikasikan lagi (cek dashboard AI Studio).

Ganti rute cukup satu baris di `config.py` — `otak.py` yang mengurus bedanya.

## Bagaimana LLM menjalankan aksi

Lewat **satu pintu**: skrip [jarvis-do](jarvis-do).

```bash
jarvis-do open firefox      # luncurkan aplikasi
jarvis-do shell df -h       # perintah BACA-SAJA
jarvis-do cuaca             # cuaca kota default
jarvis-do cuaca Bandung     # cuaca kota lain
jarvis-do apps              # daftar aplikasi yang dikenal
```

Claude Code dijalankan dengan `--allowedTools "Bash(jarvis-do:*)"`, jadi
**itu satu-satunya perintah yang boleh dia jalankan** — bukan Bash penuh.

`jarvis-do cuaca [kota]` dibikin aksi tersendiri, bukan lewat `shell`, karena
dua alasan. **Keamanan**: menambahkan `curl` ke daftar putih shell berarti
membuka jalan ke semua alamat, termasuk mengirim data keluar — aksi ini cuma
bisa menghubungi satu host dengan bentuk URL yang sudah ditentukan.
**Kecepatan**: lewat WebSearch bawaan Claude Code, pertanyaan cuaca makan
~15 detik dan $0,06; lewat sini ~0,8 detik dan gratis. Pakai wttr.in, tanpa
API key. Kota default diatur lewat `JV_KOTA`.

**WebSearch/WebFetch** diizinkan untuk pertanyaan terkini lain yang jawabannya
tidak ada di komputer ini (berita, harga, fakta yang berubah). Ini **tidak**
memberi akses network ke shell — keduanya jalan lewat infrastruktur Anthropic,
bukan lewat mesin ini, jadi tidak bisa dipakai mengirim data keluar dari sini.

`jarvis-do shell` memakai **daftar putih** di `SHELL_AMAN` ([tools.py](src/jarvis/tools.py)):
hanya perintah yang membaca (`ls`, `df`, `ps`, `cat`, …). Perintah dengan pipe,
redirect, atau titik koma ditolak apa pun isinya. Menyebut apa yang boleh selalu
lebih aman daripada menebak semua yang berbahaya.

Sudah diuji: permintaan "hapus semua file di Downloads" ditolak, dan Jarvis
menjelaskan bahwa dia hanya bisa membaca.

## Membuka aplikasi — semua yang terpasang, bukan cuma yang didaftarkan

Urutan pencarian saat kamu bilang "buka X" ([commands.py](src/jarvis/commands.py)):

1. **`APP_ALIASES`** — kurasi manual, untuk alias custom atau menimpa nama
   otomatis yang kurang pas.
2. **[aplikasi.py](src/jarvis/aplikasi.py)** — baca LANGSUNG dari sistem, dua sumber:
   - **Semua `.desktop` yang terpasang** (`/usr/share/applications`,
     `~/.local/share/applications`, Flatpak) — cara yang sama dipakai menu
     aplikasi GNOME sendiri.
   - **Game Steam** — baca `libraryfolders.vdf` milik Steam sendiri untuk
     menemukan semua library folder (termasuk drive eksternal), lalu
     `appmanifest_*.acf` di tiap folder untuk daftar nama → appid, diluncurkan
     lewat `steam -applaunch <appid>`. Steam **tidak** membuat `.desktop`
     per game, jadi game tidak akan pernah ketemu lewat jalur pertama — ini
     kenapa perlu jalur terpisah.

     Nama game dicocokkan **fuzzy**, jadi tidak perlu menyebutnya lengkap —
     "buka cyberpunk" sudah cukup untuk "Cyberpunk 2077". Untuk game,
     kata kerja pembukanya juga bisa "main"/"mainin"/"maen"/"play", selain
     "buka" — "main cyberpunk" terasa lebih natural daripada "buka cyberpunk".
3. Tebakan terakhir: nama mentahnya sebagai binary (`"buka gimp"` → `gimp`).

Kedua indeks dibangun **sekali** saat start, disimpan di memori — bukan tiap
kali "buka X" diucapkan, supaya jalur cepat tetap cepat. **Restart Jarvis**
kalau baru pasang aplikasi atau game baru dan mau langsung dikenali.

```python
APP_ALIASES = {
    "obs": "obs",
    "diskord": "discord",   # tulis sesuai yang whisper dengar, bukan ejaan resmi
}
```

`jarvis-do apps` (dipanggil LLM) juga sudah tahu daftar ini — lihat
[Otak LLM](#otak-llm) di atas.

### Membuka folder proyek di editor

`PROJECT_ALIASES` di [commands.py](src/jarvis/commands.py) — beda dari `APP_ALIASES`
karena hasilnya butuh **argumen** (path folder), bukan cuma nama binary:

```python
PROJECT_ALIASES = {
    "project jarvis": os.path.expanduser("~/Documents/jarvis/files"),
    "jarvis": os.path.expanduser("~/Documents/jarvis/files"),
}
PROJECT_EDITOR = "code"
PROJECT_FLAGS = ["-n"]  # paksa window BARU, jangan pakai ulang yang aktif
```

"buka project jarvis" → `code -n /home/kamu/Documents/jarvis/files`. Tambah
proyek lain: satu baris. Arahkan ke folder WORKSPACE yang persis kamu pakai
(bukan folder induknya) — VS Code (dan riwayat sesi Claude Code-nya)
menyimpan itu per folder persis, folder induk vs subfolder dianggap dua
workspace berbeda.

### Membuka website

`WEB_ALIASES` di [commands.py](src/jarvis/commands.py) — untuk situs yang bukan
aplikasi terpasang ("buka youtube", "buka email"), jadi tidak akan pernah
ketemu lewat pencarian aplikasi biasa:

```python
WEB_ALIASES = {
    "youtube": "https://youtube.com",
    "email": "https://mail.google.com",
    "gmail": "https://mail.google.com",
    # ...
}
```

Dibuka lewat `xdg-open` (browser default sistem). Untuk situs di luar
daftar ini, LLM punya tool `buka_website(url)` sendiri (lihat
[tools.py](src/jarvis/tools.py)) yang bisa buka alamat APA PUN yang kamu sebut, bukan
cuma yang dikurasi.

**Soal kata "jarvis" sebagai isi kalimat, bukan sapaan** — ini butuh
perhatian khusus karena "jarvis" biasanya dibuang sebagai kata sapaan
("Jarvis, buka firefox" → "buka firefox"). Supaya "buka project **jarvis**"
tidak ikut kepotong jadi "buka project", `normalize()` di `commands.py`
cuma membuang "jarvis" kalau posisinya di **awal** kalimat (posisi sapaan),
bukan di tengah/ekor. Frasa perpisahan seperti "sampai jumpa jarvis" tetap
dikenali lewat pengecekan terpisah yang secara lokal melepas "jarvis" di
ekor — beda dari "buka project jarvis", di situ "jarvis" memang isi/argumen,
bukan sapaan. Diuji di `tests/test_commands.py`.

### Aplikasi yang dibuka tidak ikut mati kalau Jarvis restart

Semua peluncuran lewat `commands._luncurkan()` dijalankan via
`systemd-run --user --scope`, bukan `subprocess.Popen()` biasa. Alasannya
bukan teori — kejadian nyata saat development:

Proses yang dibuat lewat `Popen()` biasa dari dalam `jarvis.service`
otomatis ikut masuk **cgroup milik jarvis.service sendiri**. Unit-nya diset
`KillMode=control-group` (perlu, supaya subprocess internal seperti
Chatterbox ikut bersih saat Jarvis berhenti — lihat
[Riwayat percakapan](#riwayat-percakapan) soal `systemctl stop/restart`
di atas) — tapi itu berarti **aplikasi yang kamu buka lewat suara ikut kena
SIGTERM** setiap kali Jarvis di-restart atau di-stop. Steam yang lagi
mengunduh update dirinya sendiri sempat kena bunuh gara-gara ini, rusak
statenya ("didn't shutdown cleanly"), dan siklusnya berulang tiap kali
dicoba lagi — butuh beberapa lapis investigasi untuk sampai ke akar
masalahnya.

`systemd-run --scope` menaruh proses baru ke scope unit-nya **sendiri**,
lepas total dari cgroup Jarvis. Sudah diverifikasi langsung: luncurkan
proses lewat `commands._luncurkan()`, matikan `jarvis.service`, proses
tetap hidup.

Cek berapa banyak yang berhasil terindeks: `python -m jarvis.cek`.

## Mengubah gaya bicara

Semua kalimat yang diucapkan ada di [responses.py](src/jarvis/responses.py), terpisah dari
logikanya. Tiap situasi punya beberapa varian, diambil acak, dan tidak pernah
mengulang varian yang barusan dipakai — mengucapkan kalimat yang persis sama
setiap kali itu yang paling terdengar seperti bot.

Menambah varian cukup menambah string ke daftarnya:

```python
"membuka": [
    "Oke, {app}.",
    "Siap, {app}.",
    "Gaskeun.",        # ← tambahan
],
```

`{app}` dan `{detik}` diisi otomatis. `python tests/test_commands.py` akan menangkap
kalau varian barumu memakai placeholder yang tidak tersedia.

**Kenapa bukan LLM lokal?** Sudah diuji dengan qwen3-vl:4b dan qwen2.5:14b lewat
Ollama. Dua masalah: variasinya justru *lebih sedikit* daripada daftar acak
(model kolaps ke satu jawaban favorit meski temperature 1.0 — `"Maaf, coba
lagi."` empat kali berturut-turut), dan model kecil mengarang — menjawab
`"Sip."` untuk perintah yang tidak dia mengerti, atau `"Bentar ya, nanti
bantu."` untuk aplikasi yang tidak terpasang. Untuk asisten yang menjalankan
perintah nyata, itu kemunduran. Daftar acak: 0 ms, tidak pernah bohong.

## Pengaman shutdown

Salah dengar yang mematikan PC berarti kerjaan yang belum tersimpan hilang.
Ada dua lapis, dan **jawaban yang tidak jelas selalu berarti batal**:

1. Konfirmasi suara — harus ada kata setuju eksplisit ("ya", "iya", "oke").
2. Jeda 8 detik — masih bisa dibatalkan dengan "batal" atau "jangan".

Perintah shutdown juga hanya cocok kalau ada kata sasaran yang eksplisit
(komputer / laptop / pc / shutdown), sehingga "matikan musik" tidak akan
pernah mematikan komputer.

Ubah durasinya di `SHUTDOWN_CONFIRM_SECONDS` dan `SHUTDOWN_GRACE_SECONDS`
dalam [config.py](src/jarvis/config.py).

## Uji tanpa mic

```bash
python tests/test_commands.py
```

Menguji pencocokan maksud dan seluruh cabang alur shutdown. Jalankan setiap
kali menyentuh `commands.py`.

## Penyetelan

| Gejala | Perbaikan |
|---|---|
| Suku kata pertama kepotong | naikkan `PREROLL_MS` |
| Terlalu cepat berhenti merekam | naikkan `SILENCE_SECONDS` atau turunkan `SILENCE_THRESHOLD` |
| Whisper lambat | turunkan `WHISPER_MODEL_SIZE` ke `"base"` (akurasi bahasa Indonesia turun) |
| Whisper salah dengar nama app | tambahkan nama itu ke `WHISPER_INITIAL_PROMPT` |
| Wake word sering salah trigger | naikkan `WAKE_WORD_THRESHOLD` |
| `ResolutionImpossible` saat install | pakai `./scripts/install.sh`, lihat bagian 2 |

`WHISPER_MODEL_SIZE` **tidak boleh** berakhiran `.en` — itu model khusus bahasa
Inggris dan tidak bisa memahami bahasa Indonesia. Program menolak jalan kalau
disetel begitu.

## Struktur

Paket Python asli (`src/jarvis/`) — `pip install -e .` mendaftarkannya
supaya bisa diimpor sebagai `from jarvis import X` dari mana pun venv ini
aktif, dan dijalankan lewat `python -m jarvis.<nama>`:

```
files/
├── pyproject.toml          # daftarin paket `jarvis` (src layout, editable install)
├── requirements.txt        # dependensi - pasang lewat scripts/install.sh, BUKAN langsung
├── src/jarvis/
│   ├── main.py              # loop utama
│   ├── config.py            # semua setelan
│   ├── audio.py             # wake word + perekaman (satu stream berkelanjutan)
│   ├── speech_to_text.py    # faster-whisper, multilingual
│   ├── commands.py          # pencocokan maksud + handler — file yang paling sering diedit
│   ├── responses.py         # semua kalimat yang diucapkan Jarvis
│   ├── bunyi.py             # efek suara: giliranmu, menunggu, jeda, pamit
│   ├── riwayat.py           # catatan percakapan -> percakapan/*.md, plus parse balik
│   ├── jarvis_gui.py        # jendela: nyala/mati Jarvis + pilih percakapan (GTK, python3 SISTEM)
│   ├── otak.py              # lapis LLM, provider bisa ditukar
│   ├── tools.py             # tool + daftar putih shell (provider gemini)
│   ├── jarvis_do.py         # satu-satunya pintu aksi untuk LLM (provider claudecode)
│   ├── text_to_speech.py    # chatterbox / piper / espeak, mendukung interupsi
│   ├── chatterbox_server.py # proses TTS terpisah (dipanggil via venv-chatterbox)
│   ├── aplikasi.py          # penemuan aplikasi sistem-lebar (.desktop + Steam)
│   ├── cek.py                # python -m jarvis.cek - pemeriksaan sebelum jalan
│   ├── miccheck.py           # python -m jarvis.miccheck - kalibrasi SILENCE_THRESHOLD
│   ├── cek_model.py          # python -m jarvis.cek_model - lihat model Gemini tersedia
│   └── try_text.py           # python -m jarvis.try_text - uji lewat ketik, tanpa mic
├── tests/
│   ├── test_commands.py    # uji pencocokan maksud, tanpa mic
│   ├── test_riwayat.py     # uji kapan disimpan + parsing + alur resume, tanpa mic
│   └── test_audio.py       # uji logika perekaman & interupsi, tanpa mic
├── scripts/
│   ├── install.sh              # pasang dependensi + editable-install paket jarvis
│   ├── install-chatterbox.sh   # pasang suara Chatterbox (opsional, butuh GPU)
│   ├── pasang-layanan.sh       # pasang systemd --user service
│   ├── pasang-gui.sh           # pasang autostart + shortcut menu + shortcut Desktop
│   └── jarvis-do               # shim: satu-satunya perintah yang boleh dijalankan LLM
└── systemd/
    ├── jarvis.service.template # template unit systemd --user
    └── 99-jarvis-inotify.conf  # contoh sysctl, naikkan limit inotify
```
