package org.drivercontrol.drivercontrol;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Parser local tolerante de ofertas de Uber. */
public final class OfferParser {

    private OfferParser() {}

    private static final Pattern MONEY = Pattern.compile(
            "(?i)(?<!\\w)(?:ARS\\s*|\\$\\s*)([0-9OIl|]+(?:[.,][0-9OIl|]+)*(?:\\s[0-9OIl|]{3})*)");
    private static final Pattern UNIT_PRICE = Pattern.compile(
            "(?i)(?:/\\s*|por\\s+)(?:km|kil[oó]metros?|h|horas?|min(?:utos?)?)\\b");
    private static final String[] SUPPLEMENT_HINTS = {
            "inicio de viaje", "inicio del viaje", "por iniciar", "adicional", "extra",
            "bonific", "bono", "bonus", "incentivo", "propina", "peaje", "descuento"
    };
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
            return ParseResult.failure(fare == -2 ? "tarifa ambigua; confirmá el importe"
                    : "falta tarifa principal", candidate, excerpt(joined));
        }

        List<MetricPair> pairs = extractPairs(lines);
        MetricPair pickup = null;
        MetricPair trip = null;

        for (MetricPair p : pairs) {
            if (pickup == null && (containsAny(p.context, PICKUP_HINTS)
                    || p.context.matches("^a\\s*[0-9oil|].*"))) pickup = p;
            if (trip == null && p != pickup && containsAny(p.context, TRIP_HINTS)) trip = p;
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
        if (!offer.isUsable()) return ParseResult.failure("datos incompletos del viaje", true, excerpt(joined));
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
                    || lower.contains("nafta ") || lower.startsWith("deja ")
                    || lower.startsWith("tras costos ") || lower.startsWith("tras nafta ")
                    || lower.startsWith("reserva ") || lower.startsWith("factor:")
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
        double chosen = -1;
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i);
            // OCR may put the currency and its amount on consecutive lines.
            if (line.matches("(?i)\\+?\\s*(?:ARS|\\$)\\s*") && i + 1 < lines.size()
                    && lines.get(i + 1).matches("[0-9OIl|][0-9OIl|., ]*")) {
                line += " " + lines.get(++i);
            }
            Matcher m = MONEY.matcher(line);
            int previousEnd = 0;
            while (m.find()) {
                double value = parseLocaleNumber(m.group(1));
                String before = line.substring(previousEnd, m.start()).trim().toLowerCase(Locale.ROOT);
                previousEnd = m.end();
                Matcher next = MONEY.matcher(line);
                boolean hasNext = next.find(m.end());
                String after = line.substring(m.end(), hasNext ? next.start() : line.length())
                        .trim().toLowerCase(Locale.ROOT);
                if (value < 100 || value > 2_000_000) continue;
                String context = before + " " + after;
                // Read wrapped unit/supplement labels, stopping at another amount or leg.
                if (!hasNext) {
                    for (int j = i + 1; j < Math.min(lines.size(), i + 3); j++) {
                        String label = lines.get(j).toLowerCase(Locale.ROOT);
                        if (MONEY.matcher(label).find() || MINUTES.matcher(label).find()
                                || KM.matcher(label).find()
                                || label.matches("[+]?\\s*(?:ars|\\$)\\s*")) break;
                        context += " " + label;
                    }
                }
                if (i > 0) {
                    String label = lines.get(i - 1).toLowerCase(Locale.ROOT);
                    if (!MONEY.matcher(label).find() && !MINUTES.matcher(label).find()
                            && !KM.matcher(label).find()) context += " " + label;
                }
                if (before.endsWith("+") || before.endsWith("-")
                        || containsAny(context, SUPPLEMENT_HINTS)
                        || UNIT_PRICE.matcher(context).find()) continue;
                // Never guess the largest of competing prices. Duplicate OCR is harmless.
                if (chosen > 0 && Math.abs(chosen - value) > 0.01) return -2;
                chosen = value;
            }
        }
        return chosen;
    }

    /** A cloud result must not replace the visible principal fare with a supplement. */
    public static boolean matchesVisibleFare(String raw, double cloudFare) {
        if (raw == null || !Double.isFinite(cloudFare)) return false;
        double visibleFare = chooseFare(sanitizeLines(raw));
        return visibleFare >= 100 && Math.abs(visibleFare - cloudFare) <= 0.01;
    }

    /** Remote interpretation may only confirm a complete, locally verified offer. */
    public static boolean matchesVisibleOffer(String raw, double fare, double pickupMin,
            double pickupKm, double tripMin, double tripKm) {
        Offer visible = parse(raw).offer;
        return visible != null && visible.isUsable()
                && Math.abs(visible.fare - fare) <= 0.01
                && Math.abs(visible.pickupMin - pickupMin) <= 0.01
                && Math.abs(visible.pickupKm - pickupKm) <= 0.01
                && Math.abs(visible.tripMin - tripMin) <= 0.01
                && Math.abs(visible.tripKm - tripKm) <= 0.01;
    }

    private static List<MetricPair> extractPairs(List<String> lines) {
        List<MetricPair> out = new ArrayList<>();
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i);
            // Primero se intenta la línea aislada para no mezclar pickup y viaje contiguos.
            MetricPair p = matchPair(line);
            boolean metricLine = MINUTES.matcher(line).find() || KM.matcher(line).find();
            boolean legLabel = line.toLowerCase(Locale.ROOT).matches(
                    "(?:viaje|trayecto|recogida|pickup|para llegar)\\s*:?\\s*");
            if (p == null && i + 1 < lines.size() && (metricLine || legLabel)
                    && !MONEY.matcher(line).find()) {
                // OCR puede separar minutos y km de una misma fila en dos líneas.
                p = matchPair(line + " " + lines.get(i + 1));
                if (p != null) i++; // Consume both lines; never reuse the pickup distance.
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
            return Double.isFinite(fare) && Double.isFinite(pickupMin) && Double.isFinite(pickupKm)
                    && Double.isFinite(tripMin) && Double.isFinite(tripKm)
                    && fare > 0 && pickupMin >= 0 && pickupKm >= 0 && tripMin > 0 && tripKm > 0;
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
