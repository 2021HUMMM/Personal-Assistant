#!/usr/bin/env bash
# Pasang antarmuka Jarvis (jarvis_gui.py): auto-nyala saat login, shortcut di
# menu aplikasi, dan shortcut di Desktop.
#
#   ./pasang-gui.sh          pasang
#   ./pasang-gui.sh copot    copot semuanya
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOSTART="$HOME/.config/autostart/jarvis-gui.desktop"
APLIKASI="$HOME/.local/share/applications/jarvis-gui.desktop"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
DESKTOP_FILE="$DESKTOP_DIR/jarvis-gui.desktop"

if [ "${1:-}" = "copot" ]; then
    rm -f "$AUTOSTART" "$APLIKASI" "$DESKTOP_FILE"
    echo "Dicopot: autostart, shortcut menu aplikasi, shortcut Desktop."
    exit 0
fi

if ! python3 -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk" 2>/dev/null; then
    echo "GTK (PyGObject) tidak ada di python3 sistem." >&2
    echo "Pasang dulu:  sudo apt install python3-gi gir1.2-gtk-3.0" >&2
    exit 1
fi

mkdir -p "$(dirname "$AUTOSTART")" "$(dirname "$APLIKASI")"

# Icon pakai emoji lewat ikon tema bawaan GNOME yang paling mendekati -
# tidak perlu bikin file .png sendiri.
cat > /tmp/jarvis-gui.desktop.tmp <<EOF
[Desktop Entry]
Type=Application
Name=Jarvis
Comment=Nyalakan Jarvis dan pilih percakapan
Exec=python3 $DIR/jarvis_gui.py
Icon=audio-input-microphone
Terminal=false
Categories=Utility;
EOF

install -m 644 /tmp/jarvis-gui.desktop.tmp "$AUTOSTART"
install -m 644 /tmp/jarvis-gui.desktop.tmp "$APLIKASI"

if [ -d "$DESKTOP_DIR" ]; then
    install -m 755 /tmp/jarvis-gui.desktop.tmp "$DESKTOP_FILE"
    # Nautilus menganggap file .desktop di Desktop sebagai "belum dipercaya"
    # sampai ditandai - tanpa ini, dobel-klik cuma nampilin isi teksnya,
    # bukan menjalankannya.
    if command -v gio >/dev/null; then
        gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
    fi
else
    echo "[!] Folder Desktop tidak ditemukan - shortcut menu aplikasi tetap dipasang."
fi

rm -f /tmp/jarvis-gui.desktop.tmp
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "Terpasang:"
echo "  - Auto-nyala saat login : $AUTOSTART"
echo "  - Menu aplikasi         : $APLIKASI"
[ -f "$DESKTOP_FILE" ] && echo "  - Shortcut Desktop      : $DESKTOP_FILE"
echo
echo "Coba sekarang:  python3 $DIR/jarvis_gui.py"
echo "Copot semuanya: ./pasang-gui.sh copot"
