"""
CDTracker - shared core (data + NAS sync)
Goff Computer cash deposit tracker.

The data file lives on the NAS:
  //<NAS Tailscale address>/notes/Backups/CDTracker Backup/cdtracker.db
Every change downloads the latest copy from the NAS, applies the
change, and uploads it right back, so the Debian and Android apps
always work from the same data. If the NAS can't be reached,
nothing is changed and the app says so.
"""

import configparser
import csv
import getpass
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

APP_NAME = "CDTracker"
VERSION = "5.0.6"
DEFAULT_TARGET = Decimal("200.00")

CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "cdtracker")
DATA_DIR = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "cdtracker")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.ini")
AUTH_FILE = os.path.join(CONFIG_DIR, "smb-auth")
OLD_DB = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "cash-tracker", "cash.db")

NAS_DEFAULTS = {
    "server": "",
    "share": "notes",
    "folder": "Backups/CDTracker Backup",
    "file": "cdtracker.db",
}

# --------------------------------------------------------------------------
# Data layer (no GUI code here)
# --------------------------------------------------------------------------

def to_cents(text):
    """'$1,234.5' -> 123450. Raises ValueError on bad input."""
    s = str(text).strip().replace("$", "").replace(",", "")
    if not s:
        raise ValueError("Enter an amount.")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"'{text}' is not a dollar amount.")
    if d <= 0:
        raise ValueError("Amount must be more than $0.")
    return int((d * 100).quantize(Decimal("1")))


def money(cents):
    return f"${Decimal(cents) / 100:,.2f}"


def parse_date(text):
    """Accepts 2026-11-22, 11/22/2026, 11/22/26, 11/22 (this year)."""
    s = str(text).strip()
    if not s:
        return date.today().isoformat()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        d = datetime.strptime(s, "%m/%d").date()
        return d.replace(year=date.today().year).isoformat()
    except ValueError:
        raise ValueError(f"'{text}' is not a date. Use MM/DD/YYYY.")


