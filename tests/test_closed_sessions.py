import json
import types
import unittest

from test_finance_model import _load_main_without_kivy
import sqlite3
from finance_core import freeze_session_metrics
from excel_exporter import _session_summary


class ClosedSessionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _load_main_without_kivy()

    def setUp(self):
        self.app = object.__new__(self.main.DriverControlApp)
        self.app.conn = sqlite3.connect(":memory:")
        self.app.conn.row_factory = sqlite3.Row
        self.app.conn.execute("PRAGMA foreign_keys=ON")
        self.app._create_or_migrate_db()
        self.messages = []
        self.app.show_message = lambda *args: self.messages.append(args)
        self.app.refresh_all = lambda: None
        self.dialog = types.SimpleNamespace(dismiss=lambda: None)
        with self.app.transaction():
            self.app.conn.execute("UPDATE settings SET value='2000' WHERE key='fuel_price'")
            self.app.conn.execute("INSERT INTO work_sessions(id,opened_at,opening_odometer,current_odometer,opening_cash) VALUES(1,'19/09/2026 23:00',1000,1050,1000)")
            self.app.conn.execute("INSERT INTO trips(id,created_at,amount,payment,session_id) VALUES(1,'20/09/2026 00:30',20000,'Efectivo',1)")
            self.app.conn.execute("INSERT INTO expenses(created_at,category,amount,payment,session_id) VALUES('20/09/2026 00:40','Nafta',10000,'Efectivo',1)")
            self.app.conn.execute("INSERT INTO fuel(id,created_at,amount,liters,odometer,session_id) VALUES(1,'20/09/2026 00:40',10000,5,1050,1)")

    def tearDown(self):
        self.app.conn.close()

    def close(self):
        widgets = {k: types.SimpleNamespace(text=v) for k, v in {"odometer": "1050", "cash": "11000"}.items()}
        self.app.save_close_session(self.dialog, widgets)
        self.assertEqual("CLOSED", self.app.conn.execute("SELECT status FROM work_sessions").fetchone()[0])

    def test_close_survives_price_and_consumption_changes_in_all_reports(self):
        self.close()
        with self.app.transaction():
            self.app.conn.execute("UPDATE settings SET value='9999' WHERE key='fuel_price'")
            self.app.conn.execute("UPDATE settings SET value='30' WHERE key='fuel_consumption'")
        metrics = self.app._session_metrics(1)
        self.assertEqual(8000, metrics["fuel_cost"])
        self.assertEqual(12000, metrics["net"])
        self.assertEqual(11000, metrics["cash_expected"])
        self.assertEqual("CLOSE", metrics["snapshot_basis"])
        period = self.app._range_metrics(["19/09/2026"])
        self.assertEqual(12000, period["profit"])
        self.assertEqual(10000, period["fuel_purchases"])
        self.assertEqual(0, self.app._range_metrics(["20/09/2026"])["income"])
        excel = _session_summary(self.app.conn, {"fuel_price": "9999", "fuel_consumption": "30"})[0]
        self.assertEqual(metrics["net"], excel["estimated_result"])
        self.assertEqual(metrics["fuel_cost"], excel["fuel_cost"])

    def test_closed_trip_and_fuel_cannot_be_deleted(self):
        self.close()
        self.app.delete_trip(1, self.dialog)
        self.app.delete_fuel(1, self.dialog)
        for table in ("trips", "fuel", "expenses"):
            self.assertEqual(1, self.app.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        self.assertTrue(all("cerrada" in body for _, body in self.messages[-2:]))

    def test_open_trip_can_still_be_deleted(self):
        self.app.delete_trip(1, self.dialog)
        self.assertEqual(0, self.app.conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0])

    def test_legacy_migration_is_explicit_and_idempotent(self):
        with self.app.transaction():
            self.app.conn.execute("UPDATE work_sessions SET status='CLOSED',closed_at='20/09/2026 01:00',closing_odometer=1050")
            self.app.conn.execute("PRAGMA user_version=2")
        self.app._create_or_migrate_db()
        self.app._create_or_migrate_db()
        saved = self.app._session_metrics(1)
        self.assertEqual("LEGACY_RECONSTRUCTED", saved["snapshot_basis"])
        self.assertEqual(8000, saved["fuel_cost"])
        self.assertEqual(1, self.app.conn.execute("SELECT COUNT(*) FROM session_financial_snapshots").fetchone()[0])

    def test_failed_snapshot_rolls_back_the_close(self):
        # Simulate a DB write failure after the UPDATE but before committing.
        self.app.conn.execute("CREATE TRIGGER refuse_snapshot BEFORE INSERT ON session_financial_snapshots BEGIN SELECT RAISE(ABORT,'test write failure'); END")
        widgets = {k: types.SimpleNamespace(text=v) for k, v in {"odometer": "1050", "cash": "11000"}.items()}
        self.app.save_close_session(self.dialog, widgets)
        self.assertEqual("OPEN", self.app.conn.execute("SELECT status FROM work_sessions").fetchone()[0])

    def test_partial_summary_does_not_invent_cash_reconciliation(self):
        with self.app.transaction():
            self.app.conn.execute("INSERT INTO session_summaries(session_id,income_total,trip_count,confidence,source_mode,updated_at) VALUES(1,50000,8,'PARTIAL','QUICK','20/09/2026 01:00')")
        self.assertFalse(self.app._session_metrics(1)["cash_reconciliation_known"])

    def test_non_finite_input_is_rejected(self):
        for value in ("nan", "inf", "-inf", "1e999"):
            with self.subTest(value=value), self.assertRaises(self.main.ValidationError):
                self.app._parse_non_negative_float(value, "Importe")
