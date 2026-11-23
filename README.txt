CDTracker 5.0.0 - Goff Computer cash deposit tracker
====================================================

The data file is kept on the NAS at:
  smb://<NAS Tailscale address>/notes/Backups/CDTracker Backup/cdtracker.db

The Debian and Android apps share that one file. Each time you add,
edit, delete or deposit, the app gets the latest copy from the NAS,
makes the change, and puts it right back. So whichever device you
pick up, it shows the latest data.

If the NAS can't be reached (Tailscale off, no internet), you can
still look at the last copy, but nothing gets saved. The app tells
you "Not saved", and what you typed stays in the boxes so you can
try again.

You'll need: the NAS's Tailscale address (100.x.x.x), and the TrueNAS
SMB username and password that can write to the "notes" share.


IMPORTANT - DO THE DEBIAN COMPUTER FIRST
----------------------------------------
Your current entries are on the Debian computer where you've been
using "Cash Deposit Tracker". The first time CDTracker runs there,
it copies those entries up to the NAS. Install on that computer
before the Android device, or the Android app will start a new,
empty file on the NAS instead.


1. DEBIAN
---------
Easiest: the .deb package.

a) Download cdtracker_x.x.x_all.deb from
     https://github.com/regoff32/CDTracker/releases
   (or use the one in the CDTracker package zip).
b) In a terminal, from the folder it's in:

     sudo apt install ./cdtracker_5.0.3_all.deb

   apt also installs what it needs (python3-tk, smbclient).
c) Open "CDTracker" from the applications menu. The first time on a
   computer, a NAS settings window asks for:
     NAS address : your NAS's Tailscale IP (100.x.x.x)
     Share       : notes
     Folder      : Backups/CDTracker Backup
     File name   : cdtracker.db
     Username / Password : your TrueNAS SMB login
   Click "Save & connect". (A computer that was already set up
   keeps its settings and skips this.)

To update: install the newer .deb the same way.
To remove:  sudo apt remove cdtracker   (data on the NAS is untouched)

If this computer had the older install-debian.sh version, remove its
copy first so the menu uses the .deb one (settings are kept):

     rm -f ~/.local/bin/cdtracker ~/.local/share/applications/cdtracker.desktop
     rm -rf ~/.local/share/cdtracker/app

In the window:
- Status line at the bottom: green = saved on NAS, red = NAS not
  reachable.
- File > Refresh from NAS (or F5) gets the latest copy, e.g. after
  using the Android app.
- File > NAS settings... changes the NAS address or login.
- Select all / Ctrl+click / Shift+click to pick several lines, then
  Delete selected.
- Help > About shows the version.

Without the .deb: from the source folder, run  bash install-debian.sh
(installs just for your user).


2. ANDROID APP (APK) - recommended
----------------------------------
GitHub builds the app every time the code changes.

a) Make sure Tailscale is installed and connected on the phone.
b) On the phone, open:
     https://github.com/regoff32/CDTracker/releases
   and tap the newest CDTracker-x.x.x.apk to download it.
c) Open the downloaded file. If Android asks, allow your browser
   to "install unknown apps", then tap Install.
d) Open CDTracker. The NAS settings screen appears the first time:
     NAS address : your NAS's Tailscale IP (100.x.x.x)
     Share       : notes
     Folder      : Backups/CDTracker Backup
     File name   : cdtracker.db
     Username / Password : your TrueNAS SMB login
   Tap "Save & connect".

To update later: download the newer APK from Releases and install
it over the old one. Your settings stay.

The "Settings" button at the bottom changes the NAS login later.


3. ANDROID WITH TERMUX (alternative, no APK)
-------------------------------------------
This version runs in Termux and opens in your browser.

a) Install from F-Droid (not the Play Store - those versions are
   out of date):
     - Termux
     - Termux:Widget   (optional - gives a home-screen button)
b) Make sure Tailscale is installed and connected on the device.
c) Get the CDTracker-5.0.0.tar.gz file onto the device (Downloads).
d) Open Termux and run:

  termux-setup-storage
  cd ~
  tar xzf ~/storage/downloads/CDTracker-5.0.0.tar.gz
  cd CDTracker
  sh install-android.sh

   (termux-setup-storage asks for permission to see Downloads -
    tap Allow.)
e) Enter the NAS username and password when asked.

To start it:
  - type  cdtracker  in Termux, or
  - long-press the home screen > Widgets > Termux:Widget, place it,
    and tap "CDTracker".

The app opens in the browser. Leave the Termux window open while
you use it. Tap "Quit" in the app when you're done.

Tips on Android:
- The Date box opens Android's own calendar.
- Tap a line to edit or delete it.
- Deposit History: tap a deposit to see its entries, or to undo it.
- Coming back to the browser tab gets the latest data automatically.
- "Add to Home screen" from the browser's menu makes a shortcut, but
  Termux still needs to be running (start it with cdtracker or the
  widget first).


CHANGING THE NAS PASSWORD OR ADDRESS
------------------------------------
Debian: File > NAS settings...   (or in a terminal: cdtracker --setup)
Termux: cdtracker --setup

Settings live in ~/.config/cdtracker/ (the password file can only be
read by your user).


WHERE THINGS ARE
----------------
NAS data file:  notes/Backups/CDTracker Backup/cdtracker.db
Local copy:     ~/.local/share/cdtracker/cdtracker.db   (last download)
Program files:  ~/.local/share/cdtracker/app/
Check version:  cdtracker --version


TROUBLESHOOTING
---------------
"Can't reach the NAS"      -> Turn on or reconnect Tailscale, then
                              press F5 (Debian) or Refresh (Android).
"rejected the username..." -> Run  cdtracker --setup  again.
"doesn't have permission"  -> Give that NAS user write access to
                              notes/Backups in TrueNAS.
Android page won't load    -> CDTracker isn't running. Start it with
                              cdtracker or the widget.
