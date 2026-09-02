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
import android.util.DisplayMetrics;
import android.view.WindowManager;

import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;

/** Captura autorizada + OCR local. No guarda ni transmite imágenes. */
public class OcrCaptureService extends Service {
    public static final String ACTION_START = "org.drivercontrol.drivercontrol.OCR_START";
    public static final String ACTION_STOP = "org.drivercontrol.drivercontrol.OCR_STOP";
    public static final String EXTRA_RESULT_CODE = "result_code";
    public static final String EXTRA_RESULT_DATA = "result_data";
    private static final String CHANNEL = "driver_control_ocr";

    private HandlerThread thread;
    private Handler worker;
    private MediaProjection projection;
    private VirtualDisplay virtualDisplay;
    private ImageReader reader;
    private TextRecognizer recognizer;
    private volatile boolean processing;
    private long lastFrameAt;

    @Override public void onCreate() {
        super.onCreate();
        thread = new HandlerThread("DriverControlOcr");
        thread.start();
        worker = new Handler(thread.getLooper());
        recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(CHANNEL,
                    "Lectura visual de ofertas", NotificationManager.IMPORTANCE_LOW);
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null) return START_NOT_STICKY;
        if (ACTION_STOP.equals(intent.getAction())) { stopSelf(); return START_NOT_STICKY; }
        if (!ACTION_START.equals(intent.getAction()) || projection != null) return START_NOT_STICKY;
        startForeground(52, buildNotification());
        int resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED);
        Intent data;
        if (Build.VERSION.SDK_INT >= 33) data = intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent.class);
        else {
            //noinspection deprecation
            data = intent.getParcelableExtra(EXTRA_RESULT_DATA);
        }
        if (resultCode != Activity.RESULT_OK || data == null) { stopSelf(); return START_NOT_STICKY; }
        startCapture(resultCode, data);
        return START_NOT_STICKY;
    }

    private void startCapture(int resultCode, Intent data) {
        DisplayMetrics metrics = getResources().getDisplayMetrics();
        int width = metrics.widthPixels;
        int height = metrics.heightPixels;
        MediaProjectionManager manager = (MediaProjectionManager)
                getSystemService(MEDIA_PROJECTION_SERVICE);
        projection = manager.getMediaProjection(resultCode, data);
        projection.registerCallback(new MediaProjection.Callback() {
            @Override public void onStop() { stopSelf(); }
        }, worker);
        reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2);
        reader.setOnImageAvailableListener(source -> processFrame(source, width, height), worker);
        virtualDisplay = projection.createVirtualDisplay("DriverControlOfferOcr", width, height,
                metrics.densityDpi, DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                reader.getSurface(), null, worker);
    }

    private void processFrame(ImageReader source, int width, int height) {
        Image image = source.acquireLatestImage();
        if (image == null) return;
        long now = SystemClock.elapsedRealtime();
        if (processing || now - lastFrameAt < 800L) { image.close(); return; }
        processing = true;
        lastFrameAt = now;
        Bitmap full;
        try {
            Image.Plane plane = image.getPlanes()[0];
            int rowPadding = plane.getRowStride() - plane.getPixelStride() * width;
            full = Bitmap.createBitmap(width + rowPadding / plane.getPixelStride(), height,
                    Bitmap.Config.ARGB_8888);
            full.copyPixelsFromBuffer(plane.getBuffer());
        } catch (Throwable error) {
            image.close(); processing = false; return;
        }
        image.close();
        int cropTop = Math.round(height * 0.30f);
        Bitmap card = Bitmap.createBitmap(full, 0, cropTop, width, height - cropTop);
        full.recycle();
        recognizer.process(InputImage.fromBitmap(card, 0))
                .addOnSuccessListener(result -> {
                    String text = result.getText();
                    getSharedPreferences("driver_control_overlay", MODE_PRIVATE).edit()
                            .putString("last_ocr_text", text.substring(0, Math.min(1500, text.length())))
                            .apply();
                    sendBroadcast(new Intent(UberOfferAccessibilityService.ACTION_OCR_TEXT)
                            .setPackage(getPackageName())
                            .putExtra(UberOfferAccessibilityService.EXTRA_OCR_TEXT, text));
                })
                .addOnCompleteListener(task -> { card.recycle(); processing = false; });
    }

    private Notification buildNotification() {
        PendingIntent stop = PendingIntent.getService(this, 53,
                new Intent(this, OcrCaptureService.class).setAction(ACTION_STOP),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this, CHANNEL)
                .setContentTitle("Driver Control: lectura visual activa")
                .setContentText("Las ofertas se analizan localmente")
                .setSmallIcon(android.R.drawable.ic_menu_camera)
                .addAction(android.R.drawable.ic_delete, "Detener", stop)
                .build();
    }

    @Override public void onDestroy() {
        if (reader != null) reader.setOnImageAvailableListener(null, null);
        if (virtualDisplay != null) virtualDisplay.release();
        if (reader != null) reader.close();
        if (projection != null) projection.stop();
        if (recognizer != null) recognizer.close();
        if (thread != null) thread.quitSafely();
        projection = null;
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}
