package org.drivercontrol.drivercontrol;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Intent;
import android.os.Build;
import android.os.SystemClock;
import android.provider.Settings;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Fuente rápida de texto de Uber Driver.
 *
 * <p>Solo lee texto visible/accesible. No pulsa controles, no acepta ni rechaza viajes.
 * Está acotado por cantidad de nodos y frecuencia para evitar tirones.</p>
 */
public class UberOfferAccessibilityService extends AccessibilityService {
    private static final String[] UBER_PACKAGES = {"com.ubercab.driver", "com.ubercab"};
    private static final long MIN_REFRESH_MS = 500L;
    private static final long STATUS_THROTTLE_MS = 2500L;
    private static final int MAX_NODES = 360;
    private static final int MAX_DEPTH = 18;
    private static final int MAX_LINES = 140;

    private long lastRefresh = 0L;
    private long lastStatusAt = 0L;
    private int lastPayloadHash = 0;

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        AccessibilityServiceInfo info = getServiceInfo();
        if (info != null) {
            info.packageNames = UBER_PACKAGES;
            info.eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
                    | AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
                    | AccessibilityEvent.TYPE_VIEW_SCROLLED;
            info.feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC;
            info.notificationTimeout = 150;
            info.flags |= AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
                    | AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
                    | AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS;
            setServiceInfo(info);
        }
        startOverlayIfAllowed();
        sendStatus("Accesibilidad activa · abrí Uber", false);
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null) return;
        CharSequence packageName = event.getPackageName();
        if (packageName == null || !isUberPackage(packageName.toString())) return;

        long now = SystemClock.elapsedRealtime();
        if (now - lastRefresh < MIN_REFRESH_MS) return;
        lastRefresh = now;

        List<String> visible = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        CollectState state = new CollectState();

        AccessibilityNodeInfo source = event.getSource();
        if (source != null) {
            try {
                collectVisibleText(source, visible, seen, state, 0);
            } finally {
                recycleQuietly(source);
            }
        }

        AccessibilityNodeInfo activeRoot = getRootInActiveWindow();
        if (activeRoot != null) {
            try {
                CharSequence rootPackage = activeRoot.getPackageName();
                if (rootPackage == null || isUberPackage(rootPackage.toString())) {
                    collectVisibleText(activeRoot, visible, seen, state, 0);
                }
            } finally {
                recycleQuietly(activeRoot);
            }
        }

        try {
            List<AccessibilityWindowInfo> windows = getWindows();
            if (windows != null) {
                for (AccessibilityWindowInfo window : windows) {
                    if (window == null || state.nodes >= MAX_NODES || visible.size() >= MAX_LINES) continue;
                    AccessibilityNodeInfo root = window.getRoot();
                    if (root == null) continue;
                    try {
                        CharSequence rootPackage = root.getPackageName();
                        if (rootPackage != null && isUberPackage(rootPackage.toString())) {
                            collectVisibleText(root, visible, seen, state, 0);
                        }
                    } finally {
                        recycleQuietly(root);
                    }
                }
            }
        } catch (Throwable ignored) {
            // Algunos fabricantes pueden restringir getWindows(); source/root siguen disponibles.
        }

        if (visible.isEmpty()) {
            sendStatus("Uber detectado · sin texto accesible; usá OCR", true);
            return;
        }

        String raw = joinLines(visible);
        int hash = raw.hashCode();
        if (hash == lastPayloadHash) return;
        lastPayloadHash = hash;
        sendText(raw);
    }

    private boolean isUberPackage(String packageName) {
        if (packageName == null) return false;
        for (String allowed : UBER_PACKAGES) {
            if (allowed.equals(packageName) || packageName.startsWith(allowed + ".")) return true;
        }
        return false;
    }

    private void collectVisibleText(
            AccessibilityNodeInfo node,
            List<String> out,
            Set<String> seen,
            CollectState state,
            int depth
    ) {
        if (node == null || depth > MAX_DEPTH || state.nodes >= MAX_NODES || out.size() >= MAX_LINES) return;
        state.nodes++;

        addText(node.getText(), out, seen);
        addText(node.getContentDescription(), out, seen);
        if (Build.VERSION.SDK_INT >= 26) addText(node.getHintText(), out, seen);

        int childCount = Math.min(node.getChildCount(), 48);
        for (int i = 0; i < childCount && state.nodes < MAX_NODES && out.size() < MAX_LINES; i++) {
            AccessibilityNodeInfo child = null;
            try {
                child = node.getChild(i);
                if (child != null) collectVisibleText(child, out, seen, state, depth + 1);
            } catch (Throwable ignored) {
                // Un nodo inválido no debe cortar toda la lectura.
            } finally {
                recycleQuietly(child);
            }
        }
    }

    private void addText(CharSequence value, List<String> out, Set<String> seen) {
        if (value == null || out.size() >= MAX_LINES) return;
        String text = value.toString().trim().replaceAll("\\s+", " ");
        if (text.isEmpty() || text.length() > 240) return;
        if (seen.add(text)) out.add(text);
    }

    private String joinLines(List<String> lines) {
        StringBuilder raw = new StringBuilder();
        for (String line : lines) {
            if (raw.length() > 0) raw.append('\n');
            raw.append(line);
            if (raw.length() >= 7000) break;
        }
        return raw.toString();
    }

    private void sendText(String raw) {
        try {
            Intent intent = new Intent(this, DriverOverlayService.class)
                    .setAction(DriverOverlayService.ACTION_SOURCE_TEXT)
                    .putExtra(DriverOverlayService.EXTRA_SOURCE_TEXT, raw)
                    .putExtra(DriverOverlayService.EXTRA_SOURCE_KIND, "Accesibilidad");
            startOverlayService(intent);
        } catch (Throwable error) {
            sendStatus("Error enviando lectura de Accesibilidad", true);
        }
    }

    private void sendStatus(String message, boolean throttled) {
        long now = SystemClock.elapsedRealtime();
        if (throttled && now - lastStatusAt < STATUS_THROTTLE_MS) return;
        lastStatusAt = now;
        try {
            Intent intent = new Intent(this, DriverOverlayService.class)
                    .setAction(DriverOverlayService.ACTION_READER_STATUS)
                    .putExtra(DriverOverlayService.EXTRA_READER_STATUS, message);
            startOverlayService(intent);
        } catch (Throwable ignored) {
        }
    }

    private void startOverlayIfAllowed() {
        if (!Settings.canDrawOverlays(this)) return;
        try {
            Intent intent = new Intent(this, DriverOverlayService.class)
                    .setAction(DriverOverlayService.ACTION_START);
            startOverlayService(intent);
        } catch (Throwable ignored) {
        }
    }

    private void startOverlayService(Intent intent) {
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(intent);
        else startService(intent);
    }

    private static void recycleQuietly(AccessibilityNodeInfo node) {
        if (node == null) return;
        try {
            node.recycle();
        } catch (Throwable ignored) {
        }
    }

    @Override
    public void onInterrupt() {
        sendStatus("Accesibilidad interrumpida", false);
    }

    private static final class CollectState {
        int nodes = 0;
    }
}
