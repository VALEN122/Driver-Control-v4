package org.drivercontrol.drivercontrol;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Context;
import android.content.BroadcastReceiver;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.drawable.GradientDrawable;
import android.os.SystemClock;
import android.os.Build;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.text.NumberFormat;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Driver Control: lectura local de ofertas visibles en Uber Driver.
 * No hace clicks, no acepta/rechaza viajes y no persiste nombres/direcciones.
 */
public class UberOfferAccessibilityService extends AccessibilityService {
    private static final String UBER_PACKAGE = "com.ubercab.driver";
    private static final long MIN_REFRESH_MS = 300L;

    private WindowManager windowManager;
    private LinearLayout overlay;
    private TextView verdictView;
    private TextView headlineView;
    private TextView metricsView;
    private long lastRefresh = 0L;
    private String lastSignature = "";
    public static final String ACTION_OCR_TEXT = "org.drivercontrol.drivercontrol.OCR_TEXT";
    public static final String EXTRA_OCR_TEXT = "ocr_text";
    private boolean receiverRegistered = false;
    private final BroadcastReceiver ocrReceiver = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) {
            if (intent == null || !ACTION_OCR_TEXT.equals(intent.getAction())) return;
            String raw = intent.getStringExtra(EXTRA_OCR_TEXT);
            if (raw == null || raw.trim().isEmpty()) return;
            List<String> lines = new ArrayList<>();
            for (String line : raw.split("\\n")) if (!line.trim().isEmpty()) lines.add(line.trim());
            Offer offer = parseOffer(lines);
            if (offer != null && offer.isUsable()) {
                Analysis analysis = analyze(offer);
                String signature = offer.fare + "|" + offer.pickupMin + "|" + offer.pickupKm +
                        "|" + offer.tripMin + "|" + offer.tripKm;
                if (!signature.equals(lastSignature) || overlay == null) {
                    lastSignature = signature;
                    showOrUpdateOverlay(analysis);
                }
            }
        }
    };

    // $ 4.800 | $4.800,50 | ARS 4.800
    private static final Pattern MONEY = Pattern.compile(
            "(?i)(?<!\\+)(?:ARS\\s*|\\$\\s*)([0-9OIl|][0-9OIl|., ]*)");
    private static final Pattern MINUTES = Pattern.compile(
            "(?i)([0-9]+(?:[.,][0-9]+)?)\\s*(?:min|minuto|minutos)\\b");
    private static final Pattern KM = Pattern.compile(
            "(?i)([0-9]+(?:[.,][0-9]+)?)\\s*km\\b");
    private static final Pattern PAIRED = Pattern.compile(
            "(?i)([0-9]+(?:[.,][0-9]+)?)\\s*(?:min|minuto|minutos)\\b.{0,40}?([0-9]+(?:[.,][0-9]+)?)\\s*km\\b");

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        AccessibilityServiceInfo info = getServiceInfo();
        if (info != null) {
            info.packageNames = new String[]{UBER_PACKAGE};
            info.eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED |
                    AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED;
            info.feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC;
            info.notificationTimeout = 80;
            info.flags |= AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS |
                    AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS |
                    AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS;
            setServiceInfo(info);
        }
        windowManager = (WindowManager) getSystemService(Context.WINDOW_SERVICE);
        IntentFilter filter = new IntentFilter(ACTION_OCR_TEXT);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(ocrReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        else registerReceiver(ocrReceiver, filter);
        receiverRegistered = true;
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null || event.getPackageName() == null) {
            hideOverlay();
            return;
        }
        String pkg = event.getPackageName().toString();
        if (!UBER_PACKAGE.equals(pkg)) {
            hideOverlay();
            return;
        }
        long now = SystemClock.elapsedRealtime();
        if (now - lastRefresh < MIN_REFRESH_MS) return;
        lastRefresh = now;

        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return;
        try {
            List<String> visible = new ArrayList<>();
            collectVisibleText(root, visible, new HashSet<String>());
            Offer offer = parseOffer(visible);
            if (offer != null && offer.isUsable()) {
                Analysis a = analyze(offer);
                String signature = offer.fare + "|" + offer.pickupMin + "|" + offer.pickupKm +
                        "|" + offer.tripMin + "|" + offer.tripKm;
                if (!signature.equals(lastSignature) || overlay == null) {
                    lastSignature = signature;
                    showOrUpdateOverlay(a);
                }
            } else {
                hideOverlay();
            }
        } finally {
            root.recycle();
        }
    }

    @Override
    public void onInterrupt() {
        hideOverlay();
    }

    @Override
    public void onDestroy() {
        hideOverlay();
        if (receiverRegistered) {
            try { unregisterReceiver(ocrReceiver); } catch (Exception ignored) {}
            receiverRegistered = false;
        }
        super.onDestroy();
    }

    private void collectVisibleText(AccessibilityNodeInfo node, List<String> out, Set<String> seen) {
        if (node == null || !node.isVisibleToUser()) return;
        CharSequence text = node.getText();
        CharSequence desc = node.getContentDescription();
        addText(text, out, seen);
        addText(desc, out, seen);
        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                collectVisibleText(child, out, seen);
                child.recycle();
            }
        }
    }

    private void addText(CharSequence cs, List<String> out, Set<String> seen) {
        if (cs == null) return;
        String s = cs.toString().trim();
        if (s.isEmpty() || s.length() > 240) return;
        if (seen.add(s)) out.add(s);
    }

    private Offer parseOffer(List<String> lines) {
        if (lines.isEmpty()) return null;
        String joined = join(lines, " | ");

        // Una solicitud de viaje normalmente muestra un importe y al menos dos métricas temporales/distancia.
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
            } else {
                return null;
            }
        }

        // Evita reaccionar a cualquier pantalla de Uber que no parezca una oferta nueva.
        String lower = joined.toLowerCase(Locale.ROOT);
        boolean offerHint = lower.contains("viaje") || lower.contains("solicitud") ||
                lower.contains("acept") || lower.contains("uberx") || lower.contains("comfort") ||
                lower.contains("para llegar") || lower.contains("recoger");
        if (!offerHint) return null;

        return new Offer(fare, pickupMin, pickupKm, tripMin, tripKm);
    }

    private Analysis analyze(Offer o) {
        SharedPreferences p = getSharedPreferences("driver_control_overlay", MODE_PRIVATE);
        double consumption = p.getFloat("fuel_consumption", 8.0f);
        double fuelPrice = p.getFloat("fuel_price", 2048.0f);
        double minHourly = p.getFloat("min_hourly", 15000.0f);
        double minPerKm = p.getFloat("min_per_km", 500.0f);
        double maxPickupKm = p.getFloat("max_pickup_km", 3.0f);

        double totalMin = Math.max(0.1, o.pickupMin + o.tripMin);
        double totalKm = Math.max(0.1, o.pickupKm + o.tripKm);
        double liters = totalKm * consumption / 100.0;
        double fuelCost = liters * fuelPrice;
        double net = Math.max(0.0, o.fare - fuelCost);
        double hourly = net / totalMin * 60.0;
        double perKm = net / totalKm;

        double score = 50.0;
        score += clamp((hourly / minHourly - 1.0) * 35.0, -25, 25);
        score += clamp((perKm / minPerKm - 1.0) * 30.0, -20, 20);
        score += o.pickupKm <= maxPickupKm ? 10 : -Math.min(20, (o.pickupKm - maxPickupKm) * 5);
        score = clamp(score, 0, 100);

        String verdict;
        int accent;
        if (score >= 75) { verdict = "CONVIENE"; accent = Color.rgb(26, 190, 109); }
        else if (score >= 55) { verdict = "DUDOSO"; accent = Color.rgb(230, 170, 35); }
        else { verdict = "NO CONVIENE"; accent = Color.rgb(225, 65, 75); }

        return new Analysis(o, liters, fuelCost, net, hourly, perKm, score, verdict, accent);
    }

    private void showOrUpdateOverlay(Analysis a) {
        if (windowManager == null) return;
        if (overlay == null) createOverlay();
        if (overlay == null) return;

        verdictView.setText(a.verdict + "  " + Math.round(a.score) + "/100");
        verdictView.setTextColor(a.accentColor);
        headlineView.setText(money(a.offer.fare) + " · " + fmt1(a.offer.pickupKm + a.offer.tripKm) +
                " km · " + Math.round(a.offer.pickupMin + a.offer.tripMin) + " min");
        metricsView.setText(money(a.hourly) + "/h  ·  " + money(a.perKm) + "/km\n" +
                "Nafta " + money(a.fuelCost) + " · Neto " + money(a.net));
        if (overlay.getParent() == null) {
            try { windowManager.addView(overlay, buildLayoutParams()); }
            catch (Exception ignored) { overlay = null; }
        }
    }

    private void createOverlay() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(12);
        box.setPadding(pad, dp(9), pad, dp(9));
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.argb(238, 17, 24, 32));
        bg.setCornerRadius(dp(16));
        bg.setStroke(dp(1), Color.argb(160, 130, 145, 160));
        box.setBackground(bg);
        box.setElevation(dp(8));

        verdictView = textView(15, true, Color.WHITE);
        headlineView = textView(14, true, Color.WHITE);
        metricsView = textView(12, false, Color.rgb(210, 220, 230));
        box.addView(verdictView);
        box.addView(headlineView);
        box.addView(metricsView);
        box.setOnClickListener(v -> {
            if (metricsView != null) {
                metricsView.setVisibility(metricsView.getVisibility() == View.VISIBLE ? View.GONE : View.VISIBLE);
            }
        });
        overlay = box;
    }

    private WindowManager.LayoutParams buildLayoutParams() {
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE |
                        WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL |
                        WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
        lp.y = dp(96);
        return lp;
    }

    private TextView textView(int sp, boolean bold, int color) {
        TextView t = new TextView(this);
        t.setTextSize(sp);
        t.setTextColor(color);
        if (bold) t.setTypeface(t.getTypeface(), android.graphics.Typeface.BOLD);
        t.setPadding(0, dp(1), 0, dp(1));
        return t;
    }

    private void hideOverlay() {
        if (overlay != null && windowManager != null && overlay.getParent() != null) {
            try { windowManager.removeView(overlay); } catch (Exception ignored) {}
        }
        lastSignature = "";
    }

    private static List<Double> findNumbers(Pattern p, String text, int group) {
        List<Double> out = new ArrayList<>();
        Matcher m = p.matcher(text);
        while (m.find() && out.size() < 10) {
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
        } catch (Exception e) {
            return -1;
        }
    }

    private String money(double v) {
        NumberFormat nf = NumberFormat.getNumberInstance(new Locale("es", "AR"));
        nf.setMaximumFractionDigits(0);
        return "$" + nf.format(Math.max(0, v));
    }

    private String fmt1(double v) {
        return String.format(new Locale("es", "AR"), "%.1f", v);
    }

    private int dp(int value) {
        float density = getResources().getDisplayMetrics().density;
        return Math.round(value * density);
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
