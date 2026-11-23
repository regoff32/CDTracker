package com.goffcomputer.cdtracker;

import android.content.Context;
import android.content.SharedPreferences;

import com.hierynomus.msdtyp.AccessMask;
import com.hierynomus.mserref.NtStatus;
import com.hierynomus.msfscc.FileAttributes;
import com.hierynomus.mssmb2.SMB2CreateDisposition;
import com.hierynomus.mssmb2.SMB2CreateOptions;
import com.hierynomus.mssmb2.SMB2ShareAccess;
import com.hierynomus.mssmb2.SMBApiException;
import com.hierynomus.security.bc.BCSecurityProvider;
import com.hierynomus.smbj.SMBClient;
import com.hierynomus.smbj.SmbConfig;
import com.hierynomus.smbj.auth.AuthenticationContext;
import com.hierynomus.smbj.connection.Connection;
import com.hierynomus.smbj.session.Session;
import com.hierynomus.smbj.share.DiskShare;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.EnumSet;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

/**
 * Keeps the local copy of the data file in step with the NAS.
 * Every change: download the latest, apply it, upload it right back.
 * Same rules as Store in cdtracker_core.py.
 */
final class NasStore {

    static final class SyncError extends Exception {
        SyncError(String msg) {
            super(msg);
        }
    }

    interface Op<T> {
        T run(CashBook b) throws Exception;
    }

    private interface ShareOp<T> {
        T run(DiskShare share) throws Exception;
    }

    private final SharedPreferences prefs;
    private final File cache, tmp, before;
    boolean online = false;
    private long lastSync = 0;

    NasStore(Context ctx) {
        prefs = ctx.getSharedPreferences("nas", Context.MODE_PRIVATE);
        File dir = ctx.getFilesDir();
        cache = new File(dir, "cdtracker.db");
        tmp = new File(dir, "cdtracker.db.download");
        before = new File(dir, "cdtracker.db.before");
    }

    // ---- settings ---------------------------------------------------------
    private String pref(String k, String def) {
        return prefs.getString(k, def);
    }

    boolean isSetUp() {
        return !pref("server", "").isEmpty() && !pref("user", "").isEmpty();
    }

    JSONObject settings() throws JSONException {
        return new JSONObject()
                .put("server", pref("server", ""))
                .put("share", pref("share", "notes"))
                .put("folder", pref("folder", "Backups/CDTracker Backup"))
                .put("file", pref("file", "cdtracker.db"))
                .put("user", pref("user", ""))
                .put("domain", pref("domain", ""))
                .put("hasPassword", !pref("password", "").isEmpty());
    }

    void saveSettings(JSONObject j) {
        SharedPreferences.Editor e = prefs.edit();
        for (String k : new String[]{"server", "share", "folder", "file", "user", "domain"}) {
            e.putString(k, j.optString(k, "").trim());
        }
        String pw = j.optString("password", "");
        if (!pw.isEmpty()) e.putString("password", pw);
        e.apply();
    }

    // ---- local copy -------------------------------------------------------
    CashBook openLocal() {
        return new CashBook(cache.getPath());
    }

    String statusText() {
        if (!isSetUp()) return "NAS not set up - tap Settings";
        SimpleDateFormat t = new SimpleDateFormat("h:mm a", Locale.US);
        SimpleDateFormat dt = new SimpleDateFormat("MM/dd h:mm a", Locale.US);
        if (online && lastSync > 0) return "Saved on NAS - last synced " + t.format(new Date(lastSync));
        if (lastSync > 0) return "NAS not reachable - showing copy from " + dt.format(new Date(lastSync));
        if (cache.exists())
            return "NAS not reachable - showing copy from " + dt.format(new Date(cache.lastModified()));
        return "NAS not reachable";
    }

    // ---- SMB --------------------------------------------------------------
    private String smbPath(String name) {
        String folder = pref("folder", "").replace('/', '\\');
        while (folder.startsWith("\\")) folder = folder.substring(1);
        while (folder.endsWith("\\")) folder = folder.substring(0, folder.length() - 1);
        return folder.isEmpty() ? name : folder + "\\" + name;
    }

