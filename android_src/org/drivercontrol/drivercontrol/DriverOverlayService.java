package org.drivercontrol.drivercontrol;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
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
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Flotante independiente de Accesibilidad.
 * Recibe texto desde Accesibilidad u OCR, analiza ofertas y además ofrece
 * una calculadora de vuelto rápida que funciona aunque Accesibilidad esté apagada.
 */
public class DriverOverlayService extends Service {
    public static final String ACTION_START = "org.drivercontrol.drivercontrol.OVERLAY_START";
    public static final String ACTION_STOP = "org.drivercontrol.drivercontrol.OVERLAY_STOP";
    public static final String ACTION_SOURCE_TEXT = "org.drivercontrol.drivercontrol.SOURCE_TEXT";
    public static final String EXTRA_SOURCE_TEXT = "source_text";
    public static final String EXTRA_SOURCE_KIND = "source_kind";

    private static final String CHANNEL = "driver_control_overlay";
    private static final int NOTIFICATION_ID = 61;
    private static final long OFFER_VISIBLE_MS = 6500L;

    private static final Pattern MONEY = Pattern.compile(
            "(?i)(?<!\\+)(?:ARS\\s*|\\$\\s*)([0-9OIl|][0-9OIl|., ]*)");
    private static final Pattern MINUTES = Pattern.compile(
            "(?i)([0-9]+(?:[.,][0-9]+)?)\\s*(?:min\\.?|minuto(?:s)?)\\b");
    private static final Pattern KM = Pattern.compile(
            "(?i)([0-9]+(?:[.,][0-9]+)?)\\s*(?:km|kil[oó]metro(?:s)?)\\b");
    private static final Pattern PAIRED = Pattern.compile(
            "(?i)([0-9]+(?:[.,][0-9]+)?)\\s*(?:min\\.?|minuto(?:s)?)\\b.{0,80}?([0-9]+(?:[.,][0-9]+)?)\\s*(?:km|kil[oó]metro(?:s)?)\\b");

    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private WindowManager windowManager;
    private LinearLayout tripOverlay;
    private TextView verdictView;
    private TextView headlineView;
    private TextView metricsView;
    private TextView changeBubble;
    private LinearLayout changePanel;
    private String lastSignature = "";
    private long lastOfferAt = 0L;
    private boolean receiverRegistered = false;

    private final Runnable hideStaleOffer = new Runnable() {
        @Override public void run() {
            long age = android.os.SystemClock.elapsedRealtime() - lastOfferAt;
            if (lastOfferAt > 0 && age >= OFFER_VISIBLE_MS) hideTripOverlay();
        }
    };

