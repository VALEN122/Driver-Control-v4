package org.drivercontrol.drivercontrol;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.SystemClock;
import android.provider.Settings;
import android.util.DisplayMetrics;

import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;

import java.text.NumberFormat;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Captura autorizada + OCR local con ML Kit.
 * No persiste ni transmite capturas. Solo envía el texto reconocido al parser local.
 *
 * También reconoce la pantalla de cobro simple (por ejemplo AR$5.600) y deja
 * ese importe precargado para la calculadora flotante de vuelto.
 */
public class OcrCaptureService extends Service {
    public static final String ACTION_START = "org.drivercontrol.drivercontrol.OCR_START";
    public static final String ACTION_STOP = "org.drivercontrol.drivercontrol.OCR_STOP";
    public static final String EXTRA_RESULT_CODE = "result_code";
    public static final String EXTRA_RESULT_DATA = "result_data";

    private static final String CHANNEL = "driver_control_ocr";
    private static final int NOTIFICATION_ID = 52;
    private static final long FRAME_INTERVAL_MS = 900L;
    private static final int MAX_OCR_WIDTH = 1080;
    private static final long CASH_REPEAT_GUARD_MS = 5000L;

    // Acepta ARS6.506, ARS 6,506, AR$5.600 y $5.600.
    private static final Pattern MONEY = Pattern.compile(
            "(?i)(?:ARS\\s*|AR\\s*\\$\\s*|\\$\\s*)([0-9OIl|][0-9OIl|.,\\s]*)"
    );
    private static final Pattern MINUTES = Pattern.compile(
            "(?i)[0-9OIl|]+(?:[.,][0-9OIl|]+)?\\s*(?:min\\.?|minuto(?:s)?)\\b"
    );
    private static final Pattern KM = Pattern.compile(
            "(?i)[0-9OIl|]+(?:[.,][0-9OIl|]+)?\\s*(?:km|kil[oó]metro(?:s)?)\\b"
    );

    private HandlerThread thread;
    private Handler worker;
    private MediaProjection projection;
    private VirtualDisplay virtualDisplay;
    private ImageReader reader;
    private TextRecognizer recognizer;
    private volatile boolean processing;
    private long lastFrameAt;
    private int lastTextHash;
    private long lastCashAt;
    private double lastCashFare = -1.0;

