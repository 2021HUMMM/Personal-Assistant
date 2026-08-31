"""
Lihat model Gemini apa saja yang tersedia di akunmu.

    python cek_model.py

Nama model berubah-ubah, jadi jangan percaya nilai default di config.py -
cek langsung ke akunmu, lalu setel JV_GEMINI_MODEL atau ubah config.
"""

import config


def main():
    if not config.GEMINI_API_KEY:
        print("GEMINI_API_KEY belum diset.")
        print("Ambil kunci gratis di https://aistudio.google.com/apikey lalu:")
        print('  export GEMINI_API_KEY="..."')
        return 1

    from google import genai

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    print(f"Model yang bisa dipakai untuk generateContent "
          f"(default sekarang: {config.GEMINI_MODEL})\n")

    ada = False
    for m in client.models.list():
        aksi = getattr(m, "supported_actions", None) or []
        if "generateContent" not in aksi:
            continue
        ada = True
        nama = m.name.replace("models/", "")
        tanda = " <- default di config" if nama == config.GEMINI_MODEL else ""
        print(f"  {nama}{tanda}")
        if getattr(m, "display_name", None):
            print(f"      {m.display_name}")

    if not ada:
        print("  (tidak ada yang cocok - cek kuncimu)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
