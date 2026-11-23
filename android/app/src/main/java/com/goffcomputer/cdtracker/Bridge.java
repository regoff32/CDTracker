package com.goffcomputer.cdtracker;

import android.app.Activity;
import android.webkit.JavascriptInterface;

import org.json.JSONObject;

/**
 * Called from the page's JavaScript as window.CDT. Answers the same
 * /api/... requests the Termux version's little web server does, so
 * one web/index.html works for both.
 */
final class Bridge {
    private final Activity activity;
    private final NasStore store;

    Bridge(Activity activity, NasStore store) {
        this.activity = activity;
        this.store = store;
    }

    @JavascriptInterface
    public synchronized String call(String path, String body) {
        try {
            JSONObject in = body == null ? null : new JSONObject(body);
            return handle(path, in).toString();
        } catch (Exception e) {
            try {
                return new JSONObject().put("error", "Error: " + e.getMessage()).toString();
            } catch (Exception ignored) {
                return "{\"error\":\"Error\"}";
            }
        }
    }

    @JavascriptInterface
    public void quit() {
        activity.runOnUiThread(activity::finish);
    }

    private JSONObject handle(String path, JSONObject in) throws Exception {
        if (path.equals("/api/state")) return state(true);
        if (path.equals("/api/settings")) {
            if (in == null) return store.settings();
            store.saveSettings(in);
            return state(true);
        }
        if (path.startsWith("/api/deposit/")) {
            long id = Long.parseLong(path.substring(path.lastIndexOf('/') + 1));
            try (CashBook b = store.openLocal()) {
                return new JSONObject().put("entries", b.batch(id));
            }
        }
        if (in == null) return state(false);

        try {
            switch (path) {
                case "/api/add": {
                    String d = Fmt.parseDate(in.optString("date"));
                    String n = in.optString("name");
                    long c = Fmt.toCents(in.optString("cash"));
                    store.write(b -> { b.add(d, n, c); return null; });
                    break;
                }
                case "/api/update": {
                    long id = in.getLong("id");
                    String d = Fmt.parseDate(in.optString("date"));
                    String n = in.optString("name");
                    long c = Fmt.toCents(in.optString("cash"));
                    store.write(b -> { b.update(id, d, n, c); return null; });
                    break;
                }
                case "/api/delete": {
                    long id = in.getLong("id");
                    store.write(b -> { b.delete(id); return null; });
                    break;
                }
                case "/api/deposit": {
                    String d = Fmt.parseDate(in.optString("date"));
                    String note = in.optString("note").trim();
                    store.write(b -> b.makeDeposit(d, note));
                    break;
                }
                case "/api/undo": {
                    long id = in.getLong("id");
                    store.write(b -> { b.undoDeposit(id); return null; });
                    break;
                }
                case "/api/target": {
                    long c = Fmt.toCents(in.optString("amount"));
                    store.write(b -> { b.setTarget(c); return null; });
                    break;
                }
                default:
                    return new JSONObject().put("error", "Unknown request " + path);
            }
        } catch (NasStore.SyncError e) {
            return state(false).put("error", "Not saved. " + e.getMessage());
        } catch (IllegalArgumentException e) {
            return state(false).put("error", e.getMessage());
        }
        return state(false);
    }

    private JSONObject state(boolean pull) throws Exception {
        JSONObject st = new JSONObject()
                .put("app", "CDTracker")
                .put("version", BuildConfig.VERSION_NAME);
        if (!store.isSetUp()) {
            return st.put("needSetup", true).put("status", store.statusText())
                    .put("online", false);
        }
        String err = null;
        if (pull) {
            try {
                store.pull();
            } catch (NasStore.SyncError e) {
                err = e.getMessage();
            }
        }
        try (CashBook b = store.openLocal()) {
            st.put("online", store.online)
                    .put("status", store.statusText())
                    .put("total", b.currentTotal())
                    .put("target", b.getTarget())
                    .put("current", b.batch(null))
                    .put("deposits", b.deposits());
        }
        if (err != null) st.put("error", err);
        return st;
    }
}
