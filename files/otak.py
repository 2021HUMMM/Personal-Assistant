"""
Otak LLM - dipanggil hanya kalau fuzzy matcher tidak menemukan perintah.

Sengaja dibuat provider-agnostik. `Otak` menentukan bentuknya, tiap provider
mengisinya. Ganti Gemini ke Claude cukup mengubah LLM_PROVIDER di config,
tanpa menyentuh main.py atau tools.py.

Penting dipahami: model tidak menyimpan apa pun antar panggilan. Yang bikin
percakapan terasa nyambung adalah `Percakapan` di bawah - kita kirim ulang
seluruh riwayat tiap kali.
"""

import json
import os
import queue
import subprocess
import threading
import time

import config
import tools


class Percakapan:
    """
    Riwayat jangka pendek. Hidup di memori proses, hilang saat program ditutup -
    dan memang seharusnya begitu.

    Direset JIKA DAN HANYA JIKA reset() dipanggil eksplisit (dari intent
    "stop jarvis" di commands.py) - tidak ada reset otomatis berbasis waktu
    diam. maks_giliran tetap ada sebagai rem biaya: tanpa batas ini, perintah
    ke-50 dalam satu sesi panjang akan mengirim 50 giliran sekaligus.
    """

    def __init__(self, maks_giliran=None):
        self.maks_giliran = maks_giliran or config.LLM_MAX_GILIRAN
        self._pesan = []

    def ambil(self):
        return list(self._pesan)

    def tambah(self, peran: str, teks: str):
        self._pesan.append((peran, teks))
        self._pesan = self._pesan[-self.maks_giliran * 2:]

    def reset(self):
        self._pesan = []


class Otak:
    """Bentuk yang harus dipenuhi tiap provider."""

    def tanya(self, ucapan: str, ctx) -> str:
        raise NotImplementedError

    def siap(self) -> bool:
        raise NotImplementedError

    def reset_percakapan(self):
        """Mulai percakapan bersih. Aman dipanggil kapan saja."""

    def muat_riwayat(self, giliran):
        """
        Muat percakapan LAMA supaya obrolan lanjut dari situ - dipakai
        jarvis_gui.py lewat main.py saat kamu pilih "lanjutkan percakapan".
        `giliran`: list (ucapan, jawaban) dari riwayat.muat_dari_berkas().
        Default tidak melakukan apa-apa - provider yang mendukungnya
        (OtakGemini) menimpa ini.
        """


class OtakGemini(Otak):
    def __init__(self):
        self._client = None
        self.percakapan = Percakapan()
        self.total_token = 0

    def siap(self) -> bool:
        return bool(config.GEMINI_API_KEY)

    def reset_percakapan(self):
        self.percakapan.reset()

    def muat_riwayat(self, giliran):
        # Beda dari rute claudecode: di sini "sesi" itu literal list Python
        # kita sendiri (lihat kelas Percakapan), bukan sesuatu yang dikelola
        # server. Jadi "melanjutkan" cukup mengisi ulang list-nya - tidak
        # perlu generasi ulang, dan tidak perlu ID apa pun dari luar.
        self.percakapan.reset()
        for ucapan, jawaban in giliran:
            self.percakapan.tambah("user", ucapan)
            self.percakapan.tambah("model", jawaban)

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=config.GEMINI_API_KEY)
        return self._client

    def tanya(self, ucapan: str, ctx) -> str:
        from google.genai import types

        riwayat = self.percakapan.ambil()
        isi = [types.Content(role=("user" if p == "user" else "model"),
                             parts=[types.Part(text=t)])
               for p, t in riwayat]
        isi.append(types.Content(role="user", parts=[types.Part(text=ucapan)]))

        respons = self._get_client().models.generate_content(
            model=config.GEMINI_MODEL,
            contents=isi,
            config=types.GenerateContentConfig(
                system_instruction=config.LLM_SYSTEM_PROMPT,
                # Fungsi Python biasa - SDK yang menjalankan loop tool-nya.
                tools=tools.buat_tools(ctx),
                max_output_tokens=config.LLM_MAX_TOKENS,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    maximum_remote_calls=config.LLM_MAX_TOOL_CALLS,
                ),
            ),
        )

        jawaban = (respons.text or "").strip()
        self._catat_pemakaian(respons)

        self.percakapan.tambah("user", ucapan)
        if jawaban:
            self.percakapan.tambah("model", jawaban)
        return jawaban

    def _catat_pemakaian(self, respons):
        u = getattr(respons, "usage_metadata", None)
        if not u:
            return
        masuk = getattr(u, "prompt_token_count", 0) or 0
        keluar = getattr(u, "candidates_token_count", 0) or 0
        self.total_token += masuk + keluar
        print(f"[otak] token: {masuk} masuk + {keluar} keluar "
              f"(total sesi ini: {self.total_token})")


