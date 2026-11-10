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
        public final double maintenanceCost;
        public final double operatingProfit;
        public final double netProfit;
        public final double perHour;
        public final double perKm;
        public final double score;
        public final Verdict verdict;

        Result(double liters, double fuelCost, double maintenanceCost, double operatingProfit,
               double netProfit, double perHour, double perKm, double score, Verdict verdict) {
            this.liters = liters;
            this.fuelCost = fuelCost;
            this.maintenanceCost = maintenanceCost;
            this.operatingProfit = operatingProfit;
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

        return analyze(fare, pickupMin, pickupKm, tripMin, tripKm, consumption,
                fuelPrice, minHourly, minPerKm, maxPickupKm,
                p.getFloat("maintenance_per_km", 0.0f), fatigueRisk, paused);
    }

    public static Result analyze(double fare, double pickupMin, double pickupKm,
            double tripMin, double tripKm, double consumption, double fuelPrice,
            double minHourly, double minPerKm, double maxPickupKm,
            double maintenancePerKm, int fatigueRisk, boolean paused) {
        double[] values = {fare, pickupMin, pickupKm, tripMin, tripKm, consumption,
                fuelPrice, minHourly, minPerKm, maxPickupKm, maintenancePerKm};
        for (double value : values) {
            if (!Double.isFinite(value) || value < 0) throw new IllegalArgumentException("Datos inválidos");
        }
        if (fare <= 0 || tripMin <= 0 || tripKm <= 0 || consumption <= 0
                || fuelPrice <= 0 || minHourly <= 0 || minPerKm <= 0 || maxPickupKm <= 0)
            throw new IllegalArgumentException("Datos incompletos");
        double totalMin = pickupMin + tripMin;
        double totalKm = pickupKm + tripKm;
        double liters = totalKm * consumption / 100.0;
        double fuelCost = liters * fuelPrice;
        double maintenanceCost = totalKm * maintenancePerKm;
        double net = fare - fuelCost;
        double operatingProfit = net - maintenanceCost;
        double hourly = operatingProfit / totalMin * 60.0;
        double perKm = operatingProfit / totalKm;

        double score = 50.0;
        score += clamp((hourly / Math.max(1.0, minHourly) - 1.0) * 35.0, -25, 25);
        score += clamp((perKm / Math.max(1.0, minPerKm) - 1.0) * 30.0, -20, 20);
        score += pickupKm <= maxPickupKm
                ? 10 : -Math.min(20, (pickupKm - maxPickupKm) * 5);
        score = clamp(score, 0, 100);

        Verdict verdict;
        // Los mínimos son condiciones obligatorias para recomendar una oferta.
        // La puntuación no puede convertir una oferta bajo el mínimo en verde.
        boolean hourlyOk = hourly >= minHourly;
        boolean kmOk = perKm >= minPerKm;
        if (paused || fatigueRisk >= 2 || operatingProfit <= 0 || (!hourlyOk && !kmOk)) {
            verdict = Verdict.DISCARD;
        } else if (!hourlyOk || !kmOk || pickupKm > maxPickupKm
                || fatigueRisk == 1 || score < 75) {
            verdict = Verdict.REVIEW;
        } else {
            verdict = Verdict.ACCEPT;
        }
        return new Result(liters, fuelCost, maintenanceCost, operatingProfit,
                net, hourly, perKm, score, verdict);
    }

    private static double clamp(double value, double min, double max) {
        return Math.max(min, Math.min(max, value));
    }
}
