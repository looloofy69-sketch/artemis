package com.artemis.helper;

import android.content.Context;
import android.content.SharedPreferences;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;

/**
 * Runtime pairing token. The phone creates and stores its own token so a local
 * controller can pair without ADB. An ADB-authorized host can still override
 * the in-memory session token through TokenReceiver for the existing USB flow.
 */
public final class TokenStore {
    private static final String PREFS = "artemis_runtime";
    private static final String KEY_TOKEN = "runtime_token";
    private static volatile String token;

    private TokenStore() {}

    public static synchronized String initialize(Context context) {
        if (token != null) return token;
        SharedPreferences prefs = context.getApplicationContext()
                .getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        String stored = prefs.getString(KEY_TOKEN, null);
        if (stored == null || stored.length() < 48) {
            stored = generateToken();
            prefs.edit().putString(KEY_TOKEN, stored).apply();
        }
        token = stored;
        return stored;
    }

    public static synchronized String rotate(Context context) {
        String fresh = generateToken();
        context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit().putString(KEY_TOKEN, fresh).apply();
        token = fresh;
        return fresh;
    }

    private static String generateToken() {
        byte[] bytes = new byte[32];
        new SecureRandom().nextBytes(bytes);
        StringBuilder out = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) out.append(String.format(java.util.Locale.ROOT, "%02x", b & 0xff));
        return out.toString();
    }

    /** Used by the existing ADB-gated token receiver to create a process-only session token. */
    public static void set(String value) {
        token = (value == null || value.isEmpty()) ? null : value;
    }

    public static boolean isSet() {
        return token != null;
    }

    /** Constant-time comparison so a local app cannot guess the token byte by byte. */
    public static boolean matches(String candidate) {
        String current = token;
        if (current == null || candidate == null) return false;
        return MessageDigest.isEqual(
                current.getBytes(StandardCharsets.UTF_8),
                candidate.getBytes(StandardCharsets.UTF_8));
    }
}
