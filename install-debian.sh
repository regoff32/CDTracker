#!/bin/sh
# CDTracker 5 - install on Debian (for the current user)
set -e
cd "$(dirname "$0")"
APP="$HOME/.local/share/cdtracker/app"

need=""
python3 -c "import tkinter" 2>/dev/null || need="$need python3-tk"
command -v smbclient >/dev/null 2>&1 || need="$need smbclient"
if [ -n "$need" ]; then
    echo "Installing:$need  (needs your sudo password)"
    sudo apt install -y $need
fi

mkdir -p "$APP/web" "$HOME/.local/bin" "$HOME/.local/share/applications"
install -m 644 cdtracker_core.py "$APP/"
install -m 755 cdtracker_desktop.py "$APP/"
install -m 644 web/index.html "$APP/web/"
ln -sf "$APP/cdtracker_desktop.py" "$HOME/.local/bin/cdtracker"

cat > "$HOME/.local/share/applications/cdtracker.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=CDTracker
Comment=Cash deposit tracker (Goff Computer)
Exec=$HOME/.local/bin/cdtracker
Icon=accessories-calculator
Terminal=false
Categories=Office;Finance;
DESK

# Remove the old "Cash Deposit Tracker" launcher (its data is moved over
# to the NAS the first time CDTracker runs).
rm -f "$HOME/.local/bin/cash-tracker" \
      "$HOME/.local/share/applications/cash-tracker.desktop"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

if [ ! -f "$HOME/.config/cdtracker/smb-auth" ]; then
    python3 "$APP/cdtracker_desktop.py" --setup || true
fi
echo
echo "CDTracker $(python3 "$APP/cdtracker_desktop.py" --version | cut -d' ' -f2) installed."
echo "Open 'CDTracker' from your applications menu, or run: cdtracker"
