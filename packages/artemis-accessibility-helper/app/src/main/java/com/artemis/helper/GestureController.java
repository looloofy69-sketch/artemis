package com.artemis.helper;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.graphics.Path;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.accessibility.AccessibilityNodeInfo;

import java.util.List;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Synchronous gesture and action executor using native AccessibilityService APIs.
 * Works without requiring UiAutomation or root privileges.
 */
public final class GestureController {

    private static final String TAG = "ArtemisGestureCtrl";
    private static final Handler MAIN_HANDLER = new Handler(Looper.getMainLooper());

    private GestureController() {}

    public static boolean tap(AccessibilityService service, float x, float y, long timeoutMs) {
        Path path = new Path();
        path.moveTo(x, y);
        GestureDescription.StrokeDescription stroke = new GestureDescription.StrokeDescription(path, 0L, 60L);
        GestureDescription gesture = new GestureDescription.Builder().addStroke(stroke).build();
        return dispatchSynchronous(service, gesture, timeoutMs);
    }

    public static boolean doubleTap(AccessibilityService service, float x, float y, long timeoutMs) {
        if (!tap(service, x, y, timeoutMs)) return false;
        try {
            Thread.sleep(100L);
        } catch (InterruptedException ignored) {}
        return tap(service, x, y, timeoutMs);
    }

    public static boolean longPress(AccessibilityService service, float x, float y, long durationMs, long timeoutMs) {
        Path path = new Path();
        path.moveTo(x, y);
        long pressDur = Math.max(500L, Math.min(durationMs, 5000L));
        GestureDescription.StrokeDescription stroke = new GestureDescription.StrokeDescription(path, 0L, pressDur);
        GestureDescription gesture = new GestureDescription.Builder().addStroke(stroke).build();
        return dispatchSynchronous(service, gesture, timeoutMs + pressDur);
    }

    public static boolean swipe(
            AccessibilityService service,
            float x1, float y1, float x2, float y2,
            long durationMs, long timeoutMs
    ) {
        Path path = new Path();
        path.moveTo(x1, y1);
        path.lineTo(x2, y2);
        long safeDuration = Math.max(50L, Math.min(durationMs, 5000L));
        GestureDescription.StrokeDescription stroke = new GestureDescription.StrokeDescription(path, 0L, safeDuration);
        GestureDescription gesture = new GestureDescription.Builder().addStroke(stroke).build();
        return dispatchSynchronous(service, gesture, timeoutMs + safeDuration);
    }

    public static boolean setText(AccessibilityService service, String text) {
        return setText(service, text, false);
    }

