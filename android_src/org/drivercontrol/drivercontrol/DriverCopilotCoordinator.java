package org.drivercontrol.drivercontrol;

import android.accessibilityservice.AccessibilityService;
import android.graphics.Bitmap;
import android.graphics.ColorSpace;
import android.hardware.HardwareBuffer;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;

import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Executor;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Única autoridad para capturar y procesar la pantalla de Uber.
 *
 * Convierte la captura a bitmap y ejecuta ML Kit fuera del hilo principal. Nunca
 * persiste imágenes. Clasifica el resultado antes de entregarlo al overlay y evita
 * procesar dos cuadros o dos lectores al mismo tiempo.
 */
public final class DriverCopilotCoordinator {
    public enum ScreenType { OFFER, CASH_COLLECTION, IRRELEVANT }

    public interface Callback {
        void onResult(ScreenType type, String text, double cashFare, float confidence);
        void onError(String message);
    }

    private static final long MIN_CAPTURE_INTERVAL_MS = 1200L;
    private static final int MAX_OCR_WIDTH = 1080;
    private static final Pattern MONEY = Pattern.compile(
            "(?i)(?:ARS\\s*|AR\\s*\\$\\s*|\\$\\s*)([0-9OIl|][0-9OIl|.,\\s]*)");
    private static final Pattern MINUTES = Pattern.compile(
            "(?i)[0-9OIl|]+(?:[.,][0-9OIl|]+)?\\s*(?:min\\.?|minuto(?:s)?)\\b");
    private static final Pattern KM = Pattern.compile(
            "(?i)[0-9OIl|]+(?:[.,][0-9OIl|]+)?\\s*(?:km|kil[oó]metro(?:s)?)\\b");

    private final HandlerThread workerThread = new HandlerThread("DriverCopilotVision");
    private final Handler worker;
    private final Executor workerExecutor;
    private final TextRecognizer recognizer;
    private boolean inFlight;
    private long lastCaptureAt;
    private int lastPayloadHash;

    public DriverCopilotCoordinator() {
        workerThread.start();
        worker = new Handler(workerThread.getLooper());
        workerExecutor = command -> worker.post(command);
        recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
    }

    public synchronized boolean tryBeginCapture() {
        long now = SystemClock.elapsedRealtime();
        if (inFlight || now - lastCaptureAt < MIN_CAPTURE_INTERVAL_MS) return false;
        inFlight = true;
        lastCaptureAt = now;
        return true;
    }

    public Executor callbackExecutor() {
        return workerExecutor;
    }

    public void process(AccessibilityService.ScreenshotResult result, Callback callback) {
        worker.post(() -> processOnWorker(result, callback));
    }

    public synchronized void failCapture() {
        inFlight = false;
    }

    private void processOnWorker(AccessibilityService.ScreenshotResult result, Callback callback) {
        HardwareBuffer buffer = null;
        Bitmap hardware = null;
        Bitmap software = null;
        Bitmap scaled = null;
        try {
            if (result == null) throw new IllegalStateException("captura vacía");
            buffer = result.getHardwareBuffer();
            if (buffer == null) throw new IllegalStateException("imagen vacía");
            ColorSpace color = result.getColorSpace();
            if (color == null) color = ColorSpace.get(ColorSpace.Named.SRGB);
            hardware = Bitmap.wrapHardwareBuffer(buffer, color);
            if (hardware == null) throw new IllegalStateException("formato no compatible");
            software = hardware.copy(Bitmap.Config.ARGB_8888, false);
            if (software == null) throw new IllegalStateException("copia no disponible");

            // Se descarta la barra superior; oferta y cobro aparecen debajo de ella.
            int top = Math.max(0, Math.round(software.getHeight() * 0.07f));
            Bitmap crop = Bitmap.createBitmap(
                    software, 0, top, software.getWidth(), software.getHeight() - top);
            if (crop.getWidth() > MAX_OCR_WIDTH) {
                int height = Math.max(1,
                        Math.round(crop.getHeight() * (MAX_OCR_WIDTH / (float) crop.getWidth())));
                scaled = Bitmap.createScaledBitmap(crop, MAX_OCR_WIDTH, height, true);
                recycle(crop);
            } else {
                scaled = crop;
            }
        } catch (Throwable error) {
            recycle(scaled);
            recycle(software);
            recycle(hardware);
            close(buffer);
            failCapture();
            callback.onError("Lectura visual: " + error.getMessage());
            return;
        } finally {
            recycle(hardware);
            close(buffer);
        }

        final Bitmap input = scaled;
        final Bitmap original = software;
        recognizer.process(InputImage.fromBitmap(input, 0))
                .addOnSuccessListener(workerExecutor, resultText -> {
                    String text = resultText == null ? "" : resultText.getText().trim();
                    if (text.isEmpty()) {
                        callback.onError("OCR · pantalla sin texto útil");
                        return;
                    }
                    int hash = text.hashCode();
                    synchronized (this) {
                        if (hash == lastPayloadHash) return;
                        lastPayloadHash = hash;
                    }
                    VisionDecision decision = classify(text);
                    callback.onResult(decision.type, text, decision.cashFare, decision.confidence);
                })
                .addOnFailureListener(workerExecutor,
                        error -> callback.onError("OCR · no pudo reconocer este cuadro"))
                .addOnCompleteListener(workerExecutor, task -> {
                    recycle(input);
                    if (original != input) recycle(original);
                    failCapture();
                });
    }