def show_date(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%d").strftime("%m/%d/%Y")
    except ValueError:
        return iso


class CashBook:
    def __init__(self, path):
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS deposits (
                id          INTEGER PRIMARY KEY,
                dep_date    TEXT NOT NULL,
                total_cents INTEGER NOT NULL,
                note        TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS entries (
                id          INTEGER PRIMARY KEY,
                ent_date    TEXT NOT NULL,
                name        TEXT NOT NULL,
                cents       INTEGER NOT NULL,
                deposit_id  INTEGER REFERENCES deposits(id),
                created     TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        self.db.commit()

    def close(self):
        try:
            self.db.close()
        except Exception:
            pass

    # settings ------------------------------------------------------------
    def get_target(self):
        r = self.db.execute(
            "SELECT value FROM settings WHERE key='target_cents'").fetchone()
        return int(r[0]) if r else int(DEFAULT_TARGET * 100)

    def set_target(self, cents):
        self.db.execute("INSERT OR REPLACE INTO settings VALUES "
                        "('target_cents', ?)", (str(cents),))
        self.db.commit()

    # entries -------------------------------------------------------------
    def add(self, ent_date, name, cents):
        name = name.strip()
        if not name:
            raise ValueError("Enter a name.")
        self.db.execute(
            "INSERT INTO entries (ent_date, name, cents) VALUES (?,?,?)",
            (ent_date, name, cents))
        self.db.commit()

    def update(self, entry_id, ent_date, name, cents):
        name = name.strip()
        if not name:
            raise ValueError("Enter a name.")
        self.db.execute(
            "UPDATE entries SET ent_date=?, name=?, cents=? WHERE id=?",
            (ent_date, name, cents, entry_id))
        self._refresh_deposit_total(entry_id)
        self.db.commit()

    def delete(self, entry_id):
        dep = self.db.execute("SELECT deposit_id FROM entries WHERE id=?",
                              (entry_id,)).fetchone()
        self.db.execute("DELETE FROM entries WHERE id=?", (entry_id,))
        if dep and dep[0]:
            self._recalc_deposit(dep[0])
        self.db.commit()

    def get(self, entry_id):
        return self.db.execute(
            "SELECT id, ent_date, name, cents, deposit_id FROM entries "
            "WHERE id=?", (entry_id,)).fetchone()

    def _refresh_deposit_total(self, entry_id):
        r = self.db.execute("SELECT deposit_id FROM entries WHERE id=?",
                            (entry_id,)).fetchone()
        if r and r[0]:
            self._recalc_deposit(r[0])

    def _recalc_deposit(self, dep_id):
        self.db.execute(
            "UPDATE deposits SET total_cents = (SELECT COALESCE(SUM(cents),0)"
            " FROM entries WHERE deposit_id=?) WHERE id=?", (dep_id, dep_id))

    def batch(self, deposit_id=None):
        """Entries in a batch with running total.
        deposit_id None = the current, not-yet-deposited batch."""
        if deposit_id is None:
            rows = self.db.execute(
                "SELECT id, ent_date, name, cents FROM entries "
                "WHERE deposit_id IS NULL ORDER BY ent_date, id").fetchall()
        else:
            rows = self.db.execute(
                "SELECT id, ent_date, name, cents FROM entries "
                "WHERE deposit_id=? ORDER BY ent_date, id",
                (deposit_id,)).fetchall()
        out, run = [], 0
        for rid, d, n, c in rows:
            run += c
            out.append((rid, d, n, c, run))
        return out

    def current_total(self):
        return self.db.execute(
            "SELECT COALESCE(SUM(cents),0) FROM entries "
            "WHERE deposit_id IS NULL").fetchone()[0]

    # deposits ------------------------------------------------------------
    def make_deposit(self, dep_date, note=""):
        total = self.current_total()
        if total <= 0:
            raise ValueError("There is nothing to deposit.")
        cur = self.db.execute(
            "INSERT INTO deposits (dep_date, total_cents, note) VALUES (?,?,?)",
            (dep_date, total, note))
        self.db.execute("UPDATE entries SET deposit_id=? "
                        "WHERE deposit_id IS NULL", (cur.lastrowid,))
        self.db.commit()
        return cur.lastrowid, total

    def undo_deposit(self, dep_id):
        """Put a deposit's entries back into the current batch."""
        self.db.execute("UPDATE entries SET deposit_id=NULL "
                        "WHERE deposit_id=?", (dep_id,))
        self.db.execute("DELETE FROM deposits WHERE id=?", (dep_id,))
        self.db.commit()

    def deposits(self):
        return self.db.execute(
            "SELECT d.id, d.dep_date, d.total_cents, COUNT(e.id), d.note "
            "FROM deposits d LEFT JOIN entries e ON e.deposit_id=d.id "
            "GROUP BY d.id ORDER BY d.dep_date DESC, d.id DESC").fetchall()

    @staticmethod
    def read_csv(path):
        """Read a CSV laid out like Export (DATE, NAME, CASH, TOTAL with
        a "*** DEPOSIT ***" line after each batch). TOTAL is ignored and
        worked out again. Returns (deposits, current) where deposits is
        a list of (iso_date, note, [(iso_date, name, cents), ...]) and
        current is the list of entries after the last deposit line.
        Raises ValueError naming the line if anything can't be read."""
        deposits, batch = [], []
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        for n, row in enumerate(rows, start=1):
            row = [c.strip() for c in row] + ["", "", "", ""]
            d, name, cash = row[0], row[1], row[2]
            if not any(row[:4]):
                continue
            if n == 1 and d.upper() == "DATE":
                continue
            try:
                if name.upper().startswith("*** DEPOSIT ***"):
                    note = name[len("*** DEPOSIT ***"):].strip()
                    if not batch:
                        raise ValueError("deposit line with no entries before it")
                    deposits.append((parse_date(d), note, batch))
                    batch = []
                    continue
                if not name:
                    raise ValueError("no name")
                batch.append((parse_date(d), name, to_cents(cash)))
            except ValueError as ex:
                raise ValueError(f"Line {n} of the file: {ex}")
        return deposits, batch

    def import_batches(self, deposits, current):
        """Add deposits (with their entries) and current entries, all at
        once - either everything goes in or nothing does."""
        try:
            for dep_date, note, entries in deposits:
                total = sum(c for _d, _n, c in entries)
                cur = self.db.execute(
                    "INSERT INTO deposits (dep_date, total_cents, note) "
                    "VALUES (?,?,?)", (dep_date, total, note))
                self.db.executemany(
                    "INSERT INTO entries (ent_date, name, cents, deposit_id) "
                    "VALUES (?,?,?,?)",
                    [(d, nm, c, cur.lastrowid) for d, nm, c in entries])
            self.db.executemany(
                "INSERT INTO entries (ent_date, name, cents) VALUES (?,?,?)",
                current)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def matching_deposits(self, deposits):
        """How many of these deposits (same date and amount) already exist."""
        n = 0
        for dep_date, _note, entries in deposits:
            total = sum(c for _d, _n, c in entries)
            if self.db.execute("SELECT 1 FROM deposits WHERE dep_date=? AND "
                               "total_cents=?", (dep_date, total)).fetchone():
                n += 1
        return n

    def export_csv(self, path):
        """Everything, laid out like the paper form: entries, then a
        DEPOSIT line after each batch."""
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["DATE", "NAME", "CASH", "TOTAL"])
            for dep_id, dd, total, _n, note in reversed(self.deposits()):
                for _id, d, n, c, run in self.batch(dep_id):
                    w.writerow([show_date(d), n, f"{c/100:.2f}",
                                f"{run/100:.2f}"])
                w.writerow([show_date(dd), "*** DEPOSIT ***" +
                            (f" {note}" if note else ""), "",
                            f"{total/100:.2f}"])
            for _id, d, n, c, run in self.batch(None):
                w.writerow([show_date(d), n, f"{c/100:.2f}",
                            f"{run/100:.2f}"])




# --------------------------------------------------------------------------
# Settings / NAS login
# --------------------------------------------------------------------------

class SyncError(Exception):
    pass


def load_config():
    cp = configparser.ConfigParser()
    cp.read(CONFIG_FILE)
    nas = dict(NAS_DEFAULTS)
    if cp.has_section("nas"):
        nas.update({k: v for k, v in cp.items("nas") if v})
    return nas


def save_config(nas, username=None, password=None, domain=""):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    cp = configparser.ConfigParser()
    cp["nas"] = {k: nas[k] for k in NAS_DEFAULTS}
    with open(CONFIG_FILE, "w") as f:
        cp.write(f)
    if username is not None:
        fd = os.open(AUTH_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(f"username = {username}\npassword = {password}\n")
            if domain:
                f.write(f"domain = {domain}\n")
        os.chmod(AUTH_FILE, 0o600)


def load_auth():
    """(username, password) saved for the NAS, or ("", "")."""
    user = pw = ""
    try:
        with open(AUTH_FILE) as f:
            for line in f:
                k, _, v = line.partition("=")
                if k.strip() == "username":
                    user = v.strip()
                elif k.strip() == "password":
                    pw = v.strip()
    except OSError:
        pass
    return user, pw


def is_set_up():
    return os.path.exists(AUTH_FILE) and bool(load_config()["server"])


def setup_terminal():
    """Ask for the NAS login in a terminal and test it."""
    nas = load_config()
    print(f"\n{APP_NAME} {VERSION} - NAS setup")
    print(f"Data file: //{nas['server']}/{nas['share']}/{nas['folder']}/"
          f"{nas['file']}")
    print("Press Enter to keep the value in [brackets].\n")
    for key, label in (("server", "NAS address (Tailscale IP)"),
                       ("share", "Share"), ("folder", "Folder")):
        while True:
            v = input(f"{label} [{nas[key]}]: ").strip()
            if v:
                nas[key] = v.strip("/")
            if nas[key]:
                break
    user = ""
    while not user:
        user = input("NAS (TrueNAS SMB) username: ").strip()
    pw = getpass.getpass("NAS password: ")
    save_config(nas, user, pw)
    print("\nTesting the connection...")
    try:
        Store().pull()
        print("OK - connected, and the data file is in place.")
        return 0
    except SyncError as ex:
        print(f"PROBLEM: {ex}")
        print("Run setup again to fix it:  cdtracker --setup")
        return 1


# --------------------------------------------------------------------------
# NAS sync with smbclient
# --------------------------------------------------------------------------

def _friendly(out):
    o = out.upper()
    if "LOGON_FAILURE" in o or "ACCESS_DENIED" in o and "TREE" not in o:
        return "The NAS rejected the username or password."
    if "BAD_NETWORK_NAME" in o:
        return "The share name on the NAS is wrong."
    if ("IO_TIMEOUT" in o or "HOST_UNREACHABLE" in o or "CONNECTION_REFUSED"
            in o or "NETWORK_UNREACHABLE" in o or "CONNECTION_DISCONNECTED"
            in o or "NOT_FOUND" in o and "CONNECTION" in o):
        return "Can't reach the NAS. Check that Tailscale is connected."
    if "ACCESS_DENIED" in o:
        return "The NAS user doesn't have permission to that folder."
    line = next((l for l in out.splitlines() if "NT_STATUS" in l), "")
    return f"NAS error: {line.strip() or out.strip()[:200]}"


class Store:
    """Keeps a local copy of the data file in step with the NAS."""

    def __init__(self):
        self.nas = load_config()
        os.makedirs(DATA_DIR, exist_ok=True)
        self.cache = os.path.join(DATA_DIR, "cdtracker.db")
        self.book = None
        self.last_sync = None      # datetime of last good NAS contact
        self.online = False

    # -- low level --------------------------------------------------------
    @staticmethod
    def _q(s):
        return '"' + s.replace('"', '') + '"'

    def _smb(self, commands, timeout=40):
        if not shutil.which("smbclient"):
            raise SyncError("smbclient is not installed.")
        if not os.path.exists(AUTH_FILE):
            raise SyncError("The NAS login isn't set up yet. "
                            "Run: cdtracker --setup")
        cmd = ["smbclient", f"//{self.nas['server']}/{self.nas['share']}",
               "-A", AUTH_FILE, "-c", "; ".join(commands)]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            self.online = False
            raise SyncError("Can't reach the NAS (timed out). "
                            "Check that Tailscale is connected.")
        out = (p.stdout or "") + (p.stderr or "")
        # Connection-level failures
        if "do_connect" in out or "tree connect failed" in out.lower() \
                or "session setup failed" in out.lower() \
                or "LOGON_FAILURE" in out:
            self.online = False
            raise SyncError(_friendly(out))
        return out

    def _cd(self):
        return f"cd {self._q(self.nas['folder'])}"

    def _ensure_folder(self):
        parts = [p for p in self.nas["folder"].split("/") if p]
        cmds, path = [], ""
        for p in parts:
            path = f"{path}/{p}" if path else p
            cmds.append(f"mkdir {self._q(path)}")
        self._smb(cmds)

    def _open(self):
        if self.book:
            self.book.close()
        self.book = CashBook(self.cache)

    # -- public -----------------------------------------------------------
    def open_local(self):
        """Open the last downloaded copy (for viewing when offline)."""
        self._open()

    def pull(self):
        """Download the NAS copy. Creates it on the NAS the first time."""
        tmp = self.cache + ".download"
        if os.path.exists(tmp):
            os.remove(tmp)
        fname = self.nas["file"]
        out = self._smb([self._cd(),
                         f"get {self._q(fname)} {self._q(tmp)}"])
        if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            if self.book:
                self.book.close()
                self.book = None
            os.replace(tmp, self.cache)
            self._open()
        elif "NAME_NOT_FOUND" in out or "PATH_NOT_FOUND" in out \
                or "NO_SUCH_FILE" in out:
            # No data file on the NAS yet: start it from what we have.
            if os.path.exists(tmp):
                os.remove(tmp)
            self._first_upload()
        else:
            self.online = False
            raise SyncError(_friendly(out))
        self.online = True
        self.last_sync = datetime.now()

    def _first_upload(self):
        if self.book:
            self.book.close()
            self.book = None
        if not os.path.exists(self.cache) and os.path.exists(OLD_DB):
            shutil.copy2(OLD_DB, self.cache)       # bring over old data
        self._open()
        self._ensure_folder()
        self.push()

    def push(self):
        """Upload the local copy to the NAS (safely: upload, then swap)."""
        self.book.db.commit()
        fname = self.nas["file"]
        new = fname + ".new"
        try:
            out = self._smb([self._cd(),
                             f"put {self._q(self.cache)} {self._q(new)}"])
            if "NT_STATUS" in out:
                raise SyncError(_friendly(out))
            out = self._smb([self._cd(),
                             f"rename {self._q(new)} {self._q(fname)} -f"])
            if "NT_STATUS" in out:
                # older smbclient without "rename -f": delete, then rename
                out = self._smb([self._cd(), f"del {self._q(fname)}",
                                 f"rename {self._q(new)} {self._q(fname)}"])
            # It worked if the ".new" file is gone.
            chk = self._smb([self._cd(), f"ls {self._q(new)}"])
            if "NOT_FOUND" not in chk and "NO_SUCH_FILE" not in chk:
                raise SyncError(_friendly(out))
        except SyncError:
            self.online = False
            raise
        self.online = True
        self.last_sync = datetime.now()

    def write(self, fn):
        """Get the latest from the NAS, apply fn(book), upload it back.
        If anything fails, the local copy is put back as it was and
        SyncError is raised - nothing is half-saved."""
        self.pull()
        backup = self.cache + ".before"
        self.book.db.commit()
        shutil.copy2(self.cache, backup)
        try:
            result = fn(self.book)
            self.push()
            return result
        except Exception:
            self.book.close()
            self.book = None
            shutil.copy2(backup, self.cache)
            self._open()
            raise

    def status_text(self):
        if self.online and self.last_sync:
            return f"Saved on NAS - last synced {self.last_sync:%I:%M %p}"
        if self.last_sync:
            return (f"NAS not reachable - showing copy from "
                    f"{self.last_sync:%m/%d %I:%M %p}")
        if os.path.exists(self.cache):
            t = datetime.fromtimestamp(os.path.getmtime(self.cache))
            return f"NAS not reachable - showing copy from {t:%m/%d %I:%M %p}"
        return "NAS not reachable"


def host_name():
    return socket.gethostname()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        sys.exit(setup_terminal())
    print(f"{APP_NAME} core {VERSION}")
