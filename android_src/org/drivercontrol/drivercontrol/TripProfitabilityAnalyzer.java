package org.drivercontrol.drivercontrol;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * Motor de conveniencia de ofertas. Costos estimados, no cobros reales de Uber.
 * Nunca considera rentable una lectura numérica inválida.
 */
public final class TripProfitabilityAnalyzer {
    public enum Verdict { ACCEPT, REVIEW, DISCARD }

    public static final class Result {
        public final double liters, fuelCost, wearCost, netProfit, perHour, perKm, score;
        public final Verdict verdict;

        Result(double liters, double fuelCost, double wearCost, double netProfit,
               double perHour, double perKm, double score, Verdict verdict) {
            this.liters = liters;
            this.fuelCost = fuelCost;
            this.wearCost = wearCost;
            this.netProfit = netProfit;
            this.perHour = perHour;
            this.perKm = perKm;
            this.score = score;
            this.verdict = verdict;
        }
    }

    private TripProfitabilityAnalyzer() {}

    private static boolean positive(double n) {
        return !Double.isNaN(n) && !Double.isInfinite(n) && n > 0;
    }
    private static boolean nonnegative(double n) {
        return !Double.isNaN(n) && !Double.isInfinite(n) && n >= 0;
    }
    private static double clamp(double v, double min, double max) {
        return Math.max(min, Math.min(max, v));
    }

    public static Result analyze(Context context, double fare, double pickupMin,
                                 double pickupKm, double tripMin, double tripKm) {
        SharedPreferences p = context.getSharedPreferences(
                "driver_control_overlay", Context.MODE_PRIVATE);
        double consumption = p.getFloat("fuel_consumption", 8.0f);
        double fuelPrice = p.getFloat("fuel_price", 2048.0f);
        double wearPerKm = p.getFloat("wear_per_km", 0.0f);
        double minHourly = p.getFloat("min_hourly", 15000.0f);
        double minPerKm = p.getFloat("min_per_km", 300.0f);
        double maxPickupKm = p.getFloat("max_pickup_km", 3.0f);
        int fatigueRisk = p.getInt("fatigue_risk", 0);
        boolean paused = p.getBoolean("driver_paused", false);

        boolean valid = positive(fare) && nonnegative(pickupMin) && nonnegative(pickupKm)
                && positive(tripMin) && positive(tripKm)
                && positive(consumption) && positive(fuelPrice)
                && nonnegative(wearPerKm) && positive(minHourly) && positive(minPerKm)
                && nonnegative(maxPickupKm);
        if (!valid) {
            return new Result(0, 0, 0, 0, 0, 0, 0, Verdict.DISCARD);
        }

        double totalMin = pickupMin + tripMin;
        double totalKm = pickupKm + tripKm;
        if (!positive(totalMin) || !positive(totalKm)) {
            return new Result(0, 0, 0, 0, 0, 0, 0, Verdict.DISCARD);
        }
        double liters = totalKm * consumption / 100.0;
        double fuelCost = liters * fuelPrice;
        double wearCost = totalKm * wearPerKm;
        double net = fare - fuelCost - wearCost;
        double hourly = net * 60.0 / totalMin;
        double perKm = net / totalKm;
        if (!nonnegative(liters) || !nonnegative(fuelCost) || !nonnegative(wearCost)
                || !Double.isFinite(net) || !Double.isFinite(hourly) || !Double.isFinite(perKm)) {
            return new Result(0, 0, 0, 0, 0, 0, 0, Verdict.DISCARD);
        }

        double score = 50;
        score += clamp((hourly / minHourly - 1) * 35, -25, 25);
        score += clamp((perKm / minPerKm - 1) * 30, -20, 20);
        score += pickupKm <= maxPickupKm
                ? 10 : -Math.min(20, (pickupKm - maxPickupKm) * 5);
        score = clamp(score, 0, 100);

        // Verde exige cumplir ambos mínimos y un acercamiento razonable.
        // Amarillo cubre viajes que requieren revisar, incluso si el puntaje es alto.
        Verdict verdict;
        if (paused || fatigueRisk >= 2 || net <= 0 || hourly < minHourly * 0.70
                || perKm < minPerKm * 0.70 || score < 45) {
            verdict = Verdict.DISCARD;
        } else if (fatigueRisk == 1 || hourly < minHourly || perKm < minPerKm
                || pickupKm > maxPickupKm || score < 75) {
            verdict = Verdict.REVIEW;
        } else {
            verdict = Verdict.ACCEPT;
        }
        return new Result(liters, fuelCost, wearCost, net, hourly, perKm, score, verdict);
    }
}
