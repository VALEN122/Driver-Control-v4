package org.drivercontrol.drivercontrol;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.os.VibratorManager;
import android.provider.Settings;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.text.NumberFormat;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Flotante independiente de Accesibilidad.
 *
 * <p>Recibe texto desde Accesibilidad u OCR, lo delega a {@link OfferParser},
 * analiza la oferta y muestra una recomendación. También mantiene una calculadora
 * de vuelto independiente. Nunca pulsa botones de Uber.</p>
 */
public class DriverOverlayService extends Service {
    public static final String ACTION_START = "org.drivercontrol.drivercontrol.OVERLAY_START";
    public static final String ACTION_STOP = "org.drivercontrol.drivercontrol.OVERLAY_STOP";
    public static final String ACTION_SOURCE_TEXT = "org.drivercontrol.drivercontrol.SOURCE_TEXT";
    public static final String ACTION_READER_STATUS = "org.drivercontrol.drivercontrol.READER_STATUS";
    public static final String ACTION_CASH_FARE = "org.drivercontrol.drivercontrol.CASH_FARE";

    public static final String EXTRA_SOURCE_TEXT = "source_text";
    public static final String EXTRA_SOURCE_KIND = "source_kind";
    public static final String EXTRA_READER_STATUS = "reader_status";
    public static final String EXTRA_CASH_FARE = "cash_fare";

    private static final String CHANNEL = "driver_control_overlay";
    private static final int NOTIFICATION_ID = 61;
    private static final long OFFER_VISIBLE_MS = 7500L;
    private static final long STATUS_VISIBLE_MS = 2600L;

    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private WindowManager windowManager;
    private LinearLayout tripOverlay;
    private TextView verdictView;
    private TextView headlineView;
    private TextView metricsView;
    private TextView changeBubble;
    private LinearLayout changePanel;
    private TextView statusChip;

    private String lastSignature = "";
    private long lastOfferAt = 0L;
    private String lastReaderStatus = "Sin lecturas todavía";
    private String lastReaderExcerpt = "";

    private final Runnable hideStaleOffer = new Runnable() {
        @Override
        public void run() {
            long age = SystemClock.elapsedRealtime() - lastOfferAt;
            if (lastOfferAt > 0 && age >= OFFER_VISIBLE_MS) hideTripOverlay();
        }
    };

    private final Runnable hideStatus = new Runnable() {
        @Override
        public void run() {
            removeStatusChip();
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL,
                    "Driver Control flotante",
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Asistente de viajes y vuelto rápido");
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }
        restoreReaderStatus();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }

        startForeground(NOTIFICATION_ID, buildNotification());

        if (Settings.canDrawOverlays(this)) showChangeBubble();

