#!/data/data/com.termux/files/usr/bin/sh
# CDTracker 5 - install on Android (run inside Termux)
set -e
cd "$(dirname "$0")"
APP="$HOME/.local/share/cdtracker/app"

echo "Installing Python and smbclient..."
pkg install -y python samba
if ! command -v smbclient >/dev/null 2>&1; then
    echo "smbclient didn't install. Run 'pkg update' and try again."
    exit 1
fi

mkdir -p "$APP/web"
cp cdtracker_core.py cdtracker_android.py "$APP/"
cp web/index.html "$APP/web/"

cat > "$PREFIX/bin/cdtracker" <<'LAUNCH'
#!/data/data/com.termux/files/usr/bin/sh
APP="$HOME/.local/share/cdtracker/app"
URL="http://127.0.0.1:8765/"
case "$1" in
  --setup|--version) exec python "$APP/cdtracker_android.py" "$@" ;;
esac
# Already running? Just open it.
if python -c "import urllib.request; urllib.request.urlopen('${URL}api/ping', timeout=1)" 2>/dev/null; then
    termux-open-url "$URL"
    exit 0
fi
[ -f "$HOME/.config/cdtracker/smb-auth" ] || python "$APP/cdtracker_android.py" --setup
(sleep 2; termux-open-url "$URL") &
exec python "$APP/cdtracker_android.py"
LAUNCH
chmod 755 "$PREFIX/bin/cdtracker"

# Home-screen shortcut for the Termux:Widget add-on
mkdir -p "$HOME/.shortcuts"
cat > "$HOME/.shortcuts/CDTracker" <<'SC'
#!/data/data/com.termux/files/usr/bin/sh
exec cdtracker
SC
chmod 755 "$HOME/.shortcuts/CDTracker"

if [ ! -f "$HOME/.config/cdtracker/smb-auth" ]; then
    python "$APP/cdtracker_android.py" --setup || true
fi
echo
echo "CDTracker installed. Start it by typing:  cdtracker"
echo "(or add the Termux:Widget to your home screen and tap CDTracker)"
