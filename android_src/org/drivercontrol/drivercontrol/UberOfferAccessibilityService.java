package org.drivercontrol.drivercontrol;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.ColorSpace;
import android.hardware.HardwareBuffer;
import android.os.Build;
import android.os.SystemClock;
import android.provider.Settings;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Lector visual de ofertas de Uber.
 *
 * En Android 11+ evita recorrer árboles grandes de Accesibilidad: toma una captura
 * mediante AccessibilityService.takeScreenshot(), ejecuta OCR local con ML Kit y
 * envía solamente el texto reconocido al parser de Driver Control.
 *
 * No pulsa botones, no acepta ni rechaza viajes, no guarda capturas y no transmite
 * imágenes fuera del teléfono.
 */
public class UberOfferAccessibilityService extends AccessibilityService {
    private static final String[] UBER_PACKAGES = {"com.ubercab.driver", "com.ubercab"};

    // Ritmo conservador: suficiente para una tarjeta que permanece varios segundos,
    // sin castigar CPU/batería ni topar el rate-limit de takeScreenshot().
    private static final long SCREENSHOT_INTERVAL_MS = 1200L;
    private static final long STATUS_THROTTLE_MS = 2500L;
    private static final int MAX_OCR_WIDTH = 1080;

    // Fallback solamente para Android < 11.
    private static final int LEGACY_MAX_NODES = 180;
    private static final int LEGACY_MAX_DEPTH = 12;
    private static final int LEGACY_MAX_LINES = 90;

    private TextRecognizer recognizer;
    private boolean screenshotInFlight = false;
    private long lastScreenshotAt = 0L;
    private long lastStatusAt = 0L;
    private int lastPayloadHash = 0;

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();

        recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);

        AccessibilityServiceInfo info = getServiceInfo();
        if (info != null) {
            info.packageNames = UBER_PACKAGES;
            info.eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
                    | AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
                    | AccessibilityEvent.TYPE_VIEW_SCROLLED;
            info.feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC;
            info.notificationTimeout = 220;

            // En Android moderno no necesitamos recuperar ventanas interactivas ni
            // nodos "no importantes": eso era una de las fuentes de tirones.
            info.flags |= AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
            setServiceInfo(info);
        }

        startOverlayIfAllowed();

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            sendStatus("Lector visual activo · abrí Uber", false);
        } else {
            sendStatus("Lector activo · modo compatibilidad", false);
        }
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null) return;

        CharSequence pkg = event.getPackageName();
        if (pkg == null || !isUberPackage(pkg.toString())) return;

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            requestVisualRead();
        } else {
            readLegacyAccessibleText(event);
        }
    }

    /**
     * Android 11+: OCR sobre screenshot provisto por Accesibilidad.
     * Esto funciona aunque Uber dibuje la tarjeta sin exponer nodos de texto.
     */
    private void requestVisualRead() {
        long now = SystemClock.elapsedRealtime();
        if (screenshotInFlight || now - lastScreenshotAt < SCREENSHOT_INTERVAL_MS) return;

        screenshotInFlight = true;
        lastScreenshotAt = now;

        try {
            takeScreenshot(
                    Display.DEFAULT_DISPLAY,
                    getMainExecutor(),
                    new AccessibilityService.TakeScreenshotCallback() {
                        @Override
                        public void onSuccess(AccessibilityService.ScreenshotResult result) {
                            processScreenshot(result);
                        }

                        @Override
                        public void onFailure(int errorCode) {
                            screenshotInFlight = false;
                            sendStatus("Lectura visual: captura falló (" + errorCode + ")", true);
                        }
                    }
            );
        } catch (Throwable error) {
            screenshotInFlight = false;
            sendStatus("Lectura visual: no se pudo capturar", true);
        }
    }

    private void processScreenshot(AccessibilityService.ScreenshotResult result) {
        if (result == null) {
            screenshotInFlight = false;
            sendStatus("Lectura visual: captura vacía", true);
            return;
        }

        HardwareBuffer buffer = null;
        Bitmap hardwareBitmap = null;
        Bitmap bitmap = null;
        Bitmap ocrBitmap = null;

        try {
            buffer = result.getHardwareBuffer();
            if (buffer == null) {
                screenshotInFlight = false;
                sendStatus("Lectura visual: sin imagen", true);
                return;
            }

            ColorSpace colorSpace = result.getColorSpace();
            if (colorSpace == null) {
                colorSpace = ColorSpace.get(ColorSpace.Named.SRGB);
            }

            hardwareBitmap = Bitmap.wrapHardwareBuffer(buffer, colorSpace);
            if (hardwareBitmap == null) {
                screenshotInFlight = false;
                sendStatus("Lectura visual: formato no compatible", true);
                return;
            }

            // ML Kit trabaja de forma más predecible con un bitmap software ARGB_8888.
            bitmap = hardwareBitmap.copy(Bitmap.Config.ARGB_8888, false);
            if (bitmap == null) {
                screenshotInFlight = false;
                sendStatus("Lectura visual: no se pudo preparar imagen", true);
                return;
            }

            if (bitmap.getWidth() > MAX_OCR_WIDTH) {
                int targetHeight = Math.max(
                        1,
                        Math.round(bitmap.getHeight() * (MAX_OCR_WIDTH / (float) bitmap.getWidth()))
                );
                ocrBitmap = Bitmap.createScaledBitmap(bitmap, MAX_OCR_WIDTH, targetHeight, true);
            } else {
                ocrBitmap = bitmap;
            }

        } catch (Throwable error) {
            screenshotInFlight = false;
            sendStatus("Lectura visual: error preparando captura", true);
            recycle(bitmap);
            recycle(hardwareBitmap);
            close(buffer);
            return;
        } finally {
            // Ya copiamos la imagen fuera del HardwareBuffer.
            close(buffer);
            recycle(hardwareBitmap);
        }

        final Bitmap input = ocrBitmap;
        final Bitmap original = bitmap;

        if (recognizer == null || input == null) {
            screenshotInFlight = false;
            if (input != original) recycle(input);
            recycle(original);
            sendStatus("Lectura visual: OCR no disponible", true);
            return;
        }

        recognizer.process(InputImage.fromBitmap(input, 0))
                .addOnSuccessListener(resultText -> {
                    String raw = resultText == null ? "" : resultText.getText();
                    if (raw == null || raw.trim().isEmpty()) {
                        sendStatus("OCR · pantalla leída sin texto", true);
                        return;
                    }

                    String trimmed = raw.trim();
                    int hash = trimmed.hashCode();
                    if (hash == lastPayloadHash) return;
                    lastPayloadHash = hash;

                    sendText(trimmed);
                })
                .addOnFailureListener(error ->
                        sendStatus("OCR · no pudo reconocer este cuadro", true))
                .addOnCompleteListener(task -> {
                    if (input != original) recycle(input);
                    recycle(original);
                    screenshotInFlight = false;
                });
    }

    /**
     * Fallback para Android 10 o anterior. Mantiene límites estrictos para no trabar
     * el teléfono. En el dispositivo objetivo (Android 14) no se usa este camino.
     */
    private void readLegacyAccessibleText(AccessibilityEvent event) {
        AccessibilityNodeInfo source = event.getSource();
        if (source == null) {
            sendStatus("Uber detectado · sin texto accesible", true);
            return;
        }

        List<String> lines = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        Counter counter = new Counter();

        try {
            collectLegacy(source, lines, seen, counter, 0);
        } finally {
            recycleNode(source);
        }

        if (lines.isEmpty()) {
            sendStatus("Uber detectado · sin texto accesible", true);
            return;
        }

        StringBuilder out = new StringBuilder();
        for (String line : lines) {
            if (out.length() > 0) out.append('\n');
            out.append(line);
        }
        sendText(out.toString());
    }

    private void collectLegacy(
            AccessibilityNodeInfo node,
            List<String> out,
            Set<String> seen,
            Counter counter,
            int depth
    ) {
        if (node == null
                || depth > LEGACY_MAX_DEPTH
                || counter.nodes >= LEGACY_MAX_NODES
                || out.size() >= LEGACY_MAX_LINES) {
            return;
        }

        counter.nodes++;
        addLegacy(node.getText(), out, seen);
        addLegacy(node.getContentDescription(), out, seen);

        int childCount = Math.min(node.getChildCount(), 32);
        for (int i = 0; i < childCount; i++) {
            AccessibilityNodeInfo child = null;
            try {
                child = node.getChild(i);
                if (child != null) collectLegacy(child, out, seen, counter, depth + 1);
            } catch (Throwable ignored) {
            } finally {
                recycleNode(child);
            }
        }
    }

    private void addLegacy(CharSequence value, List<String> out, Set<String> seen) {
        if (value == null || out.size() >= LEGACY_MAX_LINES) return;
        String text = value.toString().trim().replaceAll("\\s+", " ");
        if (text.isEmpty() || text.length() > 240) return;
        if (seen.add(text)) out.add(text);
    }

    private void sendText(String raw) {
        try {
            Intent intent = new Intent(this, DriverOverlayService.class)
                    .setAction(DriverOverlayService.ACTION_SOURCE_TEXT)
                    .putExtra(DriverOverlayService.EXTRA_SOURCE_TEXT, raw)
                    .putExtra(DriverOverlayService.EXTRA_SOURCE_KIND, "OCR Uber");
            startOverlayService(intent);
        } catch (Throwable error) {
            sendStatus("OCR · error enviando lectura", true);
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
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent);
        } else {
            startService(intent);
        }
    }

    private boolean isUberPackage(String packageName) {
        if (packageName == null) return false;
        for (String allowed : UBER_PACKAGES) {
            if (allowed.equals(packageName) || packageName.startsWith(allowed + ".")) return true;
        }
        return false;
    }

    private static void recycle(Bitmap bitmap) {
        if (bitmap == null) return;
        try {
            if (!bitmap.isRecycled()) bitmap.recycle();
        } catch (Throwable ignored) {
        }
    }

    private static void close(HardwareBuffer buffer) {
        if (buffer == null) return;
        try {
            buffer.close();
        } catch (Throwable ignored) {
        }
    }

    private static void recycleNode(AccessibilityNodeInfo node) {
        if (node == null) return;
        try {
            node.recycle();
        } catch (Throwable ignored) {
        }
    }

    @Override
    public void onInterrupt() {
        sendStatus("Lector visual interrumpido", false);
    }

    @Override
    public void onDestroy() {
        if (recognizer != null) {
            try {
                recognizer.close();
            } catch (Throwable ignored) {
            }
            recognizer = null;
        }
        super.onDestroy();
    }

    private static final class Counter {
        int nodes = 0;
    }
}
