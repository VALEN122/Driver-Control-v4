"""Run the production Java parser on transcribed real offers; no Android stubs."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "android_src/org/drivercontrol/drivercontrol/OfferParser.java"


def card(fare, pickup_min, pickup_km, trip_min, trip_km, bonus=None, rate=680):
    lines = ["Uber Priority" if bonus else "UberX", fare,
             f"ARS{rate}/km (estimado)", "Evaluación de seguridad", "4.95 (80)"]
    if bonus:
        lines.append(bonus)
    lines.extend([f"A {pickup_min} min ({pickup_km} km)", "Origen",
                  f"Viaje: {trip_min} min ({trip_km} km)", "Destino", "Me interesa"])
    return "\n".join(lines)


class OfferParserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="dc-offer-parser-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        harness = cls.root / "ParserHarness.java"
        harness.write_text('''
import java.nio.file.Files;
import java.nio.file.Path;
import org.drivercontrol.drivercontrol.OfferParser;
public final class ParserHarness {
    public static void main(String[] args) throws Exception {
        String raw = Files.readString(Path.of(args[0]));
        if (args.length > 2) {
            System.out.print(OfferParser.matchesVisibleOffer(raw, Double.parseDouble(args[1]),
                    Double.parseDouble(args[2]), Double.parseDouble(args[3]),
                    Double.parseDouble(args[4]), Double.parseDouble(args[5])));
            return;
        }
        if (args.length > 1) {
            System.out.print(OfferParser.matchesVisibleFare(raw, Double.parseDouble(args[1])));
            return;
        }
        OfferParser.ParseResult result = OfferParser.parse(raw);
        if (result.offer == null) { System.out.print("null"); return; }
        OfferParser.Offer o = result.offer;
        System.out.print("[" + o.fare + "," + o.pickupMin + "," + o.pickupKm
                + "," + o.tripMin + "," + o.tripKm + "]");
    }
}
''', encoding="utf-8")
        subprocess.run(["java", "-m", "jdk.compiler/com.sun.tools.javac.Main",
                        "-encoding", "UTF-8", "-d", str(cls.root),
                        str(SOURCE), str(harness)], check=True, capture_output=True, text=True)

    def parse(self, raw):
        path = self.root / "offer.txt"
        path.write_text(raw, encoding="utf-8")
        result = subprocess.run(["java", "-cp", str(self.root), "ParserHarness", str(path)],
                                check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def test_priority_5506_does_not_use_714_start_supplement(self):
        self.assertEqual([5506, 4, 1.2, 18, 6.9], self.parse(
            card("ARS5,506", 4, 1.2, 18, 6.9, "+ARS714.00 por inicio de viaje")))

    def test_priority_7507_does_not_use_945_start_supplement(self):
        self.assertEqual([7507, 5, 1.5, 28, 9.2], self.parse(
            card("ARS7,507", 5, 1.5, 28, 9.2, "+ARS945.00 por inicio de viaje", 702)))

    def test_uberx_3402_preserves_pickup_and_trip(self):
        self.assertEqual([3402, 5, 1.7, 9, 2.7], self.parse(card("ARS3,402", 5, 1.7, 9, 2.7, rate=773)))

    def test_uberx_6103_preserves_pickup_and_trip(self):
        self.assertEqual([6103, 2, .7, 24, 11.1], self.parse(card("ARS6,103", 2, .7, 24, 11.1, rate=517)))

    def test_currency_and_decimal_formats(self):
        for fare in ("ARS5,506.00", "ARS5.506,00", "$5.506", "ARS 5 506", "ARS\n5,506"):
            with self.subTest(fare=fare):
                self.assertEqual(5506, self.parse(card(fare, 4, 1.2, 18, 6.9,
                    "+ARS714.00 por inicio de viaje"))[0])

    def test_large_supplement_is_never_used_or_added(self):
        self.assertEqual(5506, self.parse(card("ARS5,506", 4, 1.2, 18, 6.9,
            "+ARS50,000.00 por inicio de viaje"))[0])

    def test_wrapped_supplement_does_not_change_fare_or_pickup(self):
        for bonus in ("+ARS714.00\npor inicio de viaje", "ARS714.00\npor inicio de viaje",
                      "Adicional\nARS714.00", "+\nARS714.00\npor inicio de viaje"):
            with self.subTest(bonus=bonus):
                self.assertEqual([5506, 4, 1.2, 18, 6.9], self.parse(
                    card("ARS5,506", 4, 1.2, 18, 6.9, bonus)))

    def test_unit_prices_are_not_total_fares(self):
        base = card("ARS5,506", 4, 1.2, 18, 6.9)
        for rate in ("ARS680/km", "ARS680 / km", "$680/km", "ARS680 por km",
                     "ARS680\n/km", "ARS50,000 por hora"):
            with self.subTest(rate=rate):
                self.assertEqual(5506, self.parse(base.replace("ARS680/km (estimado)", rate))[0])

    def test_missing_main_price_does_not_fall_back_to_bonus_or_rate(self):
        self.assertIsNone(self.parse(card("", 4, 1.2, 18, 6.9,
            "+ARS714.00 por inicio de viaje")))
        self.assertIsNone(self.parse(card("", 4, 1.2, 18, 6.9)))

    def test_conflicting_main_prices_request_review(self):
        self.assertIsNone(self.parse(card("ARS5,506\nARS8,000", 4, 1.2, 18, 6.9)))

    def test_duplicate_ocr_price_is_allowed(self):
        self.assertEqual(5506, self.parse(card("ARS5,506\nARS5,506", 4, 1.2, 18, 6.9))[0])

    def test_main_and_supplement_on_same_line(self):
        self.assertEqual(5506, self.parse(card(
            "ARS5,506 +ARS714.00 por inicio de viaje", 4, 1.2, 18, 6.9))[0])

    def test_separate_leg_labels_and_split_metrics(self):
        raw = card("ARS5,506", 4, 1.2, 18, 6.9)
        raw = raw.replace("A 4 min (1.2 km)", "Para llegar\n4 min\n1.2 km")
        raw = raw.replace("Viaje: 18 min (6.9 km)", "Viaje:\n18 min\n6.9 km")
        self.assertEqual([5506, 4, 1.2, 18, 6.9], self.parse(raw))

    def test_single_leg_with_trip_word_cannot_fill_both_legs(self):
        self.assertIsNone(self.parse("UberX\nARS5,506\nPara llegar al viaje 4 min (1.2 km)\nAceptar"))

    def test_zero_trip_is_incomplete(self):
        self.assertIsNone(self.parse(card("ARS5,506", 4, 1.2, 0, 0)))

    def test_split_legs_do_not_reuse_pickup_distance_for_trip(self):
        self.assertEqual([6000,3,1,20,9],self.parse(
            "UberX\nARS6000\nA 3 min\n1 km\nViaje: 20 min\n9 km\nAceptar"))

    def test_own_overlay_text_does_not_conflict_with_main_fare(self):
        raw=card("ARS6,000",3,1,20,9)
        raw+="\nCONVIENE\nTras costos $4.000 · $400/km\n$12.000/h · Nafta $800 · 10 km\nReserva $1.000 · supera tus mínimos"
        self.assertEqual([6000,3,1,20,9],self.parse(raw))

    def test_cloud_cannot_override_visible_distances_or_times(self):
        path = self.root / "offer-cloud-metrics.txt"
        path.write_text(card("ARS5,506", 4, 1.2, 18, 6.9))
        for values, expected in (((5506,4,1.2,18,6.9),True),
                                 ((5506,4,1.2,2,6.9),False),
                                 ((5506,4,1.2,18,1),False)):
            result = subprocess.run(["java","-cp",str(self.root),"ParserHarness",str(path),
                                     *map(str,values)],check=True,capture_output=True,text=True)
            self.assertEqual(expected,json.loads(result.stdout))

    def test_cloud_cannot_override_primary_with_bonus_or_rate(self):
        raw = card("ARS5,506", 4, 1.2, 18, 6.9, "+ARS714.00 por inicio de viaje")
        path = self.root / "cloud-offer.txt"
        path.write_text(raw, encoding="utf-8")
        for fare, expected in ((5506, True), (714, False), (680, False), (6220, False)):
            with self.subTest(fare=fare):
                result = subprocess.run(["java", "-cp", str(self.root), "ParserHarness", str(path), str(fare)],
                                        check=True, capture_output=True, text=True)
                self.assertEqual(expected, json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
