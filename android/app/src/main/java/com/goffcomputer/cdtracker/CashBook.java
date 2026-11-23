package com.goffcomputer.cdtracker;

import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * The data file. Same tables as the Python version (cdtracker_core.py),
 * so the Debian and Android apps can share one file on the NAS.
 */
final class CashBook implements AutoCloseable {
    static final long DEFAULT_TARGET = 20000;   // $200.00
    private final SQLiteDatabase db;

    CashBook(String path) {
        // NO_LOCALIZED_COLLATORS keeps Android from adding its own
        // "android_metadata" table to the shared file.
        db = SQLiteDatabase.openDatabase(path, null,
                SQLiteDatabase.CREATE_IF_NECESSARY | SQLiteDatabase.NO_LOCALIZED_COLLATORS);
        // Plain single-file journal (no -wal files) so the copy on the
        // NAS is always complete and the Python version can read it.
        db.disableWriteAheadLogging();
        db.setForeignKeyConstraintsEnabled(true);
        db.execSQL("CREATE TABLE IF NOT EXISTS deposits ("
                + " id INTEGER PRIMARY KEY, dep_date TEXT NOT NULL,"
                + " total_cents INTEGER NOT NULL, note TEXT DEFAULT '')");
        db.execSQL("CREATE TABLE IF NOT EXISTS entries ("
                + " id INTEGER PRIMARY KEY, ent_date TEXT NOT NULL,"
                + " name TEXT NOT NULL, cents INTEGER NOT NULL,"
                + " deposit_id INTEGER REFERENCES deposits(id),"
                + " created TEXT DEFAULT CURRENT_TIMESTAMP)");
        db.execSQL("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)");
    }

    @Override
    public void close() {
        db.close();
    }

    // settings -------------------------------------------------------------
    long getTarget() {
        try (Cursor c = db.rawQuery("SELECT value FROM settings WHERE key='target_cents'", null)) {
            if (c.moveToFirst()) {
                try {
                    return Long.parseLong(c.getString(0));
                } catch (NumberFormatException ignored) {
                }
            }
            return DEFAULT_TARGET;
        }
    }

    void setTarget(long cents) {
        db.execSQL("INSERT OR REPLACE INTO settings VALUES ('target_cents', ?)",
                new Object[]{String.valueOf(cents)});
    }

    // entries --------------------------------------------------------------
    void add(String date, String name, long cents) {
        String n = name == null ? "" : name.trim();
        if (n.isEmpty()) throw new IllegalArgumentException("Enter a name.");
        db.execSQL("INSERT INTO entries (ent_date, name, cents) VALUES (?,?,?)",
                new Object[]{date, n, cents});
    }

    void update(long id, String date, String name, long cents) {
        String n = name == null ? "" : name.trim();
        if (n.isEmpty()) throw new IllegalArgumentException("Enter a name.");
        db.execSQL("UPDATE entries SET ent_date=?, name=?, cents=? WHERE id=?",
                new Object[]{date, n, cents, id});
        Long dep = depositOf(id);
        if (dep != null) recalc(dep);
    }

    void delete(long id) {
        Long dep = depositOf(id);
        db.execSQL("DELETE FROM entries WHERE id=?", new Object[]{id});
        if (dep != null) recalc(dep);
    }

    private Long depositOf(long id) {
        try (Cursor c = db.rawQuery("SELECT deposit_id FROM entries WHERE id=?",
                new String[]{String.valueOf(id)})) {
            if (c.moveToFirst() && !c.isNull(0)) return c.getLong(0);
            return null;
        }
    }

    private void recalc(long dep) {
        db.execSQL("UPDATE deposits SET total_cents = (SELECT COALESCE(SUM(cents),0)"
                + " FROM entries WHERE deposit_id=?) WHERE id=?", new Object[]{dep, dep});
    }

    /** Entries with running total. depositId null = not yet deposited. */
    JSONArray batch(Long depositId) throws JSONException {
        Cursor c = depositId == null
                ? db.rawQuery("SELECT id, ent_date, name, cents FROM entries"
                + " WHERE deposit_id IS NULL ORDER BY ent_date, id", null)
                : db.rawQuery("SELECT id, ent_date, name, cents FROM entries"
                + " WHERE deposit_id=? ORDER BY ent_date, id",
                new String[]{String.valueOf(depositId)});
        JSONArray out = new JSONArray();
        long run = 0;
        try {
            while (c.moveToNext()) {
                long cents = c.getLong(3);
                run += cents;
                String d = c.getString(1);
                out.put(new JSONObject()
                        .put("id", c.getLong(0))
                        .put("date", d)
                        .put("show", Fmt.showDate(d))
                        .put("name", c.getString(2))
                        .put("cents", cents)
                        .put("run", run));
            }
        } finally {
            c.close();
        }
        return out;
    }

    long currentTotal() {
        try (Cursor c = db.rawQuery(
                "SELECT COALESCE(SUM(cents),0) FROM entries WHERE deposit_id IS NULL", null)) {
            c.moveToFirst();
            return c.getLong(0);
        }
    }

    // deposits -------------------------------------------------------------
    long makeDeposit(String date, String note) {
        long total = currentTotal();
        if (total <= 0) throw new IllegalArgumentException("There is nothing to deposit.");
        db.beginTransaction();
        try {
            db.execSQL("INSERT INTO deposits (dep_date, total_cents, note) VALUES (?,?,?)",
                    new Object[]{date, total, note == null ? "" : note});
            long id;
            try (Cursor c = db.rawQuery("SELECT last_insert_rowid()", null)) {
                c.moveToFirst();
                id = c.getLong(0);
            }
            db.execSQL("UPDATE entries SET deposit_id=? WHERE deposit_id IS NULL",
                    new Object[]{id});
            db.setTransactionSuccessful();
            return total;
        } finally {
            db.endTransaction();
        }
    }

    void undoDeposit(long id) {
        db.beginTransaction();
        try {
            db.execSQL("UPDATE entries SET deposit_id=NULL WHERE deposit_id=?", new Object[]{id});
            db.execSQL("DELETE FROM deposits WHERE id=?", new Object[]{id});
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    JSONArray deposits() throws JSONException {
        JSONArray out = new JSONArray();
        try (Cursor c = db.rawQuery(
                "SELECT d.id, d.dep_date, d.total_cents, COUNT(e.id), d.note"
                        + " FROM deposits d LEFT JOIN entries e ON e.deposit_id=d.id"
                        + " GROUP BY d.id ORDER BY d.dep_date DESC, d.id DESC", null)) {
            while (c.moveToNext()) {
                String d = c.getString(1);
                out.put(new JSONObject()
                        .put("id", c.getLong(0))
                        .put("date", d)
                        .put("show", Fmt.showDate(d))
                        .put("cents", c.getLong(2))
                        .put("count", c.getLong(3))
                        .put("note", c.isNull(4) ? "" : c.getString(4)));
            }
        }
        return out;
    }
}
