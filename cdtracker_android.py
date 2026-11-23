#!/usr/bin/env python3
"""
CDTracker - Android version (runs in Termux).
Starts a small private web server on the phone/tablet itself
(127.0.0.1 only - nothing outside the device can reach it) and the
app opens in the browser. Data is the same NAS file the Debian app uses.
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
from cdtracker_core import (APP_NAME, VERSION, Store, SyncError,  # noqa: E402
                            is_set_up, setup_terminal, parse_date, to_cents,
                            show_date)

PORT = 8765
STORE = Store()


def state(pull=True):
    msg = None
    if pull:
        try:
            STORE.pull()
        except SyncError as ex:
            msg = str(ex)
            if STORE.book is None:
                STORE.open_local()
    b = STORE.book
    total, target = b.current_total(), b.get_target()
    return {
        "app": APP_NAME, "version": VERSION,
        "online": STORE.online, "status": STORE.status_text(),
        "error": msg,
        "total": total, "target": target,
        "current": [{"id": i, "date": d, "show": show_date(d), "name": n,
                     "cents": c, "run": r} for i, d, n, c, r in b.batch(None)],
        "deposits": [{"id": i, "date": d, "show": show_date(d),
                      "cents": t, "count": k, "note": note or ""}
                     for i, d, t, k, note in b.deposits()],
    }


def entries_of(dep_id):
    return [{"id": i, "date": d, "show": show_date(d), "name": n,
             "cents": c, "run": r} for i, d, n, c, r in STORE.book.batch(dep_id)]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            with open(os.path.join(HERE, "web", "index.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif p == "/api/ping":
            self._send(200, {"ok": True, "app": APP_NAME})
        elif p == "/api/state":
            self._send(200, state(pull=True))
        elif p.startswith("/api/deposit/"):
            self._send(200, {"entries": entries_of(int(p.rsplit("/", 1)[1]))})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        # Only accept requests from this device's own pages.
        if self.headers.get("X-CDTracker") != "1":
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._send(400, {"error": "bad request"})
        p = self.path
        try:
            if p == "/api/add":
                d, nm, c = (parse_date(data.get("date", "")),
                            data.get("name", ""), to_cents(data.get("cash")))
                STORE.write(lambda b: b.add(d, nm, c))
            elif p == "/api/update":
                i = int(data["id"])
                d, nm, c = (parse_date(data.get("date", "")),
                            data.get("name", ""), to_cents(data.get("cash")))
                STORE.write(lambda b: b.update(i, d, nm, c))
            elif p == "/api/delete":
                i = int(data["id"])
                STORE.write(lambda b: b.delete(i))
            elif p == "/api/deposit":
                d, note = parse_date(data.get("date", "")), \
                    str(data.get("note", "")).strip()
                STORE.write(lambda b: b.make_deposit(d, note))
            elif p == "/api/undo":
                i = int(data["id"])
                STORE.write(lambda b: b.undo_deposit(i))
            elif p == "/api/target":
                c = to_cents(data.get("amount"))
                STORE.write(lambda b: b.set_target(c))
            elif p == "/api/quit":
                self._send(200, {"ok": True})
                threading.Thread(target=SERVER.shutdown, daemon=True).start()
                return
            else:
                return self._send(404, {"error": "not found"})
        except SyncError as ex:
            st = state(pull=False)
            st["error"] = f"Not saved. {ex}"
            return self._send(200, st)
        except ValueError as ex:
            st = state(pull=False)
            st["error"] = str(ex)
            return self._send(200, st)
        self._send(200, state(pull=False))


SERVER = None


def main():
    global SERVER
    if "--version" in sys.argv:
        print(f"{APP_NAME} {VERSION}")
        return
    if "--setup" in sys.argv or not is_set_up():
        rc = setup_terminal()
        if "--setup" in sys.argv:
            sys.exit(rc)
    SERVER = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"{APP_NAME} {VERSION} running at http://127.0.0.1:{PORT}/")
    print("Leave this open while you use the app. Tap Quit in the app "
          "(or press Ctrl+C here) when done.")
    try:
        SERVER.serve_forever()
    except KeyboardInterrupt:
        pass
    print(f"{APP_NAME} stopped.")


if __name__ == "__main__":
    main()
