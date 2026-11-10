"""Regresiones de integración de los contratos del analizador y OCR.

No sustituyen pruebas unitarias Android ni una prueba sobre el dispositivo.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "android_src/org/drivercontrol/drivercontrol"


class OfferSafetyContractTest(unittest.TestCase):
    def test_green_requires_both_thresholds(self):
        source = (JAVA / "TripProfitabilityAnalyzer.java").read_text(encoding="utf-8")
        self.assertIn("hourly < minHourly", source)
        self.assertIn("perKm < minPerKm", source)
        self.assertIn("pickupKm > maxPickupKm", source)
        self.assertIn("Verdict.REVIEW", source)

    def test_invalid_or_nan_numbers_cannot_pass(self):
        source = (JAVA / "TripProfitabilityAnalyzer.java").read_text(encoding="utf-8")
        self.assertIn("Double.isNaN", source)
        self.assertIn("Double.isInfinite", source)
        self.assertIn("!valid", source)
        self.assertIn("Verdict.DISCARD", source)

    def test_wear_is_deducted_from_net_and_shown(self):
        engine = (JAVA / "TripProfitabilityAnalyzer.java").read_text(encoding="utf-8")
        overlay = (JAVA / "DriverOverlayService.java").read_text(encoding="utf-8")
        self.assertIn('p.getFloat("wear_per_km", 0.0f)', engine)
        self.assertIn("fare - fuelCost - wearCost", engine)
        self.assertIn("money(a.wearCost)", overlay)

    def test_overlay_is_small_and_collapsed_by_default(self):
        source = (JAVA / "DriverOverlayService.java").read_text(encoding="utf-8")
        self.assertIn("Math.min(dp(260)", source)
        self.assertIn("metricsView.setVisibility(View.GONE)", source)

    def test_ocr_requires_cash_context_and_unique_amount(self):
        source = (JAVA / "DriverCopilotCoordinator.java").read_text(encoding="utf-8")
        self.assertIn("cashHint && amounts.size() == 1", source)


if __name__ == "__main__":
    unittest.main()