    @Override
    public void onCreate() {
        super.onCreate();
        thread = new HandlerThread("DriverControlOcr");
        thread.start();
        worker = new Handler(thread.getLooper());
        recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);

        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL,
                    "Lectura visual de ofertas",
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("OCR local de Driver Control");
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) return START_NOT_STICKY;
        if (ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }
        if (!ACTION_START.equals(intent.getAction()) || projection != null) return START_NOT_STICKY;

        startForeground(NOTIFICATION_ID, buildNotification());
        startOverlayIfAllowed();

        int resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED);
        Intent data;
        if (Build.VERSION.SDK_INT >= 33) {
            data = intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent.class);
        } else {
            //noinspection deprecation
            data = intent.getParcelableExtra(EXTRA_RESULT_DATA);
        }

        if (resultCode != Activity.RESULT_OK || data == null) {
            sendStatus("OCR sin permiso de captura");
            stopSelf();
            return START_NOT_STICKY;
        }

        try {
            startCapture(resultCode, data);
            sendStatus("OCR activo · abrí Uber");
        } catch (Throwable error) {
            sendStatus("No se pudo iniciar OCR");
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    private void startCapture(int resultCode, Intent data) {
        DisplayMetrics metrics = getResources().getDisplayMetrics();
        int width = metrics.widthPixels;
        int height = metrics.heightPixels;

        MediaProjectionManager manager =
                (MediaProjectionManager) getSystemService(MEDIA_PROJECTION_SERVICE);
        projection = manager.getMediaProjection(resultCode, data);
        if (projection == null) throw new IllegalStateException("MediaProjection nulo");

        projection.registerCallback(new MediaProjection.Callback() {
            @Override
            public void onStop() {
                stopSelf();
            }
        }, worker);

        reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
        reader.setOnImageAvailableListener(source -> processFrame(source, width, height), worker);
        virtualDisplay = projection.createVirtualDisplay(
                "DriverControlOfferOcr",
                width,
                height,
                metrics.densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                reader.getSurface(),
                null,
                worker
        );
    }

    private void processFrame(ImageReader source, int width, int height) {
        Image image = source.acquireLatestImage();
        if (image == null) return;

        long now = SystemClock.elapsedRealtime();
        if (processing || now - lastFrameAt < FRAME_INTERVAL_MS) {
            image.close();
            return;
        }
        processing = true;
        lastFrameAt = now;

        Bitmap full = null;
        Bitmap crop = null;
        Bitmap input = null;
        try {
            Image.Plane plane = image.getPlanes()[0];
            int pixelStride = plane.getPixelStride();
            int rowPadding = plane.getRowStride() - pixelStride * width;
            int bitmapWidth = width + rowPadding / pixelStride;
            full = Bitmap.createBitmap(bitmapWidth, height, Bitmap.Config.ARGB_8888);
            full.copyPixelsFromBuffer(plane.getBuffer());
        } catch (Throwable error) {
            processing = false;
            image.close();
            return;
        }
        image.close();

        try {
            // Se conserva casi toda la pantalla: el recorte antiguo del 28% podía perder la tarifa.
            int cropTop = Math.max(0, Math.round(height * 0.08f));
            int cropHeight = Math.max(1, height - cropTop);
            int safeWidth = Math.min(width, full.getWidth());
            crop = Bitmap.createBitmap(full, 0, cropTop, safeWidth, cropHeight);
            full.recycle();

            if (crop.getWidth() > MAX_OCR_WIDTH) {
                int scaledHeight = Math.max(1,
                        Math.round(crop.getHeight() * (MAX_OCR_WIDTH / (float) crop.getWidth())));
                input = Bitmap.createScaledBitmap(crop, MAX_OCR_WIDTH, scaledHeight, true);
                crop.recycle();
            } else {
                input = crop;
            }
        } catch (Throwable error) {
            if (full != null && !full.isRecycled()) full.recycle();
            if (crop != null && !crop.isRecycled()) crop.recycle();
            processing = false;
            return;
        }

        final Bitmap bitmapForOcr = input;
        recognizer.process(InputImage.fromBitmap(bitmapForOcr, 0))
                .addOnSuccessListener(result -> {
                    String text = result.getText();
                    if (text == null) return;
                    String trimmed = normalizeCurrencyTokens(text.trim());
                    if (trimmed.isEmpty()) return;
                    int hash = trimmed.hashCode();
                    if (hash == lastTextHash) return;
                    lastTextHash = hash;

                    double cashFare = detectStandaloneCashFare(trimmed);
                    if (cashFare >= 100.0) {
                        rememberCashFare(cashFare);
                        return;
                    }

                    sendText(trimmed);
                })
                .addOnFailureListener(error -> sendStatus("OCR no pudo leer este cuadro"))
                .addOnCompleteListener(task -> {
                    if (!bitmapForOcr.isRecycled()) bitmapForOcr.recycle();
                    processing = false;
                });
    }

    /**
     * Detecta la pantalla simple de cobro. La regla es deliberadamente estricta:
     * no debe contener minutos/km ni señales típicas de la tarjeta de oferta.
     */
    private double detectStandaloneCashFare(String text) {
        if (text == null || text.trim().isEmpty()) return -1.0;
        String lower = text.toLowerCase(Locale.ROOT);

        // Evita leer nuestro propio flotante/panel.
        if (lower.contains("driver control")
                || lower.contains("vuelto rápido")
                || lower.contains("vuelto rapido")
                || lower.contains("importe del viaje")
                || lower.contains("recibido")
                || lower.contains("minimizar")
                || lower.contains("limpiar")) {
            return -1.0;
        }

        // Si hay métricas, es una oferta y debe ir al OfferParser normal.
        if (MINUTES.matcher(text).find() || KM.matcher(text).find()) return -1.0;

        // Señales claras de la segunda pantalla (oferta de viaje).
        if (lower.contains("uber priority")
                || lower.contains("dni verificado")
                || lower.contains("por inicio de viaje")
                || lower.contains("incluido")
                || lower.contains("exclusivo")
                || lower.contains("aceptar")
                || lower.contains("viaje:")) {
            return -1.0;
        }

        Matcher matcher = MONEY.matcher(text);
        List<Double> unique = new ArrayList<>();
        while (matcher.find() && unique.size() < 6) {
            double value = parseLocaleNumber(matcher.group(1));
            if (value < 100.0 || value > 2_000_000.0) continue;
            boolean duplicate = false;
            for (double existing : unique) {
                if (Math.abs(existing - value) < 0.5) {
                    duplicate = true;
                    break;
                }
            }
            if (!duplicate) unique.add(value);
        }

        if (unique.isEmpty()) return -1.0;

        boolean cashContext = lower.contains("cobrar")
                || lower.contains("cobro")
                || lower.contains("efectivo")
                || lower.contains("paga")
                || lower.contains("pagar")
                || lower.contains("total a cobrar")
                || lower.contains("importe");

        // La pantalla de referencia tiene un único importe grande. Si hay varios
        // importes, solo aceptamos la lectura cuando existe contexto explícito de cobro.
        if (unique.size() > 1 && !cashContext) return -1.0;

        double best = unique.get(0);
        if (cashContext) {
            for (double value : unique) best = Math.max(best, value);
        }
        return best;
    }

    private void rememberCashFare(double fare) {
        long now = SystemClock.elapsedRealtime();
        if (Math.abs(lastCashFare - fare) < 0.5 && now - lastCashAt < CASH_REPEAT_GUARD_MS) return;
        lastCashFare = fare;
        lastCashAt = now;

        getSharedPreferences("driver_control_overlay", MODE_PRIVATE)
                .edit()
                .putFloat("last_offer_fare", (float) fare)
                .putFloat("last_cash_fare", (float) fare)
                .putLong("last_cash_detected_at", System.currentTimeMillis())
                .apply();

        startOverlayIfAllowed();
        sendStatus("OCR · cobro detectado " + money(fare) + " · tocá $ para vuelto");
    }

    /** Normaliza AR$ para que el parser de ofertas también pueda leerlo como ARS. */
    private String normalizeCurrencyTokens(String text) {
        if (text == null) return "";
        return text.replaceAll("(?i)A\\s*R\\s*\\$\\s*", "ARS");
    }

    private static double parseLocaleNumber(String raw) {
        if (raw == null) return -1.0;
        String s = raw.trim().replace(" ", "")
                .replace('I', '1').replace('i', '1').replace('l', '1')
                .replace('|', '1').replace('O', '0').replace('o', '0');
        try {
            int lastComma = s.lastIndexOf(',');
            int lastDot = s.lastIndexOf('.');
            if (lastComma >= 0 && lastDot >= 0) {
                if (lastComma > lastDot) s = s.replace(".", "").replace(',', '.');
                else s = s.replace(",", "");
            } else if (lastComma >= 0) {
                int digitsAfter = s.length() - lastComma - 1;
                s = digitsAfter <= 2 ? s.replace(',', '.') : s.replace(",", "");
            } else if (lastDot >= 0) {
                int digitsAfter = s.length() - lastDot - 1;
                if (digitsAfter == 3 && s.length() > 4) s = s.replace(".", "");
            }
            return Double.parseDouble(s);
        } catch (Exception ignored) {
            return -1.0;
        }
    }

    private String money(double value) {
        NumberFormat nf = NumberFormat.getNumberInstance(new Locale("es", "AR"));
        nf.setMaximumFractionDigits(0);
        return "$" + nf.format(value);
    }

    private void sendText(String text) {
        try {
            Intent overlayIntent = new Intent(this, DriverOverlayService.class)
                    .setAction(DriverOverlayService.ACTION_SOURCE_TEXT)
                    .putExtra(DriverOverlayService.EXTRA_SOURCE_TEXT, text)
                    .putExtra(DriverOverlayService.EXTRA_SOURCE_KIND, "OCR");
            startOverlayService(overlayIntent);
        } catch (Throwable ignored) {
        }
    }

    private void sendStatus(String message) {
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

    private Notification buildNotification() {
        PendingIntent stop = PendingIntent.getService(
                this,
                53,
                new Intent(this, OcrCaptureService.class).setAction(ACTION_STOP),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT
        );
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL)
                : new Notification.Builder(this);
        return builder
                .setContentTitle("Driver Control: OCR activo")
                .setContentText("Lectura visual local de ofertas y cobros")
                .setSmallIcon(android.R.drawable.ic_menu_camera)
                .setOngoing(true)
                .addAction(android.R.drawable.ic_delete, "Detener", stop)
                .build();
    }

    @Override
    public void onDestroy() {
        processing = false;
        if (reader != null) reader.setOnImageAvailableListener(null, null);
        if (virtualDisplay != null) virtualDisplay.release();
        if (reader != null) reader.close();
        if (projection != null) {
            try { projection.stop(); } catch (Throwable ignored) {}
        }
        if (recognizer != null) recognizer.close();
        if (thread != null) thread.quitSafely();

        virtualDisplay = null;
        reader = null;
        projection = null;
        recognizer = null;
        stopForeground(true);
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
