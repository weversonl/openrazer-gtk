#!/usr/bin/env bash
# Installs a .desktop launcher + icon for the current user. Doesn't touch
# system packages - runs the app in place via `python3 -m razer_gtk`,
# same as the dev workflow in README.md.
set -euo pipefail

APP_ID="io.github.weversonl.OpenRazerGTK"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ICON_SRC="$PROJECT_ROOT/data/icons/hicolor/scalable/apps/$APP_ID.svg"
ICON_DEST_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/$APP_ID.desktop"

# Desktop launchers run with a minimal PATH/env, so a version manager shim
# (asdf, pyenv, ...) picked up from this shell's PATH may not work there -
# prefer a real system interpreter that actually has the GTK4/OpenRazer
# bindings, falling back to whatever's on PATH.
check_deps() {
    "$1" -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1'); import openrazer.client" \
        >/dev/null 2>&1
}

PYTHON_BIN=""
for candidate in /usr/bin/python3 "$(command -v python3 || true)"; do
    if [ -n "$candidate" ] && check_deps "$candidate"; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(command -v python3 || true)"
    if [ -z "$PYTHON_BIN" ]; then
        echo "python3 not found in PATH." >&2
        exit 1
    fi
    echo "Warning: couldn't find a python3 with GTK4/Libadwaita and python-openrazer importable." >&2
    echo "Falling back to $PYTHON_BIN - install those before running the app." >&2
fi

mkdir -p "$ICON_DEST_DIR" "$DESKTOP_DIR"
cp "$ICON_SRC" "$ICON_DEST_DIR/$APP_ID.svg"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=OpenRazerGTK
Comment=Control panel for Razer peripherals via OpenRazer
Exec=$PYTHON_BIN -m razer_gtk
Path=$PROJECT_ROOT
Icon=$APP_ID
Categories=Utility;HardwareSettings;
StartupWMClass=$APP_ID
Terminal=false
EOF

if command -v gtk4-update-icon-cache >/dev/null 2>&1; then
    gtk4-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
elif command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q "$DESKTOP_DIR" 2>/dev/null || true
fi

echo "Installed: $DESKTOP_FILE"
echo "OpenRazerGTK should now appear in your application launcher."
