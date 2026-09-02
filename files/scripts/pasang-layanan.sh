#!/usr/bin/env bash
# Pasang Jarvis sebagai layanan yang nyala otomatis saat login.
#
#   ./scripts/pasang-layanan.sh          pasang & nyalakan
#   ./scripts/pasang-layanan.sh copot    matikan & hapus
set -euo pipefail

# ROOT proyek (venv/, jarvis-do lewat scripts/) - satu tingkat di atas
# scripts/ (tempat skrip ini berada).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT="$HOME/.config/systemd/user/jarvis.service"

if [ "${1:-}" = "copot" ]; then
    systemctl --user disable --now jarvis.service 2>/dev/null || true
    rm -f "$UNIT"
    systemctl --user daemon-reload
    echo "Layanan dicopot."
    exit 0
fi

PYTHON="$ROOT/venv/bin/python"
[ -x "$PYTHON" ] || { echo "venv belum ada. Jalankan scripts/install.sh dulu." >&2; exit 1; }

# PATH minimal yang dibutuhkan: scripts/ (jarvis-do), ~/.local/bin (claude),
# /snap/bin (banyak aplikasi GUI terpasang lewat snap, mis. Discord - tanpa
# ini shutil.which() di open_app() tidak pernah nemu binary-nya sama sekali,
# walau aplikasinya beneran terpasang), lalu path sistem.
SERVICE_PATH="$ROOT/scripts:$HOME/.local/bin:/snap/bin:/usr/local/bin:/usr/bin:/bin"

mkdir -p "$(dirname "$UNIT")" "$HOME/.jarvis"
sed -e "s|__DIR__|$ROOT|g" \
    -e "s|__PYTHON__|$PYTHON|g" \
    -e "s|__PATH__|$SERVICE_PATH|g" \
    "$ROOT/systemd/jarvis.service.template" > "$UNIT"

systemctl --user daemon-reload
systemctl --user enable --now jarvis.service

echo
echo "Terpasang. Jarvis akan nyala otomatis tiap kali kamu login."
echo
echo "  systemctl --user status jarvis      lihat keadaannya"
echo "  journalctl --user -u jarvis -f      lihat lognya (di sini muncul [kamu] ...)"
echo "  systemctl --user restart jarvis     nyalakan ulang setelah ubah kode"
echo "  systemctl --user stop jarvis        matikan sementara"
echo "  ./scripts/pasang-layanan.sh copot   copot sepenuhnya"
