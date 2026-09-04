package org.drivercontrol.drivercontrol;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Intent;
import android.os.Build;
import android.os.SystemClock;
import android.provider.Settings;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Fuente rápida y liviana de texto para Driver Control.
 * No dibuja ventanas ni hace clicks. El flotante vive en DriverOverlayService,
 * por lo que puede seguir funcionando con OCR aunque Accesibilidad se desactive.
 */
public class UberOfferAccessibilityService extends AccessibilityService {
    private static final String UBER_PACKAGE = "com.ubercab.driver";
    private static final long MIN_REFRESH_MS = 700L;
    private static final int MAX_NODES = 220;
    private static final int MAX_DEPTH = 14;
    private static final int MAX_LINES = 90;

    private long lastRefresh = 0L;

    @Override protected void onServiceConnected() {
        super.onServiceConnected();
        AccessibilityServiceInfo info = getServiceInfo();
        if (info != null) {
            info.packageNames = new String[]{UBER_PACKAGE};
            info.eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED |
                    AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED;
            info.feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC;
            info.notificationTimeout = 120;
            info.flags |= AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS |
                    AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS |
                    AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS;
            setServiceInfo(info);
        }
        startOverlayIfAllowed();
    }

    @Override public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null || event.getPackageName() == null) return;
        if (!UBER_PACKAGE.equals(event.getPackageName().toString())) return;
        long now = SystemClock.elapsedRealtime();
        if (now - lastRefresh < MIN_REFRESH_MS) return;
        lastRefresh = now;

        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return;
        try {
            List<String> visible = new ArrayList<>();
            CollectState state = new CollectState();
            collectVisibleText(root, visible, new HashSet<String>(), state, 0);
            if (!visible.isEmpty()) broadcastText(visible);
        } finally {
            try { root.recycle(); } catch (Exception ignored) {}
        }
    }

    private void collectVisibleText(AccessibilityNodeInfo node, List<String> out, Set<String> seen,
                                    CollectState state, int depth) {
        if (node == null || depth > MAX_DEPTH || state.nodes >= MAX_NODES || out.size() >= MAX_LINES) return;
        state.nodes++;
        if (node.isVisibleToUser()) {
            addText(node.getText(), out, seen);
            addText(node.getContentDescription(), out, seen);
        }
        int childCount = Math.min(node.getChildCount(), 40);
        for (int i = 0; i < childCount && state.nodes < MAX_NODES && out.size() < MAX_LINES; i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                try { collectVisibleText(child, out, seen, state, depth + 1); }
                finally { try { child.recycle(); } catch (Exception ignored) {} }
            }
        }
    }

    private void addText(CharSequence cs, List<String> out, Set<String> seen) {
        if (cs == null || out.size() >= MAX_LINES) return;
        String s = cs.toString().trim();
        if (s.isEmpty() || s.length() > 220) return;
        if (seen.add(s)) out.add(s);
    }

    private void broadcastText(List<String> lines) {
        StringBuilder raw = new StringBuilder();
        for (String line : lines) {
            if (raw.length() > 0) raw.append('\n');
            raw.append(line);
            if (raw.length() > 5000) break;
        }
        Intent intent = new Intent(DriverOverlayService.ACTION_SOURCE_TEXT)
                .setPackage(getPackageName())
                .putExtra(DriverOverlayService.EXTRA_SOURCE_TEXT, raw.toString())
                .putExtra(DriverOverlayService.EXTRA_SOURCE_KIND, "accessibility");
        sendBroadcast(intent);
    }

    private void startOverlayIfAllowed() {
        if (!Settings.canDrawOverlays(this)) return;
        try {
            Intent intent = new Intent(this, DriverOverlayService.class).setAction(DriverOverlayService.ACTION_START);
            if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent); else startService(intent);
        } catch (Exception ignored) {}
    }

    @Override public void onInterrupt() {}

    private static class CollectState { int nodes = 0; }
}