    /**
     * Sets (or, with {@code append}, extends) the text of the focused / first editable field.
     * ACTION_SET_TEXT replaces the whole content; appending mirrors what typing through an
     * IME does, which is the contract the host's send_text has always had.
     */
    public static boolean setText(AccessibilityService service, String text, boolean append) {
        AccessibilityNodeInfo inputNode = HierarchyDumper.findInputNode(service);
        if (inputNode == null) {
            Log.w(TAG, "No editable/focused input node found for setText");
            return false;
        }
        try {
            String value = text == null ? "" : text;
            if (append) {
                CharSequence existing = inputNode.getText();
                boolean showingHint = false;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    try {
                        showingHint = inputNode.isShowingHintText();
                    } catch (Throwable ignored) {}
                }
                if (existing != null && existing.length() > 0 && !showingHint) {
                    value = existing.toString() + value;
                }
            }
            Bundle args = new Bundle();
            args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, value);
            return inputNode.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
        } catch (Throwable t) {
            Log.w(TAG, "performAction ACTION_SET_TEXT failed", t);
            return false;
        } finally {
            HierarchyDumper.safeRecycle(inputNode);
        }
    }

    public static boolean clearText(AccessibilityService service) {
        return setText(service, "");
    }

    public static boolean performGlobalAction(AccessibilityService service, String actionName) {
        if (actionName == null) return false;
        int actionId;
        String lower = actionName.toLowerCase();
        switch (lower) {
            case "back":
                actionId = AccessibilityService.GLOBAL_ACTION_BACK;
                break;
            case "home":
                actionId = AccessibilityService.GLOBAL_ACTION_HOME;
                break;
            case "recents":
                actionId = AccessibilityService.GLOBAL_ACTION_RECENTS;
                break;
            case "notifications":
                actionId = AccessibilityService.GLOBAL_ACTION_NOTIFICATIONS;
                break;
            case "quick_settings":
                actionId = AccessibilityService.GLOBAL_ACTION_QUICK_SETTINGS;
                break;
            case "power_dialog":
                actionId = AccessibilityService.GLOBAL_ACTION_POWER_DIALOG;
                break;
            case "toggle_split_screen":
                actionId = AccessibilityService.GLOBAL_ACTION_TOGGLE_SPLIT_SCREEN;
                break;
            case "lock_screen":
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    actionId = AccessibilityService.GLOBAL_ACTION_LOCK_SCREEN;
                } else {
                    return false;
                }
                break;
            case "take_screenshot":
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    actionId = AccessibilityService.GLOBAL_ACTION_TAKE_SCREENSHOT;
                } else {
                    return false;
                }
                break;
            default:
                return false;
        }
        return service.performGlobalAction(actionId);
    }

    private static boolean dispatchSynchronous(
            final AccessibilityService service,
            final GestureDescription gesture,
            long timeoutMs
    ) {
        final CountDownLatch latch = new CountDownLatch(1);
        final AtomicBoolean result = new AtomicBoolean(false);

        MAIN_HANDLER.post(new Runnable() {
            @Override
            public void run() {
                try {
                    service.dispatchGesture(gesture, new AccessibilityService.GestureResultCallback() {
                        @Override
                        public void onCompleted(GestureDescription gestureDescription) {
                            result.set(true);
                            latch.countDown();
                        }

                        @Override
                        public void onCancelled(GestureDescription gestureDescription) {
                            result.set(false);
                            latch.countDown();
                        }
                    }, null);
                } catch (Throwable t) {
                    Log.w(TAG, "dispatchGesture threw exception", t);
                    result.set(false);
                    latch.countDown();
                }
            }
        });

        try {
            return latch.await(timeoutMs, TimeUnit.MILLISECONDS) && result.get();
        } catch (InterruptedException e) {
            return false;
        }
    }

    /**
     * Write text to the system clipboard. Clipboard writes are allowed from any
     * app on every API level (only reads are restricted since Android 10), so this
     * is the IME-free path the host uses for multiline and non-ASCII input:
     * set the clip here, then KEYCODE_PASTE over adb.
     */
    /**
     * Removes the final Unicode code point from the focused, non-password editable field.
     * Refuses unfocused/password fields rather than reading or rewriting sensitive content.
     */
    /**
     * Triggers the IME's configured editor action (for example Search, Send or Done).
     * This is supported on Android 11+ and is refused for password or non-editable fields.
     */
    /**
     * Clicks the first accessible node matching text. Exact matching is case-insensitive.
     * If the text node is not clickable, up to six ancestors are checked for a clickable
     * container. The caller remains responsible for choosing an unambiguous selector.
     */
    public static boolean clickByText(AccessibilityService service, String text, boolean exact) {
        String selector = text == null ? "" : text.trim();
        if (service == null || selector.isEmpty() || selector.length() > 256) return false;
        AccessibilityNodeInfo root = null;
        List<AccessibilityNodeInfo> matches = null;
        try {
            root = service.getRootInActiveWindow();
            if (root == null) return false;
            matches = root.findAccessibilityNodeInfosByText(selector);
            if (matches == null) return false;
            for (AccessibilityNodeInfo node : matches) {
                if (node == null || !node.isVisibleToUser() || !node.isEnabled()) continue;
                if (exact) {
                    CharSequence label = node.getText();
                    if (label == null || !selector.equalsIgnoreCase(label.toString().trim())) continue;
                }
                if (clickNodeOrClickableAncestor(node)) return true;
            }
        } catch (Throwable t) {
            Log.w(TAG, "clickByText failed", t);
        } finally {
            if (matches != null) {
                for (AccessibilityNodeInfo node : matches) {
                    HierarchyDumper.safeRecycle(node);
                }
            }
            HierarchyDumper.safeRecycle(root);
        }
        return false;
    }

    /**
     * Clicks an accessible node identified by a fully-qualified Android view ID,
     * for example com.example:id/submit_button.
     */
    public static boolean clickByViewId(AccessibilityService service, String viewId) {
        String selector = viewId == null ? "" : viewId.trim();
        if (service == null || selector.length() > 256 || !selector.contains(":id/")) return false;
        AccessibilityNodeInfo root = null;
        List<AccessibilityNodeInfo> matches = null;
        try {
            root = service.getRootInActiveWindow();
            if (root == null) return false;
            matches = root.findAccessibilityNodeInfosByViewId(selector);
            if (matches == null) return false;
            for (AccessibilityNodeInfo node : matches) {
                if (node == null || !node.isVisibleToUser() || !node.isEnabled()) continue;
                if (clickNodeOrClickableAncestor(node)) return true;
            }
        } catch (Throwable t) {
            Log.w(TAG, "clickByViewId failed", t);
        } finally {
            if (matches != null) {
                for (AccessibilityNodeInfo node : matches) {
                    HierarchyDumper.safeRecycle(node);
                }
            }
            HierarchyDumper.safeRecycle(root);
        }
        return false;
    }

    private static boolean clickNodeOrClickableAncestor(AccessibilityNodeInfo node) {
        AccessibilityNodeInfo current = node;
        boolean recycleCurrent = false;
        for (int depth = 0; current != null && depth <= 6; depth++) {
            try {
                if (current.isVisibleToUser() && current.isEnabled() && current.isClickable()
                        && current.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
                    if (recycleCurrent) HierarchyDumper.safeRecycle(current);
                    return true;
                }
                AccessibilityNodeInfo parent = current.getParent();
                if (recycleCurrent) HierarchyDumper.safeRecycle(current);
                current = parent;
                recycleCurrent = true;
            } catch (Throwable t) {
                Log.w(TAG, "clickNodeOrClickableAncestor failed", t);
                break;
            }
        }
        if (recycleCurrent) HierarchyDumper.safeRecycle(current);
        return false;
    }

    public static boolean pressImeEnter(AccessibilityService service) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return false;
        AccessibilityNodeInfo inputNode = HierarchyDumper.findInputNode(service);
        if (inputNode == null) return false;
        try {
            if (!inputNode.isFocused() || !inputNode.isEditable()
                    || inputNode.isPassword() || !inputNode.isEnabled()) {
                return false;
            }
            return inputNode.performAction(
                    AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.getId());
        } catch (Throwable t) {
            Log.w(TAG, "pressImeEnter failed", t);
            return false;
        } finally {
            HierarchyDumper.safeRecycle(inputNode);
        }
    }

    public static boolean eraseOneChar(AccessibilityService service) {
        AccessibilityNodeInfo inputNode = HierarchyDumper.findInputNode(service);
        if (inputNode == null) return false;
        try {
            if (!inputNode.isFocused() || inputNode.isPassword() || !inputNode.isEnabled()) {
                return false;
            }
            CharSequence existing = inputNode.getText();
            if (existing == null || existing.length() == 0) return true;
            String value = existing.toString();
            int end = value.offsetByCodePoints(value.length(), -1);
            Bundle args = new Bundle();
            args.putCharSequence(
                    AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                    value.substring(0, end));
            return inputNode.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args);
        } catch (Throwable t) {
            Log.w(TAG, "eraseOneChar failed", t);
            return false;
        } finally {
            HierarchyDumper.safeRecycle(inputNode);
        }
    }

    public static boolean setClipboard(final AccessibilityService service, final String text) {
        final CountDownLatch latch = new CountDownLatch(1);
        final AtomicBoolean ok = new AtomicBoolean(false);
        MAIN_HANDLER.post(new Runnable() {
            @Override
            public void run() {
                try {
                    ClipboardManager cm = (ClipboardManager) service.getSystemService(Context.CLIPBOARD_SERVICE);
                    if (cm != null) {
                        cm.setPrimaryClip(ClipData.newPlainText("artemis", text == null ? "" : text));
                        ok.set(true);
                    }
                } catch (Throwable t) {
                    Log.w(TAG, "setClipboard failed: " + t.getMessage());
                } finally {
                    latch.countDown();
                }
            }
        });
        try {
            latch.await(2000, TimeUnit.MILLISECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        return ok.get();
    }
}
