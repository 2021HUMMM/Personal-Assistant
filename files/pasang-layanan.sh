#!/usr/bin/env bash
# Pasang Jarvis sebagai layanan yang nyala otomatis saat login.
#
#   ./pasang-layanan.sh          pasang & nyalakan
#   ./pasang-layanan.sh copot    matikan & hapus
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT="$HOME/.config/systemd/user/jarvis.service"

if [ "${1:-}" = "copot" ]; then
    systemctl --user disable --now jarvis.service 2>/dev/null || true
    rm -f "$UNIT"
    systemctl --user daemon-reload
    echo "Layanan dicopot."
    exit 0
fi

PYTHON="$DIR/venv/bin/python"
[ -x "$PYTHON" ] || { echo "venv belum ada. Jalankan install.sh dulu." >&2; exit 1; }

# PATH minimal yang dibutuhkan: direktori ini (jarvis-do), ~/.local/bin (claude),
# lalu path sistem.
SERVICE_PATH="$DIR:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

mkdir -p "$(dirname "$UNIT")" "$HOME/.jarvis"
sed -e "s|__DIR__|$DIR|g" \
    -e "s|__PYTHON__|$PYTHON|g" \
    -e "s|__PATH__|$SERVICE_PATH|g" \
    "$DIR/jarvis.service.template" > "$UNIT"

systemctl --user daemon-reload
systemctl --user enable --now jarvis.service

echo
echo "Terpasang. Jarvis akan nyala otomatis tiap kali kamu login."
echo
echo "  systemctl --user status jarvis      lihat keadaannya"
echo "  journalctl --user -u jarvis -f      lihat lognya (di sini muncul [kamu] ...)"
echo "  systemctl --user restart jarvis     nyalakan ulang setelah ubah kode"
echo "  systemctl --user stop jarvis        matikan sementara"
echo "  ./pasang-layanan.sh copot           copot sepenuhnya"
