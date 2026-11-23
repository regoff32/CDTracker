package com.goffcomputer.cdtracker;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.MonthDay;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;

/** Money and date helpers - same rules as the Python version. */
final class Fmt {
    private Fmt() {}

    static long toCents(String text) {
        String s = text == null ? "" : text.trim().replace("$", "").replace(",", "");
        if (s.isEmpty()) throw new IllegalArgumentException("Enter an amount.");
        BigDecimal d;
        try {
            d = new BigDecimal(s);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("'" + text + "' is not a dollar amount.");
        }
        if (d.signum() <= 0) throw new IllegalArgumentException("Amount must be more than $0.");
        return d.movePointRight(2).setScale(0, RoundingMode.HALF_EVEN).longValueExact();
    }

    static String money(long cents) {
        return String.format(Locale.US, "$%,.2f", cents / 100.0);
    }

    private static final String[] PATTERNS = {
            "yyyy-MM-dd", "M/d/yyyy", "M/d/yy", "M-d-yyyy", "M-d-yy"};

    /** Returns an ISO date (yyyy-MM-dd). Empty means today. */
    static String parseDate(String text) {
        String s = text == null ? "" : text.trim();
        if (s.isEmpty()) return LocalDate.now().toString();
        for (String p : PATTERNS) {
            try {
                return LocalDate.parse(s, DateTimeFormatter.ofPattern(p, Locale.US)).toString();
            } catch (DateTimeParseException ignored) {
            }
        }
        try {
            return MonthDay.parse(s, DateTimeFormatter.ofPattern("M/d", Locale.US))
                    .atYear(LocalDate.now().getYear()).toString();
        } catch (DateTimeParseException e) {
            throw new IllegalArgumentException("'" + text + "' is not a date. Use MM/DD/YYYY.");
        }
    }

    static String showDate(String iso) {
        try {
            return LocalDate.parse(iso).format(DateTimeFormatter.ofPattern("MM/dd/yyyy", Locale.US));
        } catch (DateTimeParseException e) {
            return iso;
        }
    }
}
