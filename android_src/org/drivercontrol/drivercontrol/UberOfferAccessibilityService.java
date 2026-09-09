package org.drivercontrol.drivercontrol;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.SystemClock;
import android.provider.Settings;
import android.util.Base64;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.util.ArrayList;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

import org.json.JSONObject;

/**
 * Lector visual de ofertas de Uber.
 *
 * En Android 11+ evita recorrer árboles grandes de Accesibilidad: toma una captura
 * mediante AccessibilityService.takeScreenshot(), ejecuta OCR local con ML Kit y
 * envía el texto reconocido al parser local o, con consentimiento explícito,
 * una captura reducida al servidor de Gemini configurado por el usuario.
 *
 * No pulsa botones, no acepta ni rechaza viajes y no guarda capturas. En modo Gemini
 * transmite solo una imagen reducida, después del consentimiento del usuario.
 */
public class UberOfferAccessibilityService extends AccessibilityService {
    private static final String[] UBER_PACKAGES = {"com.ubercab.driver", "com.ubercab"};

    // Ritmo conservador: suficiente para una tarjeta que permanece varios segundos,
    // sin castigar CPU/batería ni topar el rate-limit de takeScreenshot().
    private static final long STATUS_THROTTLE_MS = 2500L;

    // Fallback solamente para Android < 11.
    private static final int LEGACY_MAX_NODES = 180;
    private static final int LEGACY_MAX_DEPTH = 12;
    private static final int LEGACY_MAX_LINES = 90;

    private DriverCopilotCoordinator coordinator;
    private long lastStatusAt = 0L;
    private long lastGeminiAt = 0L;
    private final ExecutorService networkExecutor = Executors.newSingleThreadExecutor();
    private final AtomicBoolean geminiInFlight = new AtomicBoolean(false);
    private static final long GEMINI_INTERVAL_MS = 7000L;

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();

