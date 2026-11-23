#!/usr/bin/env python3
"""
CDTracker - Debian desktop app (Goff Computer cash deposit tracker).
Replaces the paper Cash Form (DATE / NAME / CASH / TOTAL).
"""

import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from cdtracker_core import (APP_NAME, VERSION, Store, SyncError,  # noqa: E402
                            is_set_up, setup_terminal, parse_date, to_cents,
                            money, show_date)


def run_gui(store):
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, simpledialog

    root = tk.Tk()
    root.title(f"{APP_NAME} {VERSION} - Goff Computer")
    B = lambda: store.book  # noqa: E731
    root.geometry("760x620")
    root.minsize(640, 480)

    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure("Treeview", rowheight=26, font=("TkDefaultFont", 11))
    style.configure("Treeview.Heading", font=("TkDefaultFont", 11, "bold"))
    style.configure("Big.TLabel", font=("TkDefaultFont", 20, "bold"))
    style.configure("Ready.TLabel", font=("TkDefaultFont", 20, "bold"),
                    foreground="#0a7a0a")
    style.configure("Hint.TLabel", font=("TkDefaultFont", 11))
    style.configure("Deposit.TButton", font=("TkDefaultFont", 12, "bold"),
                    padding=8)

    # ---------------- Calendar picker ----------------
    import calendar as _cal

    def pick_date(var, near):
        """Pop up a month calendar under widget `near`; put the
        chosen date into StringVar `var` as MM/DD/YYYY."""
        try:
            sel = datetime.strptime(parse_date(var.get()), "%Y-%m-%d").date()
        except ValueError:
            sel = date.today()
        shown = [sel.year, sel.month]
        today = date.today()

        top = tk.Toplevel(near.winfo_toplevel())
        top.title("Pick a date")
        top.transient(near.winfo_toplevel())
        top.resizable(False, False)
        x = near.winfo_rootx()
        y = near.winfo_rooty() + near.winfo_height() + 2
        top.geometry(f"+{x}+{y}")

        head = ttk.Frame(top, padding=(6, 6, 6, 0))
        head.pack(fill="x")
        title = ttk.Label(head, font=("TkDefaultFont", 12, "bold"),
                          anchor="center")
        grid = ttk.Frame(top, padding=6)
        grid.pack()

        def choose(d):
            var.set(d.strftime("%m/%d/%Y"))
            top.destroy()
            near.focus_set()

        def draw():
            for w in grid.winfo_children():
                w.destroy()
            yr, mo = shown
            title.config(text=f"{_cal.month_name[mo]} {yr}")
            for c, dn in enumerate(("Su", "Mo", "Tu", "We", "Th", "Fr",
                                    "Sa")):
                ttk.Label(grid, text=dn, anchor="center", width=4).grid(
                    row=0, column=c)
            weeks = _cal.Calendar(firstweekday=6).monthdayscalendar(yr, mo)
            for r, wk in enumerate(weeks, start=1):
                for c, day in enumerate(wk):
                    if not day:
                        continue
                    d = date(yr, mo, day)
                    b = tk.Button(grid, text=str(day), width=3, relief="flat",
                                  command=lambda d=d: choose(d))
                    if d == sel:
                        b.config(bg="#2a6bc4", fg="white",
                                 activebackground="#1d4f94",
                                 activeforeground="white")
                    elif d == today:
                        b.config(bg="#d8e6f7", font=("TkDefaultFont", 10,
                                                     "bold"))
                    else:
                        b.config(bg="white")
                    b.grid(row=r, column=c, padx=1, pady=1)

        def move(months):
            m = shown[0] * 12 + (shown[1] - 1) + months
            shown[0], shown[1] = m // 12, m % 12 + 1
            draw()

        ttk.Button(head, text="«", width=3,
                   command=lambda: move(-12)).pack(side="left")
        ttk.Button(head, text="‹", width=3,
                   command=lambda: move(-1)).pack(side="left")
        ttk.Button(head, text="»", width=3,
                   command=lambda: move(12)).pack(side="right")
        ttk.Button(head, text="›", width=3,
                   command=lambda: move(1)).pack(side="right")
        title.pack(side="left", fill="x", expand=True)

        foot = ttk.Frame(top, padding=(6, 0, 6, 6))
        foot.pack(fill="x")
        ttk.Button(foot, text="Today",
                   command=lambda: choose(today)).pack(side="left")
        ttk.Button(foot, text="Cancel",
                   command=top.destroy).pack(side="right")

        top.bind("<Escape>", lambda e: top.destroy())
        top.bind("<Prior>", lambda e: move(-1))   # Page Up
        top.bind("<Next>", lambda e: move(1))     # Page Down
        draw()
        top.wait_visibility()
        top.grab_set()
        top.focus_set()

    def date_field(parent, var):
        """An entry with a calendar button next to it."""
        f = ttk.Frame(parent)
        e = ttk.Entry(f, textvariable=var, width=12,
                      font=("TkDefaultFont", 12))
        e.pack(side="left", fill="x", expand=True)
        b = ttk.Button(f, text="▾ Cal", width=5,
                       command=lambda: pick_date(var, f))
        b.pack(side="left", padx=(2, 0))
        e.bind("<Alt-Down>", lambda ev: pick_date(var, f))
        return f, e

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=8, pady=8)

    # ---------------- Current tab ----------------
    cur = ttk.Frame(nb, padding=8)
    nb.add(cur, text="  Current  ")

    form = ttk.LabelFrame(cur, text="Add cash", padding=8)
    form.pack(fill="x")

    date_var = tk.StringVar(value=date.today().strftime("%m/%d/%Y"))
    name_var = tk.StringVar()
    cash_var = tk.StringVar()

    ttk.Label(form, text="Date").grid(row=0, column=0, sticky="w")
    ttk.Label(form, text="Name").grid(row=0, column=1, sticky="w")
    ttk.Label(form, text="Cash").grid(row=0, column=2, sticky="w")
    date_box, date_e = date_field(form, date_var)
    name_e = ttk.Entry(form, textvariable=name_var, width=32,
                       font=("TkDefaultFont", 12))
    cash_e = ttk.Entry(form, textvariable=cash_var, width=10,
                       font=("TkDefaultFont", 12))
    date_box.grid(row=1, column=0, padx=(0, 6), sticky="we")
    name_e.grid(row=1, column=1, padx=(0, 6), sticky="we")
    cash_e.grid(row=1, column=2, padx=(0, 6), sticky="we")
    add_b = ttk.Button(form, text="Add")
    add_b.grid(row=1, column=3)
    form.columnconfigure(1, weight=1)

    cols = ("date", "name", "cash", "total")
    mid = ttk.Frame(cur)
    mid.pack(fill="both", expand=True, pady=8)
    tree = ttk.Treeview(mid, columns=cols, show="headings", height=12)
    for c, label, w, anchor in (("date", "DATE", 100, "center"),
                                ("name", "NAME", 300, "w"),
                                ("cash", "CASH", 100, "e"),
                                ("total", "TOTAL", 110, "e")):
        tree.heading(c, text=label)
        tree.column(c, width=w, anchor=anchor, stretch=(c == "name"))
    tree.tag_configure("odd", background="#f3f3f3")
    sb = ttk.Scrollbar(mid, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")

    bottom = ttk.Frame(cur)
    bottom.pack(fill="x")
    total_lbl = ttk.Label(bottom, text="", style="Big.TLabel")
    total_lbl.pack(side="left")
    hint_lbl = ttk.Label(bottom, text="", style="Hint.TLabel")
    hint_lbl.pack(side="left", padx=12)
    dep_b = ttk.Button(bottom, text="Make Deposit", style="Deposit.TButton")
    dep_b.pack(side="right")

    btns = ttk.Frame(cur)
    btns.pack(fill="x", pady=(8, 0))
    edit_b = ttk.Button(btns, text="Edit selected")
    del_b = ttk.Button(btns, text="Delete selected")
    edit_b.pack(side="left")
    del_b.pack(side="left", padx=6)
    ttk.Label(btns, text="Tip: press Enter in the Cash box to add.",
              style="Hint.TLabel").pack(side="right")

    # ---------------- History tab ----------------
    hist = ttk.Frame(nb, padding=8)
    nb.add(hist, text="  Deposit History  ")

    hpane = ttk.PanedWindow(hist, orient="vertical")
    hpane.pack(fill="both", expand=True)

    dtop = ttk.Frame(hpane)
    dtree = ttk.Treeview(dtop, columns=("date", "count", "total", "note"),
                         show="headings", height=8)
    for c, label, w, anchor in (("date", "DEPOSIT DATE", 120, "center"),
                                ("count", "ENTRIES", 80, "center"),
                                ("total", "AMOUNT", 110, "e"),
                                ("note", "NOTE", 300, "w")):
        dtree.heading(c, text=label)
        dtree.column(c, width=w, anchor=anchor, stretch=(c == "note"))
    dsb = ttk.Scrollbar(dtop, orient="vertical", command=dtree.yview)
    dtree.configure(yscrollcommand=dsb.set)
    dtree.pack(side="left", fill="both", expand=True)
    dsb.pack(side="right", fill="y")
    hpane.add(dtop, weight=1)

    dbot = ttk.Frame(hpane)
    ttk.Label(dbot, text="Entries in selected deposit:",
              style="Hint.TLabel").pack(anchor="w", pady=(6, 2))
    detail = ttk.Treeview(dbot, columns=cols, show="headings", height=8)
    for c, label, w, anchor in (("date", "DATE", 100, "center"),
                                ("name", "NAME", 300, "w"),
                                ("cash", "CASH", 100, "e"),
                                ("total", "TOTAL", 110, "e")):
        detail.heading(c, text=label)
        detail.column(c, width=w, anchor=anchor, stretch=(c == "name"))
    detail.tag_configure("odd", background="#f3f3f3")
    detail.pack(fill="both", expand=True)
    hpane.add(dbot, weight=1)

    hbtns = ttk.Frame(hist)
    hbtns.pack(fill="x", pady=(8, 0))
    hedit_b = ttk.Button(hbtns, text="Edit entry")
    undo_b = ttk.Button(hbtns, text="Undo deposit")
    exp_b = ttk.Button(hbtns, text="Export all to CSV...")
    hedit_b.pack(side="left")
    undo_b.pack(side="left", padx=6)
    exp_b.pack(side="right")

    # ---------------- Menu ----------------
    menubar = tk.Menu(root)
    filem = tk.Menu(menubar, tearoff=0)
    filem.add_command(label="Export all to CSV...",
                      command=lambda: export())
    filem.add_command(label="Set deposit target...",
                      command=lambda: set_target())
    filem.add_separator()
    nas = store.nas
    filem.add_command(label="Refresh from NAS  (F5)",
                      command=lambda: pull_now())
    filem.add_command(
        label=f"Data: //{nas['server']}/{nas['share']}/{nas['folder']}/"
              f"{nas['file']}", state="disabled")
    filem.add_separator()
    filem.add_command(label="Quit", command=root.destroy)
    menubar.add_cascade(label="File", menu=filem)
    helpm = tk.Menu(menubar, tearoff=0)
    helpm.add_command(label=f"About {APP_NAME}", command=lambda: messagebox.showinfo(
        f"About {APP_NAME}",
        f"{APP_NAME} version {VERSION}\nGoff Computer cash deposit tracker\n\n"
        f"Data is kept on the NAS and shared with the Android app.",
        parent=root))
    menubar.add_cascade(label="Help", menu=helpm)

    status_var = tk.StringVar()
    status_lbl = tk.Label(root, textvariable=status_var, anchor="w",
                          padx=10, font=("TkDefaultFont", 10))
    status_lbl.pack(side="bottom", fill="x", before=nb)

    def show_status():
        status_var.set(store.status_text())
        status_lbl.config(fg="#1d5e1d" if store.online else "#b00020")

    def save(fn, parent=None):
        """Run a change through the NAS. Returns (ok, result)."""
        root.config(cursor="watch")
        status_var.set("Saving to NAS...")
        root.update_idletasks()
        try:
            r = fn(store.book)
            ok = True
        except SyncError as ex:
            ok, r = False, None
            messagebox.showerror(
                APP_NAME, f"Not saved.\n\n{ex}", parent=parent or root)
        except ValueError as ex:
            ok, r = False, None
            messagebox.showerror(APP_NAME, str(ex), parent=parent or root)
        finally:
            root.config(cursor="")
        refresh()
        return ok, r

    def pull_now(_e=None):
        root.config(cursor="watch")
        status_var.set("Getting latest from NAS...")
        root.update_idletasks()
        try:
            store.pull()
        except SyncError as ex:
            messagebox.showerror(APP_NAME, str(ex), parent=root)
        finally:
            root.config(cursor="")
        refresh()
    root.config(menu=menubar)

    # ---------------- Logic ----------------
    def fill(tv, rows):
        tv.delete(*tv.get_children())
        for i, (rid, d, n, c, run) in enumerate(rows):
            tv.insert("", "end", iid=str(rid),
                      values=(show_date(d), n, money(c), money(run)),
                      tags=("odd",) if i % 2 else ())
        kids = tv.get_children()
        if kids:
            tv.see(kids[-1])

    def refresh():
        show_status()
        fill(tree, B().batch(None))
        total = B().current_total()
        target = B().get_target()
        total_lbl.config(text=f"Total: {money(total)}")
        if total >= target:
            total_lbl.config(style="Ready.TLabel")
            hint_lbl.config(text=f"Ready to deposit (target {money(target)})")
        else:
            total_lbl.config(style="Big.TLabel")
            hint_lbl.config(
                text=f"{money(target - total)} to go until {money(target)}")
        dep_b.state(["!disabled"] if total > 0 else ["disabled"])
        refresh_history()

    def refresh_history(select=None):
        dtree.delete(*dtree.get_children())
        for dep_id, dd, total, n, note in B().deposits():
            dtree.insert("", "end", iid=str(dep_id),
                         values=(show_date(dd), n, money(total), note or ""))
        if select and dtree.exists(str(select)):
            dtree.selection_set(str(select))
        else:
            detail.delete(*detail.get_children())

    def show_detail(_e=None):
        sel = dtree.selection()
        if sel:
            fill(detail, B().batch(int(sel[0])))

    def add(_e=None):
        try:
            d = parse_date(date_var.get())
            c = to_cents(cash_var.get())
            n = name_var.get().strip()
            if not n:
                raise ValueError("Enter a name.")
        except ValueError as ex:
            messagebox.showerror(APP_NAME, str(ex), parent=root)
            return
        ok, _ = save(lambda b: store.write(lambda bk: bk.add(d, n, c)))
        if ok:
            name_var.set("")
            cash_var.set("")
        name_e.focus_set()

    def edit_dialog(entry_id, after):
        row = B().get(entry_id)
        if not row:
            return
        _id, d, n, c, _dep = row
        win = tk.Toplevel(root)
        win.title("Edit entry")
        win.transient(root)
        win.resizable(False, False)
        f = ttk.Frame(win, padding=12)
        f.pack()
        dv = tk.StringVar(value=show_date(d))
        nv = tk.StringVar(value=n)
        cv = tk.StringVar(value=f"{c/100:.2f}")
        ttk.Label(f, text="Date").grid(row=0, column=0, sticky="w", pady=3)
        date_field(f, dv)[0].grid(row=0, column=1, sticky="w", pady=3)
        for r, (lbl, var, w) in enumerate((("Name", nv, 32),
                                           ("Cash", cv, 12)), start=1):
            ttk.Label(f, text=lbl).grid(row=r, column=0, sticky="w", pady=3)
            ttk.Entry(f, textvariable=var, width=w,
                      font=("TkDefaultFont", 12)).grid(
                row=r, column=1, sticky="w", pady=3)

        def save(_e=None):
            try:
                nd, nn, nc = parse_date(dv.get()), nv.get(), to_cents(cv.get())
            except ValueError as ex:
                messagebox.showerror(APP_NAME, str(ex), parent=win)
                return
            ok, _ = save(lambda b: store.write(
                lambda bk: bk.update(entry_id, nd, nn, nc)), parent=win)
            if ok:
                win.destroy()
                after()

        bf = ttk.Frame(f)
        bf.grid(row=3, column=0, columnspan=2, pady=(10, 0), sticky="e")
        ttk.Button(bf, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(bf, text="Save", command=save).pack(side="right", padx=6)
        win.bind("<Return>", save)
        win.bind("<Escape>", lambda e: win.destroy())
        win.grab_set()

    def edit_current(_e=None):
        sel = tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a line first.", parent=root)
            return
        edit_dialog(int(sel[0]), refresh)

    def delete_current():
        sel = tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a line first.", parent=root)
            return
        _id, d, n, c, _dep = B().get(int(sel[0]))
        if messagebox.askyesno(
                APP_NAME, f"Delete {n}  {money(c)}  ({show_date(d)})?",
                parent=root):
            eid = int(sel[0])
            save(lambda b: store.write(lambda bk: bk.delete(eid)))

    def edit_history(_e=None):
        dsel = dtree.selection()
        sel = detail.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select an entry in the lower list.",
                                parent=root)
            return

        def after():
            refresh()
            if dsel:
                dtree.selection_set(dsel[0])
                show_detail()
        edit_dialog(int(sel[0]), after)

    def make_deposit():
        total = B().current_total()
        if total <= 0:
            return
        target = B().get_target()
        msg = f"Deposit {money(total)}?"
        if total < target:
            msg += f"\n\n(That's under the {money(target)} target.)"
        win = tk.Toplevel(root)
        win.title("Make Deposit")
        win.transient(root)
        win.resizable(False, False)
        f = ttk.Frame(win, padding=12)
        f.pack()
        ttk.Label(f, text=msg, font=("TkDefaultFont", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        dv = tk.StringVar(value=date.today().strftime("%m/%d/%Y"))
        nv = tk.StringVar()
        ttk.Label(f, text="Deposit date").grid(row=1, column=0, sticky="w",
                                               pady=3)
        date_field(f, dv)[0].grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(f, text="Note (optional)").grid(row=2, column=0,
                                                  sticky="w", pady=3)
        ttk.Entry(f, textvariable=nv, width=28,
                  font=("TkDefaultFont", 12)).grid(row=2, column=1,
                                                   sticky="w", pady=3)
        result = {}

        def ok(_e=None):
            try:
                result["iso"] = parse_date(dv.get())
            except ValueError as ex:
                messagebox.showerror(APP_NAME, str(ex), parent=win)
                return
            result["note"] = nv.get().strip()
            win.destroy()

        bf = ttk.Frame(f)
        bf.grid(row=3, column=0, columnspan=2, pady=(10, 0), sticky="e")
        ttk.Button(bf, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(bf, text="Deposit", command=ok).pack(side="right", padx=6)
        win.bind("<Return>", ok)
        win.bind("<Escape>", lambda e: win.destroy())
        win.wait_visibility()
        win.grab_set()
        root.wait_window(win)
        if "iso" not in result:
            return
        iso = result["iso"]
        ok, r = save(lambda b: store.write(
            lambda bk: bk.make_deposit(iso, result["note"])))
        if not ok:
            return
        dep_id, amt = r
        refresh_history(select=dep_id)
        show_detail()
        messagebox.showinfo(
            APP_NAME, f"Deposit of {money(amt)} recorded for "
                      f"{show_date(iso)}.\nStarting over at $0.00.",
            parent=root)

    def undo_deposit():
        sel = dtree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a deposit first.",
                                parent=root)
            return
        vals = dtree.item(sel[0], "values")
        if messagebox.askyesno(
                APP_NAME, f"Undo the {vals[2]} deposit from {vals[0]}?\n\n"
                          "Its entries go back to the Current list.",
                parent=root):
            did = int(sel[0])
            save(lambda b: store.write(lambda bk: bk.undo_deposit(did)))

    def export():
        path = filedialog.asksaveasfilename(
            parent=root, title="Export to CSV", defaultextension=".csv",
            initialfile=f"cash-deposits-{date.today().isoformat()}.csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*")])
        if path:
            B().export_csv(path)
            messagebox.showinfo(APP_NAME, f"Saved:\n{path}", parent=root)

    def set_target():
        v = simpledialog.askstring(
            APP_NAME, "Deposit when the total reaches:",
            initialvalue=f"{B().get_target()/100:.2f}", parent=root)
        if v is None:
            return
        try:
            cents = to_cents(v)
        except ValueError as ex:
            messagebox.showerror(APP_NAME, str(ex), parent=root)
            return
        save(lambda b: store.write(lambda bk: bk.set_target(cents)))

    add_b.config(command=add)
    cash_e.bind("<Return>", add)
    cash_e.bind("<KP_Enter>", add)
    name_e.bind("<Return>", lambda e: cash_e.focus_set())
    date_e.bind("<Return>", lambda e: name_e.focus_set())
    tree.bind("<Double-1>", edit_current)
    tree.bind("<Delete>", lambda e: delete_current())
    edit_b.config(command=edit_current)
    del_b.config(command=delete_current)
    dep_b.config(command=make_deposit)
    dtree.bind("<<TreeviewSelect>>", show_detail)
    detail.bind("<Double-1>", edit_history)
    hedit_b.config(command=edit_history)
    undo_b.config(command=undo_deposit)
    exp_b.config(command=export)

    root.bind("<F5>", pull_now)
    refresh()
    if not store.online:
        root.after(300, lambda: messagebox.showwarning(
            APP_NAME, "Couldn't reach the NAS, so this is the last copy "
            "downloaded. You can look, but changes can't be saved until "
            "the NAS is reachable (check Tailscale), then press F5.",
            parent=root))
    name_e.focus_set()
    root.mainloop()




def main():
    if "--version" in sys.argv:
        print(f"{APP_NAME} {VERSION}")
        return
    if "--setup" in sys.argv or not is_set_up():
        if not sys.stdin.isatty() and not is_set_up():
            sys.exit("CDTracker isn't set up. Run in a terminal: cdtracker --setup")
        rc = setup_terminal()
        if "--setup" in sys.argv:
            sys.exit(rc)
    try:
        import tkinter  # noqa: F401
    except ImportError:
        sys.exit("tkinter is missing. Install it with:\n"
                 "  sudo apt install python3-tk")
    store = Store()
    try:
        store.pull()
    except SyncError as ex:
        print(f"NAS: {ex}", file=sys.stderr)
        store.open_local()
    run_gui(store)


if __name__ == "__main__":
    main()
