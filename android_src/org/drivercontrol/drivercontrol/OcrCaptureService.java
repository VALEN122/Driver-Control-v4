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

/**
 * Captura autorizada + OCR local con ML Kit.
 * No persiste ni transmite capturas. Solo envía el texto reconocido al parser local.
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

    private HandlerThread thread;
    private Handler worker;
    private MediaProjection projection;
    private VirtualDisplay virtualDisplay;
    private ImageReader reader;
    private TextRecognizer recognizer;
    private volatile boolean processing;
    private long lastFrameAt;
    private int lastTextHash;

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
                    String trimmed = text.trim();
                    if (trimmed.isEmpty()) return;
                    int hash = trimmed.hashCode();
                    if (hash == lastTextHash) return;
                    lastTextHash = hash;
                    sendText(trimmed);
                })
                .addOnFailureListener(error -> sendStatus("OCR no pudo leer este cuadro"))
                .addOnCompleteListener(task -> {
                    if (!bitmapForOcr.isRecycled()) bitmapForOcr.recycle();
                    processing = false;
                });
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
                .setContentText("Lectura visual local de ofertas")
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