    private VisionDecision classify(String text) {
        String lower = text.toLowerCase(Locale.ROOT);
        boolean hasMinutes = MINUTES.matcher(text).find();
        boolean hasKm = KM.matcher(text).find();
        boolean offerHint = lower.contains("aceptar") || lower.contains("viaje")
                || lower.contains("uberx") || lower.contains("priority")
                || lower.contains("para llegar") || lower.contains("recoger");
        if (hasMinutes && hasKm && (offerHint || MONEY.matcher(text).find())) {
            return new VisionDecision(ScreenType.OFFER, -1.0, offerHint ? 0.94f : 0.82f);
        }

        boolean cashHint = lower.contains("cobrar") || lower.contains("cobro")
                || lower.contains("efectivo") || lower.contains("total a cobrar")
                || lower.contains("importe") || lower.contains("paga");
        if (!hasMinutes && !hasKm) {
            List<Double> amounts = extractAmounts(text);
            if (!amounts.isEmpty() && (cashHint || amounts.size() == 1)) {
                double best = amounts.get(0);
                if (cashHint) for (double value : amounts) best = Math.max(best, value);
                return new VisionDecision(
                        ScreenType.CASH_COLLECTION, best, cashHint ? 0.96f : 0.78f);
            }
        }
        return new VisionDecision(ScreenType.IRRELEVANT, -1.0, 0.0f);
    }

    private List<Double> extractAmounts(String text) {
        List<Double> out = new ArrayList<>();
        Matcher matcher = MONEY.matcher(text);
        while (matcher.find() && out.size() < 6) {
            double value = parseLocaleNumber(matcher.group(1));
            if (value < 100.0 || value > 2_000_000.0) continue;
            boolean duplicate = false;
            for (double existing : out) if (Math.abs(existing - value) < 0.5) duplicate = true;
            if (!duplicate) out.add(value);
        }
        return out;
    }

    private static double parseLocaleNumber(String raw) {
        if (raw == null) return -1.0;
        String value = raw.trim().replace(" ", "")
                .replace('I', '1').replace('i', '1').replace('l', '1')
                .replace('|', '1').replace('O', '0').replace('o', '0');
        try {
            int comma = value.lastIndexOf(',');
            int dot = value.lastIndexOf('.');
            if (comma >= 0 && dot >= 0) {
                value = comma > dot ? value.replace(".", "").replace(',', '.')
                        : value.replace(",", "");
            } else if (comma >= 0) {
                value = value.length() - comma - 1 <= 2
                        ? value.replace(',', '.') : value.replace(",", "");
            } else if (dot >= 0 && value.length() - dot - 1 == 3 && value.length() > 4) {
                value = value.replace(".", "");
            }
            return Double.parseDouble(value);
        } catch (Exception ignored) {
            return -1.0;
        }
    }

    public void close() {
        try { recognizer.close(); } catch (Throwable ignored) {}
        workerThread.quitSafely();
    }

    private static void recycle(Bitmap bitmap) {
        if (bitmap == null) return;
        try { if (!bitmap.isRecycled()) bitmap.recycle(); } catch (Throwable ignored) {}
    }

    private static void close(HardwareBuffer buffer) {
        if (buffer == null) return;
        try { buffer.close(); } catch (Throwable ignored) {}
    }

    private static final class VisionDecision {
        final ScreenType type;
        final double cashFare;
        final float confidence;

        VisionDecision(ScreenType type, double cashFare, float confidence) {
            this.type = type;
            this.cashFare = cashFare;
            this.confidence = confidence;
        }
    }
}
