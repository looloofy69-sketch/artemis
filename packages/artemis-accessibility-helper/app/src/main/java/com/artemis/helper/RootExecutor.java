package com.artemis.helper;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Explicitly gated access to a root shell on devices that already provide su.
 *
 * This does not root a device or bypass Android's security model. On stock,
 * unrooted Android the capability remains unavailable. A person must test root
 * access and explicitly enable Root Mode in the app UI before authenticated
 * loopback callers can execute a command as root.
 */
public final class RootExecutor {
    private static final String PREFS = "artemis_runtime";
    private static final String KEY_ROOT_AVAILABLE = "root_available";
    private static final String KEY_ROOT_MODE = "root_mode_enabled";
    private static final int MAX_OUTPUT_BYTES = 32 * 1024;
    private static final int MAX_COMMAND_CHARS = 4096;

    private RootExecutor() {}

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static boolean wasRootAvailable(Context context) {
        return prefs(context).getBoolean(KEY_ROOT_AVAILABLE, false);
    }

    public static boolean isRootModeEnabled(Context context) {
        return prefs(context).getBoolean(KEY_ROOT_MODE, false);
    }

    public static void setRootModeEnabled(Context context, boolean enabled) {
        prefs(context).edit().putBoolean(KEY_ROOT_MODE, enabled).apply();
    }

    public static boolean probeRoot(Context context) {
        ExecResult result = runRaw("id -u", 15000L);
        boolean available = !result.timedOut && result.exitCode == 0
                && "0".equals(result.output.trim());
        prefs(context).edit().putBoolean(KEY_ROOT_AVAILABLE, available).apply();
        return available;
    }

    public static JSONObject capabilities(Context context, boolean accessibilityConnected)
            throws Exception {
        JSONObject json = new JSONObject();
        json.put("success", true);
        json.put("runtime", "artemis-android-runtime");
        json.put("runtime_version", "0.1.0");
        json.put("accessibility_connected", accessibilityConnected);
        json.put("screen_hierarchy", accessibilityConnected);
        json.put("gestures", accessibilityConnected);
        json.put("screen_capture", accessibilityConnected);
        json.put("root_available", wasRootAvailable(context));
        json.put("root_mode_enabled", isRootModeEnabled(context));
        json.put("root_access_note",
                "Root requires a rooted device and explicit approval. Stock Android is not bypassed.");
        return json;
    }

    public static ExecResult executeAuthorized(Context context, String command, long timeoutMs) {
        if (!isRootModeEnabled(context)) {
            return new ExecResult(-1, "", false, "Root Mode is disabled in the ARTEMIS Runtime app.");
        }
        if (!wasRootAvailable(context)) {
            return new ExecResult(-1, "", false,
                    "Root access has not been verified. Use Test root access in the app first.");
        }
        if (command == null || command.trim().isEmpty() || command.length() > MAX_COMMAND_CHARS
                || command.indexOf('\u0000') >= 0) {
            return new ExecResult(-1, "", false, "Command is empty or exceeds the 4096-character limit.");
        }
        long boundedTimeout = Math.max(250L, Math.min(timeoutMs, 10000L));
        ExecResult result = runRaw(command, boundedTimeout);
        if (!result.timedOut && result.exitCode != 0) {
            // A cached root grant can be revoked by the root manager at any time.
            String compact = result.output.trim();
            if (compact.toLowerCase().contains("permission denied")
                    || compact.toLowerCase().contains("not allowed")
                    || compact.toLowerCase().contains("denied")) {
                prefs(context).edit().putBoolean(KEY_ROOT_AVAILABLE, false).apply();
            }
        }
        return result;
    }

    private static ExecResult runRaw(String command, long timeoutMs) {
        Process process = null;
        final ByteArrayOutputStream captured = new ByteArrayOutputStream();
        final AtomicBoolean truncated = new AtomicBoolean(false);
        Thread reader = null;
        try {
            process = new ProcessBuilder("su", "-c", command)
                    .redirectErrorStream(true)
                    .start();
            final InputStream stream = process.getInputStream();
            reader = new Thread(() -> {
                byte[] buffer = new byte[2048];
                try {
                    int count;
                    while ((count = stream.read(buffer)) >= 0) {
                        synchronized (captured) {
                            int remaining = MAX_OUTPUT_BYTES - captured.size();
                            if (remaining > 0) {
                                captured.write(buffer, 0, Math.min(count, remaining));
                            }
                            if (count > remaining) truncated.set(true);
                        }
                    }
                } catch (Exception ignored) {
                    // Process termination at timeout closes the stream.
                }
            }, "ArtemisRootOutput");
            reader.setDaemon(true);
            reader.start();

            boolean finished = process.waitFor(timeoutMs, TimeUnit.MILLISECONDS);
            if (!finished) {
                process.destroyForcibly();
                process.waitFor(300, TimeUnit.MILLISECONDS);
            }
            if (reader != null) reader.join(500L);
            String output;
            synchronized (captured) {
                output = captured.toString(StandardCharsets.UTF_8.name());
            }
            if (truncated.get()) output += "\n[output truncated at 32 KiB]";
            return new ExecResult(finished ? process.exitValue() : -1, output, !finished,
                    finished ? "" : "Command timed out.");
        } catch (Exception e) {
            if (process != null) process.destroyForcibly();
            return new ExecResult(-1, "", false,
                    "Root execution failed: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    public static final class ExecResult {
        public final int exitCode;
        public final String output;
        public final boolean timedOut;
        public final String error;

        ExecResult(int exitCode, String output, boolean timedOut, String error) {
            this.exitCode = exitCode;
            this.output = output;
            this.timedOut = timedOut;
            this.error = error;
        }
    }
}