    private final BroadcastReceiver sourceReceiver = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) {
            if (intent == null || !ACTION_SOURCE_TEXT.equals(intent.getAction())) return;
            String raw = intent.getStringExtra(EXTRA_SOURCE_TEXT);
            if (raw == null || raw.trim().isEmpty()) return;
            List<String> lines = new ArrayList<>();
            for (String line : raw.split("\\n")) {
                String cleaned = line.trim();
                if (!cleaned.isEmpty()) lines.add(cleaned);
            }
            Offer offer = parseOffer(lines);
            if (offer == null || !offer.isUsable()) return;

            Analysis analysis = analyze(offer);
            String signature = offer.fare + "|" + offer.pickupMin + "|" + offer.pickupKm +
                    "|" + offer.tripMin + "|" + offer.tripKm;
            getSharedPreferences("driver_control_overlay", MODE_PRIVATE).edit()
                    .putFloat("last_offer_fare", (float) offer.fare)
                    .apply();
            lastOfferAt = android.os.SystemClock.elapsedRealtime();
            mainHandler.removeCallbacks(hideStaleOffer);
            mainHandler.postDelayed(hideStaleOffer, OFFER_VISIBLE_MS + 100L);
            if (!signature.equals(lastSignature) || tripOverlay == null) {
                lastSignature = signature;
                showOrUpdateTripOverlay(analysis);
            }
        }
    };

    @Override public void onCreate() {
        super.onCreate();
        windowManager = (WindowManager) getSystemService(WINDOW_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL, "Driver Control flotante", NotificationManager.IMPORTANCE_LOW);
            channel.setDescription("Asistente de viajes y vuelto rápido");
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }
        IntentFilter filter = new IntentFilter(ACTION_SOURCE_TEXT);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(sourceReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(sourceReceiver, filter);
        receiverRegistered = true;
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }
        startForeground(NOTIFICATION_ID, buildNotification());
        if (Settings.canDrawOverlays(this)) showChangeBubble();
        return START_STICKY;
    }

    private Notification buildNotification() {
        PendingIntent stop = PendingIntent.getService(this, 62,
                new Intent(this, DriverOverlayService.class).setAction(ACTION_STOP),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
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

        verdictView.setText(a.verdict + "  " + Math.round(a.score) + "/100");
        verdictView.setTextColor(a.accentColor);
        headlineView.setText(money(a.offer.fare) + " · " + fmt1(a.offer.pickupKm + a.offer.tripKm) +
                " km · " + Math.round(a.offer.pickupMin + a.offer.tripMin) + " min");
        metricsView.setText(money(a.hourly) + "/h  ·  " + money(a.perKm) + "/km\n" +
                "Nafta " + money(a.fuelCost) + " · Neto " + money(a.net));
        if (tripOverlay.getParent() == null) {
            try { windowManager.addView(tripOverlay, tripLayoutParams()); }
            catch (Exception ignored) { tripOverlay = null; }
        }
    }

    private void createTripOverlay() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(12), dp(9), dp(12), dp(9));
        GradientDrawable bg = rounded(Color.argb(242, 17, 24, 32), 16, Color.argb(170, 130, 145, 160));
        box.setBackground(bg);
        box.setElevation(dp(8));

        verdictView = textView(16, true, Color.WHITE);
        headlineView = textView(14, true, Color.WHITE);
        metricsView = textView(12, false, Color.rgb(210, 220, 230));
        box.addView(verdictView);
        box.addView(headlineView);
        box.addView(metricsView);
        box.setOnClickListener(v -> metricsView.setVisibility(
                metricsView.getVisibility() == View.VISIBLE ? View.GONE : View.VISIBLE));
        tripOverlay = box;
    }

    private WindowManager.LayoutParams tripLayoutParams() {
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE |
                        WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL |
                        WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
        lp.y = dp(90);
        return lp;
    }

    private void hideTripOverlay() {
        if (tripOverlay != null && windowManager != null && tripOverlay.getParent() != null) {
            try { windowManager.removeView(tripOverlay); } catch (Exception ignored) {}
        }
        lastSignature = "";
        lastOfferAt = 0L;
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
            GradientDrawable bg = rounded(Color.rgb(0, 153, 204), 28, Color.WHITE);
            bubble.setBackground(bg);
            bubble.setElevation(dp(10));
            bubble.setOnClickListener(v -> showChangePanel());
            changeBubble = bubble;
        }
        if (changeBubble.getParent() == null) {
            try { windowManager.addView(changeBubble, bubbleLayoutParams()); }
            catch (Exception ignored) { changeBubble = null; }
        }
    }

    private WindowManager.LayoutParams bubbleLayoutParams() {
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                dp(58), dp(58), WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE |
                        WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL |
                        WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
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
        panel.setBackground(rounded(Color.argb(250, 17, 24, 32), 18, Color.argb(190, 130, 145, 160)));
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
        };
        q1.setOnClickListener(quickListener);
        q2.setOnClickListener(quickListener);
        q3.setOnClickListener(quickListener);

        Runnable update = () -> {
            double fareValue = parseInput(fare.getText().toString());
            double receivedValue = parseInput(received.getText().toString());
            double[] suggested = suggestedAmounts(fareValue);
            quickValues[0] = suggested[0]; quickValues[1] = suggested[1]; quickValues[2] = suggested[2];
            q1.setText(money(suggested[0])); q2.setText(money(suggested[1])); q3.setText(money(suggested[2]));
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
            if (lastFare <= 0) fare.requestFocus(); else received.requestFocus();
            EditText target = lastFare <= 0 ? fare : received;
            target.postDelayed(() -> {
                InputMethodManager imm = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
                if (imm != null) imm.showSoftInput(target, InputMethodManager.SHOW_IMPLICIT);
            }, 180L);
        } catch (Exception ignored) {
            changePanel = null;
            showChangeBubble();
        }
    }

    private WindowManager.LayoutParams changePanelLayoutParams() {
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                Math.min(dp(360), getResources().getDisplayMetrics().widthPixels - dp(24)),
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL |
                        WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
        lp.y = dp(120);
        lp.softInputMode = WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE;
        return lp;
    }

    private void closeChangePanel() {
        if (changePanel != null && windowManager != null && changePanel.getParent() != null) {
            try { windowManager.removeView(changePanel); } catch (Exception ignored) {}
        }
        changePanel = null;
        showChangeBubble();
    }

    private void removeChangeBubble() {
        if (changeBubble != null && windowManager != null && changeBubble.getParent() != null) {
            try { windowManager.removeView(changeBubble); } catch (Exception ignored) {}
        }
    }

    private EditText numberField(String hint) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setTextColor(Color.WHITE);
        e.setHintTextColor(Color.rgb(160, 175, 190));
        e.setTextSize(19);
        e.setSingleLine(true);
        e.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        e.setPadding(dp(10), dp(4), dp(10), dp(4));
        GradientDrawable bg = rounded(Color.rgb(30, 40, 52), 12, Color.rgb(95, 115, 135));
        e.setBackground(bg);
        return e;
    }

    private Button button(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setTextSize(13);
        b.setTextColor(Color.WHITE);
        b.setAllCaps(false);
        b.setBackground(rounded(Color.rgb(40, 54, 68), 10, Color.rgb(85, 105, 125)));
        return b;
    }

    private TextView textView(int sp, boolean bold, int color) {
        TextView t = new TextView(this);
        t.setTextSize(sp);
        t.setTextColor(color);
        if (bold) t.setTypeface(t.getTypeface(), android.graphics.Typeface.BOLD);
        t.setPadding(0, dp(2), 0, dp(2));
        return t;
    }

    private GradientDrawable rounded(int color, int radiusDp, int strokeColor) {
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(color);
        bg.setCornerRadius(dp(radiusDp));
        bg.setStroke(dp(1), strokeColor);
        return bg;
    }

    private double[] suggestedAmounts(double fare) {
        double[] steps = {1000, 2000, 5000, 10000, 20000, 50000, 100000, 200000};
        double[] out = new double[3];
        int idx = 0;
        for (double step : steps) {
            if (step >= Math.max(1, fare) && idx < 3) out[idx++] = step;
        }
        double base = idx > 0 ? out[idx - 1] : Math.max(1000, Math.ceil(fare / 10000.0) * 10000.0);
        while (idx < 3) { base *= 2; out[idx++] = base; }
        return out;
    }

    private Offer parseOffer(List<String> lines) {
        if (lines.isEmpty()) return null;
        String joined = join(lines, " | ");
        List<Double> moneyValues = findNumbers(MONEY, joined, 1);
        if (moneyValues.isEmpty()) return null;
        double fare = 0.0;
        for (double v : moneyValues) if (v >= 100.0 && v > fare) fare = v;
        if (fare < 100.0) return null;

        List<double[]> pairs = new ArrayList<>();
        Matcher pm = PAIRED.matcher(joined);
        while (pm.find() && pairs.size() < 4) {
            pairs.add(new double[]{parseLocaleNumber(pm.group(1)), parseLocaleNumber(pm.group(2))});
        }

        double pickupMin = 0, pickupKm = 0, tripMin = 0, tripKm = 0;
        if (pairs.size() >= 2) {
            pickupMin = pairs.get(0)[0]; pickupKm = pairs.get(0)[1];
            tripMin = pairs.get(1)[0]; tripKm = pairs.get(1)[1];
        } else {
            List<Double> mins = findNumbers(MINUTES, joined, 1);
            List<Double> kms = findNumbers(KM, joined, 1);
            if (mins.size() >= 2 && kms.size() >= 2) {
                pickupMin = mins.get(0); pickupKm = kms.get(0);
                tripMin = mins.get(1); tripKm = kms.get(1);
            } else return null;
        }

        String lower = joined.toLowerCase(Locale.ROOT);
        boolean offerHint = lower.contains("viaje") || lower.contains("solicitud") ||
                lower.contains("acept") || lower.contains("uberx") || lower.contains("comfort") ||
                lower.contains("para llegar") || lower.contains("recoger") ||
                lower.contains("destino") || lower.contains("incluye") || lower.contains("exclusivo");
        if (!offerHint) return null;
        return new Offer(fare, pickupMin, pickupKm, tripMin, tripKm);
    }

    private Analysis analyze(Offer o) {
        SharedPreferences p = getSharedPreferences("driver_control_overlay", MODE_PRIVATE);
        double consumption = p.getFloat("fuel_consumption", 8.0f);
        double fuelPrice = p.getFloat("fuel_price", 2048.0f);
        double minHourly = p.getFloat("min_hourly", 15000.0f);
        double minPerKm = p.getFloat("min_per_km", 300.0f);
        double maxPickupKm = p.getFloat("max_pickup_km", 3.0f);

        double totalMin = Math.max(0.1, o.pickupMin + o.tripMin);
        double totalKm = Math.max(0.1, o.pickupKm + o.tripKm);
        double liters = totalKm * consumption / 100.0;
        double fuelCost = liters * fuelPrice;
        double net = Math.max(0.0, o.fare - fuelCost);
        double hourly = net / totalMin * 60.0;
        double perKm = net / totalKm;

        double score = 50.0;
        score += clamp((hourly / Math.max(1.0, minHourly) - 1.0) * 35.0, -25, 25);
        score += clamp((perKm / Math.max(1.0, minPerKm) - 1.0) * 30.0, -20, 20);
        score += o.pickupKm <= maxPickupKm ? 10 : -Math.min(20, (o.pickupKm - maxPickupKm) * 5);
        score = clamp(score, 0, 100);

        String verdict;
        int accent;
        if (perKm < minPerKm) { verdict = "NO CONVIENE"; accent = Color.rgb(225, 65, 75); }
        else if (score >= 75) { verdict = "CONVIENE"; accent = Color.rgb(26, 190, 109); }
        else if (score >= 55) { verdict = "DUDOSO"; accent = Color.rgb(230, 170, 35); }
        else { verdict = "NO CONVIENE"; accent = Color.rgb(225, 65, 75); }
        return new Analysis(o, liters, fuelCost, net, hourly, perKm, score, verdict, accent);
    }

    private static List<Double> findNumbers(Pattern p, String text, int group) {
        List<Double> out = new ArrayList<>();
        Matcher m = p.matcher(text);
        while (m.find() && out.size() < 12) {
            double v = parseLocaleNumber(m.group(group));
            if (v >= 0) out.add(v);
        }
        return out;
    }

    private static double parseLocaleNumber(String raw) {
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
        } catch (Exception e) { return -1; }
    }

    private static double parseInput(String raw) {
        if (raw == null || raw.trim().isEmpty()) return 0.0;
        double parsed = parseLocaleNumber(raw);
        return parsed < 0 ? 0.0 : parsed;
    }

    private String money(double v) {
        NumberFormat nf = NumberFormat.getNumberInstance(new Locale("es", "AR"));
        nf.setMaximumFractionDigits(0);
        return "$" + nf.format(Math.max(0, v));
    }

    private String plainNumber(double v) {
        return String.valueOf(Math.round(Math.max(0, v)));
    }

    private String fmt1(double v) {
        return String.format(new Locale("es", "AR"), "%.1f", v);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private static double clamp(double v, double min, double max) {
        return Math.max(min, Math.min(max, v));
    }

    private static String join(List<String> values, String sep) {
        StringBuilder b = new StringBuilder();
        for (String v : values) {
            if (b.length() > 0) b.append(sep);
            b.append(v);
        }
        return b.toString();
    }

    @Override public void onDestroy() {
        mainHandler.removeCallbacks(hideStaleOffer);
        hideTripOverlay();
        if (changePanel != null && windowManager != null && changePanel.getParent() != null) {
            try { windowManager.removeView(changePanel); } catch (Exception ignored) {}
        }
        removeChangeBubble();
        if (receiverRegistered) {
            try { unregisterReceiver(sourceReceiver); } catch (Exception ignored) {}
            receiverRegistered = false;
        }
        stopForeground(true);
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    private static class Offer {
        final double fare, pickupMin, pickupKm, tripMin, tripKm;
        Offer(double fare, double pickupMin, double pickupKm, double tripMin, double tripKm) {
            this.fare = fare; this.pickupMin = pickupMin; this.pickupKm = pickupKm;
            this.tripMin = tripMin; this.tripKm = tripKm;
        }
        boolean isUsable() {
            return fare > 0 && pickupMin >= 0 && pickupKm >= 0 && tripMin > 0 && tripKm > 0;
        }
    }

    private static class Analysis {
        final Offer offer;
        final double liters, fuelCost, net, hourly, perKm, score;
        final String verdict;
        final int accentColor;
        Analysis(Offer offer, double liters, double fuelCost, double net, double hourly,
                 double perKm, double score, String verdict, int accentColor) {
            this.offer = offer; this.liters = liters; this.fuelCost = fuelCost; this.net = net;
            this.hourly = hourly; this.perKm = perKm; this.score = score;
            this.verdict = verdict; this.accentColor = accentColor;
        }
    }
}
