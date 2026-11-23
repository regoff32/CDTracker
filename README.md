# CDTracker

Cash deposit tracker for Goff Computer. It replaces the paper Cash Form
(DATE / NAME / CASH / TOTAL): add cash as it comes in, and when the
running total reaches about $200, record the deposit and start over.

One data file on the NAS (SMB share over Tailscale) is shared by:

| Part | Folder / file |
|------|---------------|
| Debian desktop app (Tk) | `cdtracker_desktop.py`, `install-debian.sh` |
| Android app (APK) | `android/` - built by GitHub Actions |
| Android via Termux (alternative) | `cdtracker_android.py`, `install-android.sh` |
| Shared phone screen | `web/index.html` (used by the APK and Termux) |
| Data + NAS sync (Python) | `cdtracker_core.py` |

Every change downloads the latest file from the NAS, applies the change,
and uploads it again, so all devices see the same data. If the NAS
can't be reached, nothing is saved and the app says so.

## Getting the APK

Every push that changes `android/` or `web/` builds a signed APK and
attaches it to **Releases** (tag `v<version>`). Download it on the phone
and install.

Signing uses four repository secrets: `CDT_KEYSTORE_BASE64`,
`CDT_KEYSTORE_PASSWORD`, `CDT_KEY_ALIAS`, `CDT_KEY_PASSWORD`. Without
them the APK is signed with a temporary debug key.

## Version

5.0.2 - the Debian and Android apps always share the same version number,
even when only one of them changed. Change `versionName`/`versionCode` in
`android/app/build.gradle` and `VERSION` in `cdtracker_core.py` together
(versionCode = 5.0.2 -> 50002).

See `README.txt` for step-by-step install instructions.
