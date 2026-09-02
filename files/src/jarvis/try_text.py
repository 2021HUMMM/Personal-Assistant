"""
Coba Jarvis dengan MENGETIK, bukan bicara.

Berguna untuk memverifikasi pencocokan maksud dan aksi yang benar-benar
dijalankan (aplikasi kebuka atau tidak) sebelum berurusan dengan mic,
whisper, dan wake word. Tidak butuh dependensi apa pun.

    python -m jarvis.try_text            # aman: shutdown hanya disimulasikan
    python -m jarvis.try_text --armed    # shutdown BENERAN mematikan komputer

Ketik 'keluar' untuk berhenti.
"""

import sys

from jarvis import commands
from jarvis import config
from jarvis import otak as otak_mod

ARMED = "--armed" in sys.argv


class TextContext:
    """Context yang bicara ke stdout dan mendengar dari keyboard."""

    otak = None   # diisi di main(), dipakai handler ganti_model

    def speak(self, text):
        print(f"  [jarvis] {text}")

    def listen(self, seconds):
        return input(f"  [jarvis menunggu jawaban, {seconds:g} detik] > ")


def main():
    if not ARMED:
        commands._poweroff = lambda: "  (simulasi: di sini komputer akan mati)"
        print("Mode aman - shutdown hanya disimulasikan. Pakai --armed untuk sungguhan.\n")
    else:
        print("!! MODE ARMED - perintah shutdown akan BENERAN mematikan komputer.\n")

    print("Ketik perintah seperti kamu mengucapkannya. Contoh:")
    print("  buka firefox / bukain vscode dong / matikan komputer / keluar\n")

    ctx = TextContext()
    otak = None
    try:
        kandidat = otak_mod.buat_otak()
        if kandidat.siap():
            otak = kandidat
            ctx.otak = otak
            print(f"Otak LLM: {config.LLM_PROVIDER} "
                  f"({getattr(otak, 'model', '?')}) - AKTIF\n")
        else:
            print(f"Otak LLM: {config.LLM_PROVIDER} - tidak aktif\n")
    except ValueError as e:
        print(f"Otak LLM: {e}\n")

    while True:
        try:
            text = input("[kamu] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not text:
            continue

        matched = commands.match(text)
        if matched is None:
            print(f"  -> jalur cepat tidak cocok "
                  f"(ternormalisasi: {commands.normalize(text)!r})")
            if otak is None:
                print("     otak LLM tidak aktif - set GEMINI_API_KEY untuk mencobanya")
                continue
            print("     -> diserahkan ke LLM...")
            try:
                jawaban = otak.tanya(text, ctx)
            except Exception as e:
                print(f"     [otak gagal] {type(e).__name__}: {e}")
                continue
            ctx.speak(jawaban or "(kosong)")
            continue

        name, handler, arg = matched
        print(f"  -> intent={name}" + (f" arg={arg!r}" if arg else ""))

        response = handler(ctx, arg)
        if response is None and otak is not None:
            print("     jalur cepat tidak bisa menangani -> diserahkan ke LLM...")
            try:
                ctx.speak(otak.tanya(text, ctx) or "(kosong)")
            except Exception as e:
                print(f"     [otak gagal] {type(e).__name__}: {e}")
            continue
        if response:
            ctx.speak(response)
        if name == "quit":
            return


if __name__ == "__main__":
    main()