    private <T> T withShare(ShareOp<T> op) throws SyncError {
        if (!isSetUp()) throw new SyncError("The NAS isn't set up yet. Tap Settings.");
        SmbConfig cfg = SmbConfig.builder()
                .withSecurityProvider(new BCSecurityProvider())
                .withTimeout(30, TimeUnit.SECONDS)
                .withSoTimeout(30, TimeUnit.SECONDS)
                .build();
        try (SMBClient client = new SMBClient(cfg);
             Connection conn = client.connect(pref("server", ""))) {
            AuthenticationContext ac = new AuthenticationContext(
                    pref("user", ""), pref("password", "").toCharArray(), pref("domain", ""));
            try (Session session = conn.authenticate(ac);
                 DiskShare share = (DiskShare) session.connectShare(pref("share", "notes"))) {
                T r = op.run(share);
                online = true;
                lastSync = System.currentTimeMillis();
                return r;
            }
        } catch (SyncError e) {
            online = false;
            throw e;
        } catch (SMBApiException e) {
            online = false;
            throw new SyncError(friendly(e.getStatus()));
        } catch (Exception e) {
            online = false;
            Throwable c = e;
            while (c != null) {
                if (c instanceof SMBApiException)
                    throw new SyncError(friendly(((SMBApiException) c).getStatus()));
                c = c.getCause();
            }
            if (e instanceof IOException || e.getCause() instanceof IOException)
                throw new SyncError("Can't reach the NAS. Check that Tailscale is connected.");
            throw new SyncError("NAS error: " + e.getMessage());
        }
    }

    private static String friendly(NtStatus s) {
        if (s == NtStatus.STATUS_LOGON_FAILURE) return "The NAS rejected the username or password.";
        if (s == NtStatus.STATUS_ACCESS_DENIED) return "The NAS user doesn't have permission to that folder.";
        if (s == NtStatus.STATUS_BAD_NETWORK_NAME) return "The share name on the NAS is wrong.";
        return "NAS error: " + s;
    }

    private static void copy(InputStream in, OutputStream out) throws IOException {
        byte[] buf = new byte[65536];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
    }

    private static void copyFile(File from, File to) throws IOException {
        try (InputStream in = new FileInputStream(from); OutputStream out = new FileOutputStream(to)) {
            copy(in, out);
        }
    }

    private void ensureFolder(DiskShare share) {
        String path = "";
        for (String p : pref("folder", "").split("/")) {
            if (p.trim().isEmpty()) continue;
            path = path.isEmpty() ? p : path + "\\" + p;
            if (!share.folderExists(path)) share.mkdir(path);
        }
    }

    private void upload(DiskShare share) throws IOException {
        String name = pref("file", "cdtracker.db");
        String path = smbPath(name), newPath = smbPath(name + ".new");
        try (com.hierynomus.smbj.share.File f = share.openFile(newPath,
                EnumSet.of(AccessMask.GENERIC_WRITE),
                EnumSet.of(FileAttributes.FILE_ATTRIBUTE_NORMAL),
                SMB2ShareAccess.ALL, SMB2CreateDisposition.FILE_OVERWRITE_IF,
                EnumSet.noneOf(SMB2CreateOptions.class));
             OutputStream out = f.getOutputStream();
             InputStream in = new FileInputStream(cache)) {
            copy(in, out);
        }
        try (com.hierynomus.smbj.share.File f = share.openFile(newPath,
                EnumSet.of(AccessMask.DELETE, AccessMask.GENERIC_READ),
                EnumSet.of(FileAttributes.FILE_ATTRIBUTE_NORMAL),
                SMB2ShareAccess.ALL, SMB2CreateDisposition.FILE_OPEN,
                EnumSet.noneOf(SMB2CreateOptions.class))) {
            f.rename(path, true);
        }
    }

    /** Download the NAS copy. Creates it on the NAS the first time. */
    synchronized void pull() throws SyncError {
        withShare(share -> {
            String path = smbPath(pref("file", "cdtracker.db"));
            if (!share.fileExists(path)) {
                ensureFolder(share);
                if (!cache.exists()) {
                    try (CashBook b = openLocal()) { /* creates empty file */ }
                }
                upload(share);
                return null;
            }
            try (com.hierynomus.smbj.share.File f = share.openFile(path,
                    EnumSet.of(AccessMask.GENERIC_READ),
                    EnumSet.of(FileAttributes.FILE_ATTRIBUTE_NORMAL),
                    SMB2ShareAccess.ALL, SMB2CreateDisposition.FILE_OPEN,
                    EnumSet.noneOf(SMB2CreateOptions.class));
                 InputStream in = f.getInputStream();
                 OutputStream out = new FileOutputStream(tmp)) {
                copy(in, out);
            }
            if (tmp.length() == 0) throw new SyncError("The data file on the NAS is empty.");
            if (!tmp.renameTo(cache)) {
                copyFile(tmp, cache);
                tmp.delete();
            }
            return null;
        });
    }

    synchronized void push() throws SyncError {
        withShare(share -> {
            upload(share);
            return null;
        });
    }

    /**
     * Get the latest from the NAS, apply op, upload it back. If anything
     * fails the local copy is put back as it was - nothing is half-saved.
     */
    synchronized <T> T write(Op<T> op) throws Exception {
        pull();
        copyFile(cache, before);
        try {
            T r;
            try (CashBook b = openLocal()) {
                r = op.run(b);
            }
            push();
            return r;
        } catch (Exception e) {
            copyFile(before, cache);
            throw e;
        }
    }
}
