"""Regression scenarios from the September 28 fictitious session."""

import logging
import sqlite3
import tempfile
import types
import unittest
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from test_finance_model import _load_main_without_kivy
from finance_core import hourly_estimate
from excel_exporter import _session_summary, export_driver_control_xlsx


class Audit622Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _load_main_without_kivy()

    def setUp(self):
        self.app = object.__new__(self.main.DriverControlApp)
        self.app.conn = sqlite3.connect(":memory:")
        self.app.conn.row_factory = sqlite3.Row
        self.app.conn.execute("PRAGMA foreign_keys=ON")
        self.app._create_or_migrate_db()
        self.app.refresh_all = lambda: None
        self.messages = []
        self.app.show_message = lambda *args: self.messages.append(args)
        self.dialog = types.SimpleNamespace(dismiss=lambda: None)
        self.story = types.SimpleNamespace()
        opened = (datetime.now() - timedelta(minutes=2)).strftime(self.main.DATETIME_FORMAT)
        self.app.conn.execute(
            "INSERT INTO work_sessions(id,opened_at,opening_odometer,current_odometer,opening_cash) "
            "VALUES(1,?,1000,1000,5000)", (opened,)
        )
        self.app.conn.commit()

    def tearDown(self):
        self.app.conn.close()

    def close(self, payment="Efectivo", fee="", cash_collected="89000"):
        widgets = {key: types.SimpleNamespace(text=value) for key, value in {
            "amount": "20000", "liters": "7", "odometer": "1060", "payment": payment,
        }.items()}
        self.app.save_fuel(self.dialog, widgets)
        fields = {key: types.SimpleNamespace(text=value) for key, value in {
            "close_income": "89000", "close_trip_count": "7",
            "close_cash_collected": cash_collected, "close_mp_collected": "",
            "close_app_collected": "", "close_uber_fee": fee,
            "close_uber_owes": "", "close_driver_owes": "",
            "close_cash_counted": "74000" if payment == "Efectivo" else "94000",
            "close_odometer": "1060",
        }.items()}
        screen = types.SimpleNamespace(ids=types.SimpleNamespace(**fields),
                                       data_confidence="PARTIAL", show_details=False)
        self.app.root = types.SimpleNamespace(
            get_screen=lambda name: screen if name == "smart_close" else self.story,
            current="smart_close",
        )
        self.app.save_smart_close()
        row = self.app.conn.execute("SELECT * FROM work_sessions WHERE id=1").fetchone()
        self.assertEqual("CLOSED", row["status"], self.messages)
        self.assertEqual("day_story", self.app.root.current, self.messages)
        return self.app._session_metrics(1), row

    def test_cash_fuel_purchase_and_displayed_breakdown(self):
        metrics, row = self.close()
        self.assertEqual(74000, metrics["cash_expected"])
        self.assertEqual(0, row["cash_difference"])
        self.assertEqual(20000, metrics["cash_paid"])
        self.assertAlmostEqual(79169.6, metrics["net"])
        self.assertEqual(69000, metrics["recorded_payment_balance"])
        self.assertEqual("Pocos minutos", self.story.hourly_text)
        self.assertIn("$20.000", self.story.audit_text)
        self.assertIn("$74.000", self.story.audit_text)
        self.assertIn("$2.048/L", self.story.audit_text)
        self.assertIn("$2.857/L", self.story.audit_text)

    def test_mp_fuel_purchase_keeps_net_and_changes_cash_by_20000(self):
        metrics, row = self.close(payment="Mercado Pago")
        self.assertEqual(94000, metrics["cash_expected"])
        self.assertEqual(0, metrics["cash_paid"])
        self.assertEqual(0, row["cash_difference"])
        self.assertAlmostEqual(79169.6, metrics["net"])

    def test_unknown_cash_stays_unconfirmed(self):
        metrics, row = self.close(cash_collected="")
        self.assertFalse(metrics["cash_reconciliation_known"])
        self.assertIsNone(row["cash_difference"])
        self.assertIn("Conciliación de caja pendiente", self.story.audit_text)
        exported = _session_summary(self.app.conn, {})[0]
        self.assertIsNone(exported["cash_expected"])

    def test_explicit_zero_commission_survives_snapshot_and_settings_change(self):
        metrics, _ = self.close(fee="0")
        self.assertTrue(metrics["uber_fee_known"])
        self.app.conn.execute("UPDATE settings SET value='3000' WHERE key='fuel_price'")
        self.app.conn.commit()
        exported = _session_summary(self.app.conn, {"fuel_price": "3000"})[0]
        self.assertEqual(0, exported["uber_fee"])
        self.assertEqual(89000, exported["known_billing"])
        self.assertEqual(2048, exported["fuel_price"])
        self.assertAlmostEqual(79169.6, exported["estimated_result"])

    def test_missing_commission_is_not_exported_as_zero_and_summary_has_60_km(self):
        metrics, _ = self.close()
        self.assertFalse(metrics["uber_fee_known"])
        exported = _session_summary(self.app.conn, {})[0]
        self.assertIsNone(exported["uber_fee"])
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "audit.xlsx"
            export_driver_control_xlsx(self.app.conn, destination, "6.2.2")
            with zipfile.ZipFile(destination) as archive:
                ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                strings = ["".join(item.itertext()) for item in
                           ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("m:si", ns)]
                root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
                def value(cell):
                    text = cell.findtext("m:v", namespaces=ns)
                    return strings[int(text)] if cell.get("t") == "s" else text
                values = {}
                for row in root.findall("m:sheetData/m:row", ns):
                    cells = row.findall("m:c", ns)
                    if len(cells) == 2:
                        values[value(cells[0])] = value(cells[1])
                self.assertEqual("Sin informar", values["Comisión Uber informada"])
                self.assertEqual("60", values["Kilómetros trabajados en jornadas"])
                self.assertEqual("0", values["Kilómetros cargados en viajes"])
                self.assertEqual("89000", values["Ingresos registrados"])
                self.assertIn("Resultados", archive.read("xl/workbook.xml").decode())

    def test_hourly_rate_is_hidden_for_two_minute_demo_without_capping_real_results(self):
        self.assertIsNone(hourly_estimate(79169.6, 2))
        self.assertAlmostEqual(19792.4, hourly_estimate(79169.6, 240))
        self.assertEqual(-5000, hourly_estimate(-10000, 120))


if __name__ == "__main__":
    unittest.main()