class OtakClaudeCode(Otak):
    """
    Memakai CLI `claude` yang sudah login dengan langganan Pro-mu.
    Tidak ada tagihan API terpisah - pemakaian masuk ke jatah Pro.

    Prosesnya dibiarkan HIDUP, tidak di-spawn tiap perintah. Dua alasan:
    tidak perlu inisialisasi ulang, dan riwayat percakapan diurus Claude Code
    sendiri - tidak perlu kelas Percakapan di sini.

    Tradeoff yang harus disadari: latensinya ~2,5-3 detik, jauh di atas API
    langsung (~0,8 detik). Itu sebabnya jalur cepat di commands.py tetap
    penting - perintah sehari-hari tidak boleh lewat sini.
    """

    def __init__(self):
        self._proc = None
        self._antrian = None
        self.model = config.CLAUDECODE_MODEL
        self.total_biaya = 0.0
        # ID sesi yang Claude Code KEMBALIKAN dari giliran TERAKHIR - dipakai
        # main.py buat menulis ke riwayat.py saat percakapan disimpan, supaya
        # bisa dilanjutkan lagi nanti lewat jarvis_gui.py.
        self.session_id = None
        # ID sesi yang mau DILANJUTKAN saat proses claude berikutnya dinyalakan
        # (diisi dari luar lewat muat_riwayat_id(), dipakai jarvis_gui.py lewat
        # main.py). Beda dari self.session_id di atas - yang itu punya PROSES
        # SEKARANG, yang ini punya percakapan yang MAU disambung.
        self._resume_session_id = None

    def siap(self) -> bool:
        from shutil import which
        return which("claude") is not None

    def muat_riwayat_id(self, session_id: str):
        """
        Sambung ke sesi Claude Code LAMA lewat `claude --resume <id>` - bukan
        replay giliran satu-satu (yang berarti membayar generasi ulang tiap
        giliran). Sudah diverifikasi langsung: proses BARU dengan --resume
        beneran mengingat percakapan dari proses lama, lewat protokol
        stream-json yang sama persis dipakai di sini.

        Dipanggil SEBELUM proses claude pertama kali dinyalakan - kalau
        prosesnya sudah jalan, matikan dulu supaya nyala ulang pakai --resume.
        """
        self._resume_session_id = session_id
        self.matikan()

    def reset_percakapan(self):
        # Riwayat dipegang proses claude, jadi caranya dengan menyalakan ulang.
        # Prosesnya nyala lagi sendiri saat perintah berikutnya datang. Lepas
        # juga _resume_session_id - "stop jarvis" itu sinyal eksplisit "mulai
        # BERSIH dari sini", jangan diam-diam balik ke sesi lama yang tadi
        # sempat disambung.
        self._resume_session_id = None
        self.matikan()

    def ganti_model(self, model: str):
        """Ganti model dan nyalakan ulang prosesnya."""
        self.model = model
        self.matikan()
        print(f"[otak] model diganti ke {model}")

    def matikan(self):
        if self._proc is not None:
            try:
                self._proc.stdin.close()
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                pass
            self._proc = None
            self._antrian = None

    def _nyalakan(self):
        if self._proc is not None and self._proc.poll() is None:
            return

        perintah = [
            "claude", "-p", "--model", self.model,
            "--input-format", "stream-json",
            "--output-format", "stream-json", "--verbose",
            "--system-prompt", config.LLM_SYSTEM_PROMPT,
            "--exclude-dynamic-system-prompt-sections",
            # Pintu keluar ke komputer ini: HANYA skrip jarvis-do, bukan Bash
            # penuh. Polanya harus cocok dengan cara Claude MENULIS
            # perintahnya, jadi nama pendek - direktorinya ditaruh di PATH
            # di bawah.
            #
            # WebSearch/WebFetch diizinkan untuk pertanyaan yang jawabannya
            # tidak ada di komputer ini. Ini TIDAK memberi akses network ke
            # shell - keduanya jalan lewat infrastruktur Anthropic, bukan
            # lewat mesin ini, jadi tidak bisa dipakai mengirim data keluar
            # dari sini. Cuaca sengaja TIDAK lewat sini (lihat system prompt):
            # `jarvis-do cuaca` ~1 detik, WebSearch ~15 detik.
            "--allowedTools", "Bash(jarvis-do:*)", "WebSearch", "WebFetch",
        ]
        if self._resume_session_id:
            perintah += ["--resume", self._resume_session_id]
            print(f"[otak] menyalakan claude ({self.model}), "
                  f"melanjutkan sesi {self._resume_session_id[:8]}...")
        else:
            print(f"[otak] menyalakan claude ({self.model})...")
        # Taruh direktori ini di depan PATH supaya `jarvis-do` bisa dipanggil
        # dengan nama pendek - itu yang dicocokkan oleh --allowedTools.
        direktori = os.path.dirname(os.path.abspath(__file__))
        env = dict(os.environ, PATH=direktori + os.pathsep + os.environ.get("PATH", ""))

        self._proc = subprocess.Popen(
            perintah, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
            cwd=direktori, env=env,
        )
        self._antrian = queue.Queue()
        threading.Thread(target=self._pembaca, args=(self._proc, self._antrian),
                         daemon=True).start()

    @staticmethod
    def _pembaca(proc, antrian):
        for baris in proc.stdout:
            antrian.put(baris)
        antrian.put(None)

    def tanya(self, ucapan: str, ctx) -> str:
        self._nyalakan()

        pesan = {"type": "user",
                 "message": {"role": "user",
                             "content": [{"type": "text", "text": ucapan}]}}
        try:
            self._proc.stdin.write(json.dumps(pesan) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            # Proses mati di tengah jalan - nyalakan ulang sekali lalu coba lagi.
            print("[otak] proses claude mati, menyalakan ulang")
            self.matikan()
            self._nyalakan()
            self._proc.stdin.write(json.dumps(pesan) + "\n")
            self._proc.stdin.flush()

        return self._tunggu_hasil()

    def _tunggu_hasil(self) -> str:
        batas = time.time() + config.LLM_TIMEOUT
        while time.time() < batas:
            try:
                baris = self._antrian.get(timeout=max(0.1, batas - time.time()))
            except queue.Empty:
                break
            if baris is None:
                self.matikan()
                raise RuntimeError("proses claude berhenti tanpa hasil")
            try:
                d = json.loads(baris)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "result":
                continue

            biaya = d.get("total_cost_usd", 0.0) or 0.0
            self.total_biaya += biaya
            u = d.get("usage", {})
            print(f"[otak] {self.model}: {u.get('output_tokens', 0)} token keluar, "
                  f"setara ${biaya:.4f} (total sesi: ${self.total_biaya:.4f})")

            # Tangkap session_id dari giliran TERAKHIR - dipakai main.py saat
            # menyimpan riwayat, supaya bisa disambung lagi lewat jarvis_gui.py.
            if d.get("session_id"):
                self.session_id = d["session_id"]

            if d.get("is_error"):
                raise RuntimeError(d.get("result") or "claude mengembalikan error")
            return (d.get("result") or "").strip()

        raise TimeoutError(f"claude tidak menjawab dalam {config.LLM_TIMEOUT} detik")


def buat_otak() -> Otak:
    """Bikin otak sesuai LLM_PROVIDER di config."""
    if config.LLM_PROVIDER == "claudecode":
        return OtakClaudeCode()
    if config.LLM_PROVIDER == "gemini":
        return OtakGemini()
    raise ValueError(
        f"LLM_PROVIDER={config.LLM_PROVIDER!r} tidak dikenal. "
        "Pilihannya: 'claudecode' atau 'gemini'."
    )
