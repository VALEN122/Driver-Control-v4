package org.drivercontrol.drivercontrol;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * Motor financiero puro y verificable. La base SQLite de Kivy sincroniza sus
 * parámetros hacia estas preferencias; el visor nunca abre ni bloquea la base.
 */
public final class TripProfitabilityAnalyzer {
    public enum Verdict { ACCEPT, REVIEW, DISCARD }

    public static final class Result {
        public final double liters;
        public final double fuelCost;
        public final double netProfit;
        public final double perHour;
        public final double perKm;
        public final double score;
        public final Verdict verdict;

        Result(double liters, double fuelCost, double netProfit, double perHour,
               double perKm, double score, Verdict verdict) {
            this.liters = liters;
            this.fuelCost = fuelCost;
            this.netProfit = netProfit;
            this.perHour = perHour;
            this.perKm = perKm;
            this.score = score;
            this.verdict = verdict;
        }
    }

    private TripProfitabilityAnalyzer() {}

    public static Result analyze(Context context, double fare, double pickupMin,
                                 double pickupKm, double tripMin, double tripKm) {
        SharedPreferences p = context.getSharedPreferences(
                "driver_control_overlay", Context.MODE_PRIVATE);
        double consumption = p.getFloat("fuel_consumption", 8.0f);
        double fuelPrice = p.getFloat("fuel_price", 2048.0f);
        double minHourly = p.getFloat("min_hourly", 15000.0f);
        double minPerKm = p.getFloat("min_per_km", 300.0f);
        double maxPickupKm = p.getFloat("max_pickup_km", 3.0f);
        int fatigueRisk = p.getInt("fatigue_risk", 0);
        boolean paused = p.getBoolean("driver_paused", false);

        double totalMin = Math.max(0.1, pickupMin + tripMin);
        double totalKm = Math.max(0.1, pickupKm + tripKm);
        double liters = totalKm * consumption / 100.0;
        double fuelCost = liters * fuelPrice;
        double net = fare - fuelCost;
        double hourly = net / totalMin * 60.0;
        double perKm = net / totalKm;

        double score = 50.0;
        score += clamp((hourly / Math.max(1.0, minHourly) - 1.0) * 35.0, -25, 25);
        score += clamp((perKm / Math.max(1.0, minPerKm) - 1.0) * 30.0, -20, 20);
        score += pickupKm <= maxPickupKm
                ? 10 : -Math.min(20, (pickupKm - maxPickupKm) * 5);
        score = clamp(score, 0, 100);

        Verdict verdict;
        if (paused || fatigueRisk >= 2 || perKm < minPerKm || score < 55) {
            verdict = Verdict.DISCARD;
        } else if (fatigueRisk == 1) {
            verdict = Verdict.REVIEW;
        } else if (score >= 75) verdict = Verdict.ACCEPT;
        else verdict = Verdict.REVIEW;
        return new Result(liters, fuelCost, net, hourly, perKm, score, verdict);
    }

    private static double clamp(double value, double min, double max) {
        return Math.max(min, Math.min(max, value));
    }
}