        coordinator = new DriverCopilotCoordinator();

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
            sendStatus(isGeminiVisionEnabled()
                    ? "Gemini visual activo · preparando servidor…"
                    : "Lector visual local activo · abrí Uber", false);
        } else {
            sendStatus("Lector activo · modo compatibilidad", false);
        }
        if (isGeminiVisionEnabled()) warmGeminiServer();
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
        if (coordinator == null || !coordinator.tryBeginCapture()) return;

        try {
            takeScreenshot(
                    Display.DEFAULT_DISPLAY,
                    coordinator.callbackExecutor(),
                    new AccessibilityService.TakeScreenshotCallback() {
                        @Override
                        public void onSuccess(AccessibilityService.ScreenshotResult result) {
                            boolean geminiEnabled = isGeminiVisionEnabled();
                            coordinator.process(result, geminiEnabled, new DriverCopilotCoordinator.Callback() {
                                @Override
                                public void onResult(
                                        DriverCopilotCoordinator.ScreenType type,
                                        String text,
                                        double cashFare,
                                        float confidence,
                                        byte[] jpeg
                                ) {
                                    if (type == DriverCopilotCoordinator.ScreenType.OFFER) {
                                        if (geminiEnabled && jpeg != null) sendToGemini(jpeg, text);
                                        else sendText(text);
                                    } else if (type == DriverCopilotCoordinator.ScreenType.CASH_COLLECTION) {
                                        if (confidence >= 0.85f) sendCashFare(cashFare);
                                        else sendStatus("Confirmá el importe final", true);
                                    }
                                }

                                @Override
                                public void onError(String message) {
                                    sendStatus(message, true);
                                }
                            });
                        }

                        @Override
                        public void onFailure(int errorCode) {
                            coordinator.failCapture();
                            sendStatus("Lectura visual: captura falló (" + errorCode + ")", true);
                        }
                    }
            );
        } catch (Throwable error) {
            coordinator.failCapture();
            sendStatus("Lectura visual: no se pudo capturar", true);
        }
    }

    private boolean isGeminiVisionEnabled() {
        SharedPreferences prefs = getSharedPreferences("driver_control_overlay", MODE_PRIVATE);
        String url = prefs.getString("ai_server_url", "");
        String token = prefs.getString("ai_access_token", "");
        return prefs.getBoolean("gemini_visual_enabled", false)
                && url != null && url.startsWith("https://")
                && token != null && !token.trim().isEmpty();
    }

    private void warmGeminiServer() {
        SharedPreferences prefs = getSharedPreferences("driver_control_overlay", MODE_PRIVATE);
        String baseUrl = prefs.getString("ai_server_url", "");
        networkExecutor.execute(() -> {
            HttpURLConnection connection = null;
            try {
                URL endpoint = new URL(baseUrl.replaceAll("/+$", "") + "/health");
                connection = (HttpURLConnection) endpoint.openConnection();
                connection.setRequestMethod("GET");
                connection.setConnectTimeout(15000);
                connection.setReadTimeout(70000);
                if (connection.getResponseCode() == 200) sendStatus("Gemini visual listo · abrí Uber", false);
            } catch (Throwable error) {
                sendStatus("Servidor de Gemini iniciando · reintentará con la oferta", false);
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    private void sendToGemini(byte[] jpeg, String localText) {
        long now = SystemClock.elapsedRealtime();
        if (now - lastGeminiAt < GEMINI_INTERVAL_MS || !geminiInFlight.compareAndSet(false, true)) return;
        lastGeminiAt = now;
        sendStatus("Gemini · leyendo oferta…", false);

        SharedPreferences prefs = getSharedPreferences("driver_control_overlay", MODE_PRIVATE);
        String baseUrl = prefs.getString("ai_server_url", "");
        String token = prefs.getString("ai_access_token", "");
        networkExecutor.execute(() -> {
            HttpURLConnection connection = null;
            try {
                JSONObject body = new JSONObject();
                body.put("mime_type", "image/jpeg");
                body.put("image_base64", Base64.encodeToString(jpeg, Base64.NO_WRAP));
                body.put("local_text", localText == null ? "" : localText.substring(
                        0, Math.min(localText.length(), 2500)));

                URL endpoint = new URL(baseUrl.replaceAll("/+$", "") + "/v1/driver/vision");
                connection = (HttpURLConnection) endpoint.openConnection();
                connection.setRequestMethod("POST");
                connection.setConnectTimeout(15000);
                connection.setReadTimeout(70000);
                connection.setDoOutput(true);
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                connection.setRequestProperty("Authorization", "Bearer " + token);
                byte[] encoded = body.toString().getBytes(StandardCharsets.UTF_8);
                connection.setFixedLengthStreamingMode(encoded.length);
                try (OutputStream output = connection.getOutputStream()) {
                    output.write(encoded);
                }

                int status = connection.getResponseCode();
                InputStream stream = status >= 200 && status < 300
                        ? connection.getInputStream() : connection.getErrorStream();
                String response = readStream(stream);
                if (status < 200 || status >= 300) throw new IllegalStateException("HTTP " + status);
                JSONObject parsed = new JSONObject(response);
                if (!parsed.optBoolean("detected", false)) {
                    sendStatus("Gemini · no identificó una oferta", false);
                    sendText(localText);
                    return;
                }
                double fare = parsed.optDouble("fare", -1.0);
                double pickupMin = parsed.optDouble("pickup_min", -1.0);
                double pickupKm = parsed.optDouble("pickup_km", -1.0);
                double tripMin = parsed.optDouble("trip_min", -1.0);
                double tripKm = parsed.optDouble("trip_km", -1.0);
                if (fare <= 0.0 || pickupMin < 0.0 || pickupKm < 0.0
                        || tripMin <= 0.0 || tripKm <= 0.0) {
                    sendStatus("Gemini · lectura incompleta, uso lectura local", false);
                    sendText(localText);
                    return;
                }
                sendGeminiOffer(fare, pickupMin, pickupKm, tripMin, tripKm);
            } catch (Throwable error) {
                sendStatus("Gemini sin conexión · uso lectura local", false);
                sendText(localText);
            } finally {
                if (connection != null) connection.disconnect();
                geminiInFlight.set(false);
            }
        });
    }

    private static String readStream(InputStream stream) throws Exception {
        if (stream == null) return "";
        StringBuilder out = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null && out.length() < 32_000) out.append(line);
        }
        return out.toString();
    }

    private void sendGeminiOffer(
            double fare, double pickupMin, double pickupKm, double tripMin, double tripKm
    ) {
        try {
            Intent intent = new Intent(this, DriverOverlayService.class)
                    .setAction(DriverOverlayService.ACTION_GEMINI_OFFER)
                    .putExtra(DriverOverlayService.EXTRA_CASH_FARE, fare)
                    .putExtra(DriverOverlayService.EXTRA_PICKUP_MIN, pickupMin)
                    .putExtra(DriverOverlayService.EXTRA_PICKUP_KM, pickupKm)
                    .putExtra(DriverOverlayService.EXTRA_TRIP_MIN, tripMin)
                    .putExtra(DriverOverlayService.EXTRA_TRIP_KM, tripKm);
            startOverlayService(intent);
        } catch (Throwable error) {
            sendStatus("Gemini · no se pudo mostrar la oferta", false);
        }
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

    private void sendCashFare(double fare) {
        if (fare <= 0.0) return;
        try {
            Intent intent = new Intent(this, DriverOverlayService.class)
                    .setAction(DriverOverlayService.ACTION_CASH_FARE)
                    .putExtra(DriverOverlayService.EXTRA_CASH_FARE, fare);
            startOverlayService(intent);
        } catch (Throwable error) {
            sendStatus("OCR · error enviando importe final", true);
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
        if (coordinator != null) coordinator.close();
        coordinator = null;
        networkExecutor.shutdownNow();
        super.onDestroy();
    }

    private static final class Counter {
        int nodes = 0;
    }
}
