package com.artemis.helper;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.view.accessibility.AccessibilityManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.List;

/**
 * On-device control panel for ARTEMIS Runtime.
 *
 * Stock Android receives only capabilities granted through Android's own
 * accessibility settings. Root Mode is a separate, off-by-default capability
 * and is available only where a root manager already grants su access.
 */
public class MainActivity extends Activity {
    private TextView status;
    private TextView tokenText;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        TokenStore.initialize(this);
        buildUi();
        refreshStatus();
    }

    private void buildUi() {
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(20);
        root.setPadding(pad, pad, pad, pad);
        scroll.addView(root);

        TextView title = text("ARTEMIS Runtime", 26f, true);
        root.addView(title);
        root.addView(text(
                "First-party Android runtime for screen understanding and device actions. "
                + "This app does not bypass Android permissions.", 15f, false));
        root.addView(gap(12));

        status = text("", 15f, false);
        root.addView(status);

        root.addView(button("Open Accessibility settings", v ->
                startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))));
        root.addView(button("Refresh runtime status", v -> refreshStatus()));

        root.addView(gap(10));
        root.addView(text("Local pairing token", 18f, true));
        root.addView(text(
                "The token authorizes a local controller to read the screen and execute UI actions. "
                + "Keep it private. It is stored only in this app's private preferences.", 14f, false));
        tokenText = text("", 13f, false);
        tokenText.setTextIsSelectable(true);
        root.addView(tokenText);
        root.addView(button("Copy token", v -> copyToken()));
        root.addView(button("Rotate token (revoke old controller token)", v -> confirmRotateToken()));

        root.addView(gap(10));
        root.addView(text("Standard runtime security boundary", 18f, true));
        root.addView(text(
                "This build does not contain root-shell execution. It uses Android's user-granted "
                + "AccessibilityService capabilities only. Device-wide or privileged operations "
                + "remain controlled by Android and are not enabled by this app.", 14f, false));

        root.addView(gap(12));
        root.addView(text(
                "Network boundary: the command server listens on 127.0.0.1 only. "
                + "Screen content and commands are not sent to a remote service by this app; "
                + "ARTEMIS model calls may use the provider you configure separately.", 13f, false));

        setContentView(scroll);
    }

    private void refreshStatus() {
        boolean enabled = isAccessibilityEnabled();
        boolean connected = ArtemisAccessibilityService.getInstance() != null;
        status.setText("Accessibility service: " + (enabled ? "enabled" : "not enabled")
                + "\nRuntime server: " + (connected ? "running" : "not connected")
                + "\nLocal API: 127.0.0.1:" + ArtemisAccessibilityService.DEFAULT_PORT
                + "\nScreen hierarchy, gestures and screenshot: "
                + (connected ? "available while service is connected" : "waiting for service"));
        tokenText.setText(TokenStore.initialize(this));
    }

    private boolean isAccessibilityEnabled() {
        AccessibilityManager manager = (AccessibilityManager)
                getSystemService(Context.ACCESSIBILITY_SERVICE);
        if (manager == null) return false;
        List<AccessibilityServiceInfo> list =
                manager.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK);
        String expected = new ComponentName(this, ArtemisAccessibilityService.class).getClassName();
        for (AccessibilityServiceInfo info : list) {
            if (info.getResolveInfo() != null && info.getResolveInfo().serviceInfo != null
                    && getPackageName().equals(info.getResolveInfo().serviceInfo.packageName)
                    && expected.equals(info.getResolveInfo().serviceInfo.name)) {
                return true;
            }
        }
        return false;
    }

    private void copyToken() {
        String token = TokenStore.initialize(this);
        ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (clipboard != null) {
            clipboard.setPrimaryClip(ClipData.newPlainText("ARTEMIS Runtime token", token));
            Toast.makeText(this, "Runtime token copied. Keep it private.", Toast.LENGTH_LONG).show();
        }
    }

    private void confirmRotateToken() {
        new AlertDialog.Builder(this)
                .setTitle("Rotate runtime token?")
                .setMessage("Existing controllers using the current token will immediately lose access.")
                .setNegativeButton("Cancel", null)
                .setPositiveButton("Rotate token", (dialog, which) -> {
                    String token = TokenStore.rotate(this);
                    tokenText.setText(token);
                    Toast.makeText(this, "Token rotated.", Toast.LENGTH_SHORT).show();
                })
                .show();
    }

    private Button button(String label, View.OnClickListener listener) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setOnClickListener(listener);
        return b;
    }

    private TextView text(String value, float size, boolean bold) {
        TextView t = new TextView(this);
        t.setText(value);
        t.setTextSize(size);
        t.setPadding(0, dp(6), 0, dp(6));
        if (bold) t.setTypeface(null, android.graphics.Typeface.BOLD);
        return t;
    }

    private View gap(int heightDp) {
        View v = new View(this);
        v.setLayoutParams(new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(heightDp)));
        return v;
    }

    private int dp(int value) {
        return (int) (value * getResources().getDisplayMetrics().density + 0.5f);
    }
}