        if (intent != null) {
            String action = intent.getAction();
            if (ACTION_SOURCE_TEXT.equals(action)) {
                processSourceText(
                        intent.getStringExtra(EXTRA_SOURCE_TEXT),
                        safeSourceKind(intent.getStringExtra(EXTRA_SOURCE_KIND))
                );
            } else if (ACTION_CASH_FARE.equals(action)) {
                double fare = intent.getDoubleExtra(EXTRA_CASH_FARE, 0.0);
                if (fare > 0.0) handleDetectedCashFare(fare);
            } else if (ACTION_READER_STATUS.equals(action)) {
                String message = intent.getStringExtra(EXTRA_READER_STATUS);
                if (message != null && !message.trim().isEmpty()) {
                    updateReaderStatus(message.trim(), "");
                    showTransientStatus(message.trim(), false);
                }
            }
        }
        return START_STICKY;
    }

    private String safeSourceKind(String sourceKind) {
        return sourceKind == null || sourceKind.trim().isEmpty() ? "Lector" : sourceKind.trim();
    }

    private void processSourceText(String raw, String sourceKind) {
        if (raw == null || raw.trim().isEmpty()) {
            updateReaderStatus(sourceKind + " · sin texto", "");
            return;
        }

        OfferParser.ParseResult parsed = OfferParser.parse(raw);
        String diagnostic = sourceKind + " · " + parsed.diagnostic;
        updateReaderStatus(diagnostic, parsed.excerpt);

        if (parsed.offer == null || !parsed.offer.isUsable()) {
            if (parsed.candidate) showTransientStatus(diagnostic, true);
            return;
        }

        OfferParser.Offer offer = parsed.offer;
        Analysis analysis = analyze(offer);
        String signature = offer.fare + "|" + offer.pickupMin + "|" + offer.pickupKm
                + "|" + offer.tripMin + "|" + offer.tripKm;

        getSharedPreferences("driver_control_overlay", MODE_PRIVATE)
                .edit()
                .putFloat("last_offer_fare", (float) offer.fare)
                .apply();

        lastOfferAt = SystemClock.elapsedRealtime();
        mainHandler.removeCallbacks(hideStaleOffer);
        mainHandler.postDelayed(hideStaleOffer, OFFER_VISIBLE_MS + 100L);

        if (!signature.equals(lastSignature) || tripOverlay == null) {
            lastSignature = signature;
            showOrUpdateTripOverlay(analysis);
            vibrateOffer(analysis);
        } else {
            showOrUpdateTripOverlay(analysis);
        }
        // El propio borde del veredicto confirma la lectura; no se superpone un chip.
    }

    private void updateReaderStatus(String status, String excerpt) {
        lastReaderStatus = status;
        if (excerpt != null && !excerpt.trim().isEmpty()) lastReaderExcerpt = excerpt.trim();
        getSharedPreferences("driver_control_overlay", MODE_PRIVATE)
                .edit()
                .putString("last_reader_status", lastReaderStatus)
                .putString("last_reader_excerpt", lastReaderExcerpt)
                .putLong("last_reader_at", System.currentTimeMillis())
                .apply();
    }

    private void restoreReaderStatus() {
        SharedPreferences p = getSharedPreferences("driver_control_overlay", MODE_PRIVATE);
        lastReaderStatus = p.getString("last_reader_status", "Sin lecturas todavía");
        lastReaderExcerpt = p.getString("last_reader_excerpt", "");
    }

    private Notification buildNotification() {
        PendingIntent stop = PendingIntent.getService(
                this,
                62,
                new Intent(this, DriverOverlayService.class).setAction(ACTION_STOP),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT
        );
        Notification.Builder builder = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL)
                : new Notification.Builder(this);
        return builder
                .setContentTitle("Driver Control activo")
                .setContentText("Filtro de viajes y vuelto flotante")
                .setSmallIcon(android.R.drawable.ic_menu_directions)
                .setOngoing(true)
                .addAction(android.R.drawable.ic_delete, "Detener", stop)
                .build();
    }

    private void showOrUpdateTripOverlay(Analysis a) {
        if (!Settings.canDrawOverlays(this) || windowManager == null) return;
        if (tripOverlay == null) createTripOverlay();
        if (tripOverlay == null) return;

        verdictView.setText(a.verdict);
        verdictView.setTextColor(a.accentColor);
        tripOverlay.setBackground(rounded(
                Color.argb(248, 13, 17, 23),
                18,
                a.accentColor
        ));
        headlineView.setText(money(a.hourly) + "/h  ·  " + money(a.perKm) + "/km");
        metricsView.setText(
                money(a.offer.fare) + " · " + fmt1(a.offer.pickupKm + a.offer.tripKm)
                        + " km · " + Math.round(a.offer.pickupMin + a.offer.tripMin) + " min"
                        + "\nGanancia limpia estimada " + money(a.net)
        );

        if (tripOverlay.getParent() == null) {
            try {
                windowManager.addView(tripOverlay, tripLayoutParams());
            } catch (Throwable error) {
                tripOverlay = null;
            }
        }
    }

    private void createTripOverlay() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(13), dp(10), dp(13), dp(10));
        box.setBackground(rounded(
                Color.argb(245, 17, 24, 32),
                16,
                Color.argb(180, 130, 145, 160)
        ));
        box.setElevation(dp(8));

        verdictView = textView(28, true, Color.WHITE);
        verdictView.setGravity(Gravity.CENTER);
        headlineView = textView(20, true, Color.WHITE);
        headlineView.setGravity(Gravity.CENTER);
        metricsView = textView(12, false, Color.rgb(210, 220, 230));
        box.addView(verdictView);
        box.addView(headlineView);
        box.addView(metricsView);
        box.setOnClickListener(v -> metricsView.setVisibility(
                metricsView.getVisibility() == View.VISIBLE ? View.GONE : View.VISIBLE
        ));
        tripOverlay = box;
    }

    private WindowManager.LayoutParams tripLayoutParams() {
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                Math.min(dp(390), getResources().getDisplayMetrics().widthPixels - dp(20)),
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT
        );
        lp.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
        lp.y = dp(84);
        return lp;
    }

    private void hideTripOverlay() {
        if (tripOverlay != null && windowManager != null && tripOverlay.getParent() != null) {
            try { windowManager.removeView(tripOverlay); } catch (Throwable ignored) {}
        }
        lastSignature = "";
        lastOfferAt = 0L;
    }

    private void showTransientStatus(String message, boolean warning) {
        if (!Settings.canDrawOverlays(this) || windowManager == null || message == null) return;
        removeStatusChip();

        TextView chip = new TextView(this);
        chip.setText(message);
        chip.setTextSize(12);
        chip.setTextColor(Color.WHITE);
        chip.setGravity(Gravity.CENTER);
        chip.setPadding(dp(12), dp(7), dp(12), dp(7));
        chip.setBackground(rounded(
                warning ? Color.argb(245, 120, 72, 15) : Color.argb(245, 26, 82, 63),
                14,
                warning ? Color.rgb(235, 170, 75) : Color.rgb(90, 205, 145)
        ));
        chip.setElevation(dp(6));
        statusChip = chip;

        try {
            windowManager.addView(statusChip, statusLayoutParams());
            mainHandler.removeCallbacks(hideStatus);
            mainHandler.postDelayed(hideStatus, STATUS_VISIBLE_MS);
        } catch (Throwable ignored) {
            statusChip = null;
        }
    }

    private WindowManager.LayoutParams statusLayoutParams() {
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT
        );
        lp.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
        lp.y = dp(84);
        return lp;
    }

    private void removeStatusChip() {
        if (statusChip != null && windowManager != null && statusChip.getParent() != null) {
            try { windowManager.removeView(statusChip); } catch (Throwable ignored) {}
        }
        statusChip = null;
    }

    private void showChangeBubble() {
        if (!Settings.canDrawOverlays(this) || windowManager == null) return;
        if (changePanel != null && changePanel.getParent() != null) return;

        if (changeBubble == null) {
            TextView bubble = new TextView(this);
            bubble.setText("$");
            bubble.setTextColor(Color.WHITE);
            bubble.setTextSize(24);
            bubble.setGravity(Gravity.CENTER);
            bubble.setTypeface(bubble.getTypeface(), android.graphics.Typeface.BOLD);
            bubble.setBackground(rounded(Color.rgb(0, 153, 204), 28, Color.WHITE));
            bubble.setElevation(dp(10));
            bubble.setOnClickListener(v -> showChangePanel());
            bubble.setOnLongClickListener(v -> {
                String message = lastReaderStatus;
                if (!lastReaderExcerpt.isEmpty()) message += "\n" + lastReaderExcerpt;
                showTransientStatus(message, !lastReaderStatus.contains("oferta completa")
                        && !lastReaderStatus.contains("oferta leída"));
                return true;
            });
            changeBubble = bubble;
        }

        if (changeBubble.getParent() == null) {
            try {
                windowManager.addView(changeBubble, bubbleLayoutParams());
            } catch (Throwable error) {
                changeBubble = null;
            }
        }
    }

    private WindowManager.LayoutParams bubbleLayoutParams() {
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                dp(58),
                dp(58),
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
                        | WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT
        );
        lp.gravity = Gravity.END | Gravity.CENTER_VERTICAL;
        lp.x = dp(10);
        return lp;
    }

    private void showChangePanel() {
        if (!Settings.canDrawOverlays(this) || windowManager == null) return;
        removeChangeBubble();
        if (changePanel != null && changePanel.getParent() != null) return;

        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(14), dp(12), dp(14), dp(12));
        panel.setBackground(rounded(
                Color.argb(250, 17, 24, 32),
                18,
                Color.argb(190, 130, 145, 160)
        ));
        panel.setElevation(dp(12));

        LinearLayout titleRow = new LinearLayout(this);
        titleRow.setOrientation(LinearLayout.HORIZONTAL);
        TextView title = textView(18, true, Color.WHITE);
        title.setText("Vuelto rápido");
        titleRow.addView(title, new LinearLayout.LayoutParams(0, dp(44), 1f));
        Button close = button("×");
        close.setOnClickListener(v -> closeChangePanel());
        titleRow.addView(close, new LinearLayout.LayoutParams(dp(52), dp(44)));
        panel.addView(titleRow);

        EditText fare = numberField("Importe del viaje");
        EditText received = numberField("Recibido");
        panel.addView(fare, new LinearLayout.LayoutParams(-1, dp(58)));
        panel.addView(received, new LinearLayout.LayoutParams(-1, dp(58)));

        TextView result = textView(25, true, Color.WHITE);
        result.setGravity(Gravity.CENTER);
        result.setText("VUELTO $0");
        panel.addView(result, new LinearLayout.LayoutParams(-1, dp(62)));

        LinearLayout quickRow = new LinearLayout(this);
        quickRow.setOrientation(LinearLayout.HORIZONTAL);
        quickRow.setGravity(Gravity.CENTER);
        Button q1 = button("$10.000");
        Button q2 = button("$20.000");
        Button q3 = button("$50.000");
        quickRow.addView(q1, new LinearLayout.LayoutParams(0, dp(50), 1f));
        quickRow.addView(q2, new LinearLayout.LayoutParams(0, dp(50), 1f));
        quickRow.addView(q3, new LinearLayout.LayoutParams(0, dp(50), 1f));
        panel.addView(quickRow);

        LinearLayout bottomRow = new LinearLayout(this);
        bottomRow.setOrientation(LinearLayout.HORIZONTAL);
        Button clear = button("LIMPIAR");
        Button minimize = button("MINIMIZAR");
        bottomRow.addView(clear, new LinearLayout.LayoutParams(0, dp(50), 1f));
        bottomRow.addView(minimize, new LinearLayout.LayoutParams(0, dp(50), 1f));
        panel.addView(bottomRow);

        final double[] quickValues = new double[]{10000, 20000, 50000};
        View.OnClickListener quickListener = v -> {
            double value = v == q1 ? quickValues[0] : (v == q2 ? quickValues[1] : quickValues[2]);
            received.setText(plainNumber(value));
            received.setSelection(received.getText().length());
            vibratePattern(new long[]{0, 55, 55, 55});
        };
        q1.setOnClickListener(quickListener);
        q2.setOnClickListener(quickListener);
        q3.setOnClickListener(quickListener);

        Runnable update = () -> {
            double fareValue = parseInput(fare.getText().toString());
            double receivedValue = parseInput(received.getText().toString());
            double[] suggested = suggestedAmounts(fareValue);
            quickValues[0] = suggested[0];
            quickValues[1] = suggested[1];
            quickValues[2] = suggested[2];
            q1.setText(money(suggested[0]));
            q2.setText(money(suggested[1]));
            q3.setText(money(suggested[2]));

            if (fareValue <= 0) {
                result.setText("VUELTO $0");
                result.setTextColor(Color.WHITE);
            } else if (receivedValue >= fareValue) {
                result.setText("VUELTO " + money(receivedValue - fareValue));
                result.setTextColor(Color.rgb(70, 220, 140));
            } else if (receivedValue > 0) {
                result.setText("FALTAN " + money(fareValue - receivedValue));
                result.setTextColor(Color.rgb(255, 190, 70));
            } else {
                result.setText("VUELTO $0");
                result.setTextColor(Color.WHITE);
            }
        };

        TextWatcher watcher = new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) { update.run(); }
            @Override public void afterTextChanged(Editable s) {}
        };
        fare.addTextChangedListener(watcher);
        received.addTextChangedListener(watcher);

        clear.setOnClickListener(v -> {
            received.setText("");
            received.requestFocus();
        });
        minimize.setOnClickListener(v -> closeChangePanel());

        SharedPreferences prefs = getSharedPreferences("driver_control_overlay", MODE_PRIVATE);
        double lastFare = prefs.getFloat("last_offer_fare", 0f);
        if (lastFare > 0) fare.setText(plainNumber(lastFare));
        update.run();

        changePanel = panel;
        try {
            windowManager.addView(changePanel, changePanelLayoutParams());
            // Con una tarifa leída por OCR se priorizan los botones grandes y no se
            // abre el teclado sobre Uber. El teclado queda disponible tocando el campo.
            if (lastFare <= 0) {
                fare.requestFocus();
                fare.postDelayed(() -> {
                    InputMethodManager imm = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
                    if (imm != null) imm.showSoftInput(fare, InputMethodManager.SHOW_IMPLICIT);
                }, 180L);
            } else {
                panel.setFocusableInTouchMode(true);
                panel.requestFocus();
            }
        } catch (Throwable ignored) {
            changePanel = null;
            showChangeBubble();
        }
    }

    /** Abre el vuelto únicamente cuando OCR identifica una pantalla final de cobro. */
    private void handleDetectedCashFare(double fare) {
        getSharedPreferences("driver_control_overlay", MODE_PRIVATE)
                .edit()
                .putFloat("last_offer_fare", (float) fare)
                .putFloat("last_cash_fare", (float) fare)
                .apply();
        hideTripOverlay();
        closeChangePanelWithoutBubble();
        vibratePattern(new long[]{0, 90, 80, 90});
        showChangePanel();
    }

    private void closeChangePanelWithoutBubble() {
        if (changePanel != null && windowManager != null && changePanel.getParent() != null) {
            try { windowManager.removeView(changePanel); } catch (Throwable ignored) {}
        }
        changePanel = null;
        removeChangeBubble();
    }

    private void vibrateOffer(Analysis analysis) {
        // Una confirmación clara para viaje viable; pulso distinto para descartarlo.
        if ("CONVIENE".equals(analysis.verdict)) vibratePattern(new long[]{0, 140});
        else if ("NO CONVIENE".equals(analysis.verdict)) vibratePattern(new long[]{0, 70, 70, 70});
        else vibratePattern(new long[]{0, 90});
    }

    private void vibratePattern(long[] pattern) {
        try {
            Vibrator vibrator;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                VibratorManager manager = (VibratorManager) getSystemService(VIBRATOR_MANAGER_SERVICE);
                vibrator = manager == null ? null : manager.getDefaultVibrator();
            } else {
                vibrator = (Vibrator) getSystemService(VIBRATOR_SERVICE);
            }
            if (vibrator == null || !vibrator.hasVibrator()) return;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator.vibrate(VibrationEffect.createWaveform(pattern, -1));
            } else {
                //noinspection deprecation
                vibrator.vibrate(pattern, -1);
            }
        } catch (Throwable ignored) {}
    }

    private WindowManager.LayoutParams changePanelLayoutParams() {
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                Math.min(dp(360), getResources().getDisplayMetrics().widthPixels - dp(24)),
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT
        );
        lp.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
        lp.y = dp(120);
        lp.softInputMode = WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE;
        return lp;
    }

    private void closeChangePanel() {
        if (changePanel != null && windowManager != null && changePanel.getParent() != null) {
            try { windowManager.removeView(changePanel); } catch (Throwable ignored) {}
        }
        changePanel = null;
        showChangeBubble();
    }

    private void removeChangeBubble() {
        if (changeBubble != null && windowManager != null && changeBubble.getParent() != null) {
            try { windowManager.removeView(changeBubble); } catch (Throwable ignored) {}
        }
    }

    private EditText numberField(String hint) {
        EditText field = new EditText(this);
        field.setHint(hint);
        field.setTextColor(Color.WHITE);
        field.setHintTextColor(Color.rgb(160, 175, 190));
        field.setTextSize(19);
        field.setSingleLine(true);
        field.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        field.setPadding(dp(10), dp(4), dp(10), dp(4));
        field.setBackground(rounded(Color.rgb(30, 40, 52), 12, Color.rgb(95, 115, 135)));
        return field;
    }

    private Button button(String text) {
        Button button = new Button(this);
        button.setText(text);
        button.setTextSize(13);
        button.setTextColor(Color.WHITE);
        button.setAllCaps(false);
        button.setBackground(rounded(Color.rgb(40, 54, 68), 10, Color.rgb(85, 105, 125)));
        return button;
    }

    private TextView textView(int sp, boolean bold, int color) {
        TextView text = new TextView(this);
        text.setTextSize(sp);
        text.setTextColor(color);
        if (bold) text.setTypeface(text.getTypeface(), android.graphics.Typeface.BOLD);
        text.setPadding(0, dp(2), 0, dp(2));
        return text;
    }

    private GradientDrawable rounded(int color, int radiusDp, int strokeColor) {
        GradientDrawable background = new GradientDrawable();
        background.setColor(color);
        background.setCornerRadius(dp(radiusDp));
        background.setStroke(dp(1), strokeColor);
        return background;
    }

    private double[] suggestedAmounts(double fare) {
        double[] steps = {1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000};
        double[] out = new double[3];
        int index = 0;
        for (double step : steps) {
            if (step >= Math.max(1, fare) && index < 3) out[index++] = step;
        }
        double base = index > 0 ? out[index - 1] : Math.max(1000, Math.ceil(fare / 10000.0) * 10000.0);
        while (index < 3) {
            base *= 2;
            out[index++] = base;
        }
        return out;
    }

    private Analysis analyze(OfferParser.Offer offer) {
        TripProfitabilityAnalyzer.Result result = TripProfitabilityAnalyzer.analyze(
                this, offer.fare, offer.pickupMin, offer.pickupKm, offer.tripMin, offer.tripKm);
        String verdict;
        int accent;
        if (result.verdict == TripProfitabilityAnalyzer.Verdict.ACCEPT) {
            verdict = "CONVIENE";
            accent = Color.rgb(26, 190, 109);
        } else if (result.verdict == TripProfitabilityAnalyzer.Verdict.REVIEW) {
            verdict = "DUDOSO";
            accent = Color.rgb(230, 170, 35);
        } else {
            verdict = "NO CONVIENE";
            accent = Color.rgb(225, 65, 75);
        }
        return new Analysis(
                offer, result.liters, result.fuelCost, result.netProfit,
                result.perHour, result.perKm, result.score, verdict, accent);
    }

    private static double parseInput(String raw) {
        if (raw == null || raw.trim().isEmpty()) return 0.0;
        double parsed = OfferParser.parseLocaleNumber(raw);
        return parsed < 0 ? 0.0 : parsed;
    }

    private String money(double value) {
        NumberFormat nf = NumberFormat.getNumberInstance(new Locale("es", "AR"));
        nf.setMaximumFractionDigits(0);
        return "$" + nf.format(value);
    }

    private String plainNumber(double value) {
        return String.valueOf(Math.round(Math.max(0, value)));
    }

    private String fmt1(double value) {
        return String.format(new Locale("es", "AR"), "%.1f", value);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static double clamp(double value, double min, double max) {
        return Math.max(min, Math.min(max, value));
    }

    @Override
    public void onDestroy() {
        mainHandler.removeCallbacks(hideStaleOffer);
        mainHandler.removeCallbacks(hideStatus);
        hideTripOverlay();
        removeStatusChip();
        if (changePanel != null && windowManager != null && changePanel.getParent() != null) {
            try { windowManager.removeView(changePanel); } catch (Throwable ignored) {}
        }
        changePanel = null;
        removeChangeBubble();
        stopForeground(true);
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private static final class Analysis {
        final OfferParser.Offer offer;
        final double liters;
        final double fuelCost;
        final double net;
        final double hourly;
        final double perKm;
        final double score;
        final String verdict;
        final int accentColor;

        Analysis(
                OfferParser.Offer offer,
                double liters,
                double fuelCost,
                double net,
                double hourly,
                double perKm,
                double score,
                String verdict,
                int accentColor
        ) {
            this.offer = offer;
            this.liters = liters;
            this.fuelCost = fuelCost;
            this.net = net;
            this.hourly = hourly;
            this.perKm = perKm;
            this.score = score;
            this.verdict = verdict;
            this.accentColor = accentColor;
        }
    }

    /** Parser local tolerante de ofertas de Uber. */
    private static final class OfferParser {

            private OfferParser() {}

            private static final Pattern MONEY = Pattern.compile(
                    "(?i)(?<!\\w)(?:ARS\\s*|\\$\\s*)([0-9OIl|][0-9OIl|.,\\s]*)");
            private static final Pattern MINUTES = Pattern.compile(
                    "(?i)([0-9OIl|]+(?:[.,][0-9OIl|]+)?)\\s*(?:min\\.?|minuto(?:s)?)\\b");
            private static final Pattern KM = Pattern.compile(
                    "(?i)([0-9OIl|]+(?:[.,][0-9OIl|]+)?)\\s*(?:km|kil[oó]metro(?:s)?)\\b");
            private static final Pattern MIN_THEN_KM = Pattern.compile(
                    "(?i)([0-9OIl|]+(?:[.,][0-9OIl|]+)?)\\s*(?:min\\.?|minuto(?:s)?)\\b.{0,100}?"
                            + "([0-9OIl|]+(?:[.,][0-9OIl|]+)?)\\s*(?:km|kil[oó]metro(?:s)?)\\b");
            private static final Pattern KM_THEN_MIN = Pattern.compile(
                    "(?i)([0-9OIl|]+(?:[.,][0-9OIl|]+)?)\\s*(?:km|kil[oó]metro(?:s)?)\\b.{0,100}?"
                            + "([0-9OIl|]+(?:[.,][0-9OIl|]+)?)\\s*(?:min\\.?|minuto(?:s)?)\\b");

            private static final String[] PICKUP_HINTS = {
                    "para llegar", "a buscar", "buscar", "recoger", "recogida", "pickup",
                    "hasta el punto", "para recoger", "llegar al pasajero"
            };
            private static final String[] TRIP_HINTS = {
                    "de viaje", "viaje", "duración", "duracion", "trayecto", "destino",
                    "hasta destino", "recorrido"
            };
            private static final String[] OFFER_HINTS = {
                    "uberx", "comfort", "moto", "solicitud", "oferta", "aceptar", "aceptá",
                    "acepta", "tarifa", "ganás", "ganas", "incluye", "destino", "recoger",
                    "para llegar", "de viaje"
            };

            public static ParseResult parse(String raw) {
                if (raw == null || raw.trim().isEmpty()) {
                    return ParseResult.failure("sin texto", false, "");
                }

                List<String> lines = sanitizeLines(raw);
                if (lines.isEmpty()) {
                    return ParseResult.failure("sin texto útil", false, "");
                }

                String joined = join(lines, " | ");
                boolean hasMoney = MONEY.matcher(joined).find();
                boolean hasMinutes = MINUTES.matcher(joined).find();
                boolean hasKm = KM.matcher(joined).find();
                boolean candidate = hasMoney || (hasMinutes && hasKm) || containsAny(joined.toLowerCase(Locale.ROOT), OFFER_HINTS);

                double fare = chooseFare(lines);
                if (fare < 100.0) {
                    return ParseResult.failure("falta tarifa", candidate, excerpt(joined));
                }

                List<MetricPair> pairs = extractPairs(lines);
                MetricPair pickup = null;
                MetricPair trip = null;

                for (MetricPair p : pairs) {
                    if (pickup == null && containsAny(p.context, PICKUP_HINTS)) pickup = p;
                    if (trip == null && containsAny(p.context, TRIP_HINTS)) trip = p;
                }

                if (pairs.size() >= 2) {
                    if (pickup == null && trip == null) {
                        pickup = pairs.get(0);
                        trip = pairs.get(1);
                    } else if (pickup == null) {
                        pickup = firstDifferent(pairs, trip);
                    } else if (trip == null) {
                        trip = firstDifferent(pairs, pickup);
                    }
                }

                if (pickup == null || trip == null) {
                    List<Double> mins = findAll(MINUTES, joined, 1);
                    List<Double> kms = findAll(KM, joined, 1);
                    if (mins.size() >= 2 && kms.size() >= 2) {
                        if (pickup == null) pickup = new MetricPair(mins.get(0), kms.get(0), "fallback");
                        if (trip == null) trip = new MetricPair(mins.get(1), kms.get(1), "fallback");
                    }
                }

                if (pickup == null) {
                    return ParseResult.failure("faltan minutos/km para buscar", true, excerpt(joined));
                }
                if (trip == null) {
                    return ParseResult.failure("faltan minutos/km del viaje", true, excerpt(joined));
                }
                if (!isReasonablePair(pickup) || !isReasonablePair(trip)) {
                    return ParseResult.failure("datos fuera de rango", true, excerpt(joined));
                }

                Offer offer = new Offer(fare, pickup.minutes, pickup.km, trip.minutes, trip.km);
                return ParseResult.success(offer, excerpt(joined));
            }

            private static List<String> sanitizeLines(String raw) {
                List<String> out = new ArrayList<>();
                String[] split = raw.replace('\u00A0', ' ').split("\\r?\\n");
                for (String line : split) {
                    String cleaned = line == null ? "" : line.trim().replaceAll("\\s+", " ");
                    if (cleaned.isEmpty()) continue;
                    String lower = cleaned.toLowerCase(Locale.ROOT);
                    // Evita que OCR vuelva a analizar el propio flotante de Driver Control.
                    if (lower.contains("driver control") || lower.contains("vuelto ") || lower.equals("vuelto")
                            || lower.contains("nafta ") || lower.contains("$/h") || lower.contains("$/km")
                            || lower.contains("no conviene") || lower.contains("conviene ")
                            || lower.startsWith("conviene") || lower.contains("dudoso")) {
                        continue;
                    }
                    if (cleaned.length() > 240) cleaned = cleaned.substring(0, 240);
                    out.add(cleaned);
                    if (out.size() >= 140) break;
                }
                return out;
            }

            private static double chooseFare(List<String> lines) {
                List<FareCandidate> candidates = new ArrayList<>();
                for (int i = 0; i < lines.size(); i++) {
                    String line = lines.get(i);
                    String lower = line.toLowerCase(Locale.ROOT);
                    Matcher m = MONEY.matcher(line);
                    while (m.find()) {
                        double value = parseLocaleNumber(m.group(1));
                        if (value < 100 || value > 2_000_000) continue;
                        int score = 0;
                        if (containsAny(lower, OFFER_HINTS)) score += 5;
                        if (lower.contains("tarifa") || lower.contains("ganás") || lower.contains("ganas")) score += 4;
                        if (lower.contains("$/") || lower.contains("por km") || lower.contains("por hora")) score -= 8;
                        if (i < 12) score += 1;
                        candidates.add(new FareCandidate(value, score, i));
                    }
                }
                if (candidates.isEmpty()) return -1;
                candidates.sort(Comparator
                        .comparingInt((FareCandidate c) -> c.score).reversed()
                        .thenComparingInt(c -> c.lineIndex)
                        .thenComparingDouble(c -> -c.value));
                int bestScore = candidates.get(0).score;
                double best = candidates.get(0).value;
                if (bestScore <= 1) {
                    // Sin contexto, la tarifa suele ser el importe monetario más alto visible en la tarjeta.
                    for (FareCandidate c : candidates) best = Math.max(best, c.value);
                }
                return best;
            }

            private static List<MetricPair> extractPairs(List<String> lines) {
                List<MetricPair> out = new ArrayList<>();
                for (int i = 0; i < lines.size(); i++) {
                    String line = lines.get(i);
                    // Primero se intenta la línea aislada para no mezclar pickup y viaje contiguos.
                    MetricPair p = matchPair(line);
                    if (p == null && i + 1 < lines.size()) {
                        // OCR puede separar minutos y km de una misma fila en dos líneas.
                        p = matchPair(line + " " + lines.get(i + 1));
                    }
                    if (p != null && !containsSimilar(out, p)) {
                        out.add(p);
                        if (out.size() >= 6) break;
                    }
                }
                return out;
            }

            private static MetricPair matchPair(String text) {
                Matcher a = MIN_THEN_KM.matcher(text);
                if (a.find()) {
                    return new MetricPair(parseLocaleNumber(a.group(1)), parseLocaleNumber(a.group(2)),
                            text.toLowerCase(Locale.ROOT));
                }
                Matcher b = KM_THEN_MIN.matcher(text);
                if (b.find()) {
                    return new MetricPair(parseLocaleNumber(b.group(2)), parseLocaleNumber(b.group(1)),
                            text.toLowerCase(Locale.ROOT));
                }
                return null;
            }

            private static boolean containsSimilar(List<MetricPair> values, MetricPair candidate) {
                for (MetricPair p : values) {
                    if (Math.abs(p.minutes - candidate.minutes) < 0.01 && Math.abs(p.km - candidate.km) < 0.01) return true;
                }
                return false;
            }

            private static MetricPair firstDifferent(List<MetricPair> values, MetricPair excluded) {
                for (MetricPair p : values) if (p != excluded) return p;
                return null;
            }

            private static boolean isReasonablePair(MetricPair p) {
                return p.minutes >= 0 && p.minutes <= 240 && p.km >= 0 && p.km <= 500;
            }

            private static List<Double> findAll(Pattern pattern, String text, int group) {
                List<Double> out = new ArrayList<>();
                Matcher m = pattern.matcher(text);
                while (m.find() && out.size() < 12) {
                    double v = parseLocaleNumber(m.group(group));
                    if (v >= 0) out.add(v);
                }
                return out;
            }

            static double parseLocaleNumber(String raw) {
                if (raw == null) return -1;
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
                    return -1;
                }
            }

            private static boolean containsAny(String text, String[] needles) {
                for (String needle : needles) if (text.contains(needle)) return true;
                return false;
            }

            private static String join(List<String> values, String separator) {
                StringBuilder b = new StringBuilder();
                for (String value : values) {
                    if (b.length() > 0) b.append(separator);
                    b.append(value);
                }
                return b.toString();
            }

            private static String excerpt(String text) {
                String compact = text.replaceAll("\\s+", " ").trim();
                return compact.length() <= 280 ? compact : compact.substring(0, 280) + "…";
            }

            private static final class MetricPair {
                final double minutes;
                final double km;
                final String context;
                MetricPair(double minutes, double km, String context) {
                    this.minutes = minutes;
                    this.km = km;
                    this.context = context;
                }
            }

            private static final class FareCandidate {
                final double value;
                final int score;
                final int lineIndex;
                FareCandidate(double value, int score, int lineIndex) {
                    this.value = value;
                    this.score = score;
                    this.lineIndex = lineIndex;
                }
            }

            public static final class Offer {
                public final double fare;
                public final double pickupMin;
                public final double pickupKm;
                public final double tripMin;
                public final double tripKm;

                public Offer(double fare, double pickupMin, double pickupKm, double tripMin, double tripKm) {
                    this.fare = fare;
                    this.pickupMin = pickupMin;
                    this.pickupKm = pickupKm;
                    this.tripMin = tripMin;
                    this.tripKm = tripKm;
                }

                public boolean isUsable() {
                    return fare > 0 && pickupMin >= 0 && pickupKm >= 0 && tripMin > 0 && tripKm > 0;
                }
            }

            public static final class ParseResult {
                public final Offer offer;
                public final String diagnostic;
                public final boolean candidate;
                public final String excerpt;

                private ParseResult(Offer offer, String diagnostic, boolean candidate, String excerpt) {
                    this.offer = offer;
                    this.diagnostic = diagnostic;
                    this.candidate = candidate;
                    this.excerpt = excerpt;
                }

                static ParseResult success(Offer offer, String excerpt) {
                    return new ParseResult(offer, "oferta completa", true, excerpt);
                }

                static ParseResult failure(String diagnostic, boolean candidate, String excerpt) {
                    return new ParseResult(null, diagnostic, candidate, excerpt);
                }
            }
    }

}
