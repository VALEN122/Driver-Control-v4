import importlib.util
import sqlite3
import sys
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path


def _module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


class _DummyWidget:
    def __init__(self, *args, **kwargs):
        pass


class _DummyBuilder:
    @staticmethod
    def load_string(_value):
        return None


class _DummyClock:
    @staticmethod
    def schedule_once(*_args, **_kwargs):
        return None

    @staticmethod
    def schedule_interval(*_args, **_kwargs):
        return None


def _property(default=None):
    return default


def _load_main_without_kivy():
    _module("kivy")
    _module("kivy.lang", Builder=_DummyBuilder)
    _module("kivy.clock", Clock=_DummyClock)
    _module("kivy.graphics", Color=_DummyWidget, RoundedRectangle=_DummyWidget)
    _module("kivy.metrics", dp=lambda value: value)
    _module(
        "kivy.properties",
        BooleanProperty=_property,
        ListProperty=_property,
        NumericProperty=_property,
        StringProperty=_property,
    )
    _module("kivy.uix")
    _module("kivy.uix.scrollview", ScrollView=_DummyWidget)
    _module("kivy.uix.screenmanager", Screen=_DummyWidget)
    _module("kivy.uix.widget", Widget=_DummyWidget)
    _module("kivy.utils", platform="linux")
    _module("kivymd")
    _module("kivymd.app", MDApp=_DummyWidget)
    _module("kivymd.uix")
    _module("kivymd.uix.boxlayout", MDBoxLayout=_DummyWidget)
    _module("kivymd.uix.card", MDCard=_DummyWidget)
    _module("kivymd.uix.button", MDFlatButton=_DummyWidget)
    _module("kivymd.uix.dialog", MDDialog=_DummyWidget)
    _module("kivymd.uix.list", TwoLineListItem=_DummyWidget)
    _module("kivymd.uix.textfield", MDTextField=_DummyWidget)

    main_path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("driver_control_main_test", main_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FinanceModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _load_main_without_kivy()

    def setUp(self):
        self.app = object.__new__(self.main.DriverControlApp)
        self.app.conn = sqlite3.connect(":memory:")
        self.app.conn.row_factory = sqlite3.Row
        self.app.conn.execute("PRAGMA foreign_keys = ON")
        self.app._create_or_migrate_db()

    def tearDown(self):
        self.app.conn.close()

    def test_event_handlers_are_callable(self):
        """Kivy reserves on_<property> names for property callbacks."""
        invalid_handlers = [
            name
            for name, value in self.main.DriverControlApp.__dict__.items()
            if name.startswith("on_") and not callable(value)
        ]
        self.assertEqual([], invalid_handlers)

    def test_money_model_and_cash_reconciliation_are_separate(self):
        now = datetime.now()
        opened = (now - timedelta(hours=1)).strftime(self.main.DATETIME_FORMAT)
        date_text = now.strftime(self.main.DATE_FORMAT)
        with self.app.transaction():
            cursor = self.app.conn.execute(
                """
                INSERT INTO work_sessions(
                    opened_at,opening_odometer,current_odometer,opening_cash,status
                ) VALUES(?,?,?,?, 'OPEN')
                """,
                (opened, 10000, 10050, 1000),
            )
            session_id = int(cursor.lastrowid)
            self.app.conn.execute(
                """
                INSERT INTO trips(
                    created_at,amount,payment,km,duration,cash_received,
                    change_given,session_id,uber_fee
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    now.strftime(self.main.DATETIME_FORMAT),
                    10000,
                    self.main.PAYMENT_CASH,
                    0,
                    0,
                    10000,
                    0,
                    session_id,
                    2500,
                ),
            )
            self.app.conn.execute(
                "INSERT INTO expenses(created_at,category,description,amount,payment,session_id) "
                "VALUES(?,?,?,?,?,?)",
                (now.strftime(self.main.DATETIME_FORMAT), "Combustible", "Carga", 5000, "Efectivo", session_id),
            )
            self.app.conn.execute(
                "INSERT INTO expenses(created_at,category,description,amount,payment,session_id) "
                "VALUES(?,?,?,?,?,?)",
                (now.strftime(self.main.DATETIME_FORMAT), "Peaje", "Peaje", 1000, "Efectivo", session_id),
            )
            self.app.conn.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES('fuel_consumption','8')"
            )
            self.app.conn.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES('fuel_price','2000')"
            )

        period = self.app._range_metrics([date_text])
        self.assertEqual(period["income"], 10000)
        self.assertEqual(period["uber_fee"], 2500)
        self.assertEqual(period["known_billing"], 12500)
        self.assertEqual(period["expenses"], 1000)
        self.assertEqual(period["km"], 50)
        self.assertEqual(period["fuel_cost"], 8000)
        self.assertEqual(period["profit"], 1000)

        session = self.app._session_metrics(session_id)
        self.assertEqual(session["cash_expected"], 5000)
        self.assertEqual(session["net"], 1000)

    def test_schema_contains_new_financial_and_vehicle_fields(self):
        trip_columns = {
            row["name"] for row in self.app.conn.execute("PRAGMA table_info(trips)")
        }
        session_columns = {
            row["name"] for row in self.app.conn.execute("PRAGMA table_info(work_sessions)")
        }
        self.assertIn("uber_fee", trip_columns)
        self.assertIn("current_odometer", session_columns)
        table = self.app.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='maintenance_records'"
        ).fetchone()
        self.assertIsNotNone(table)
        summary_table = self.app.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_summaries'"
        ).fetchone()
        self.assertIsNotNone(summary_table)
        schema_version = self.app.conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(schema_version, self.main.DB_SCHEMA_VERSION)

    def test_smart_close_summary_replaces_trip_detail_without_double_counting(self):
        now = datetime.now()
        opened = (now - timedelta(hours=4)).strftime(self.main.DATETIME_FORMAT)
        closed = now.strftime(self.main.DATETIME_FORMAT)
        date_text = now.strftime(self.main.DATE_FORMAT)
        with self.app.transaction():
            cursor = self.app.conn.execute(
                """
                INSERT INTO work_sessions(
                    opened_at,closed_at,opening_odometer,current_odometer,
                    closing_odometer,opening_cash,status
                ) VALUES(?,?,?,?,?,?,'CLOSED')
                """,
                (opened, closed, 20000, 20100, 20100, 5000),
            )
            session_id = int(cursor.lastrowid)
            self.app.conn.execute(
                """
                INSERT INTO trips(
                    created_at,amount,payment,km,duration,cash_received,
                    change_given,session_id,uber_fee
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    now.strftime(self.main.DATETIME_FORMAT),
                    10000,
                    self.main.PAYMENT_CASH,
                    20,
                    30,
                    10000,
                    0,
                    session_id,
                    1000,
                ),
            )
            self.app.conn.execute(
                """
                INSERT INTO session_summaries(
                    session_id,income_total,trip_count,cash_collected,
                    mp_collected,app_collected,uber_fee,uber_owes,
                    driver_owes,confidence,source_mode,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    session_id,
                    25000,
                    5,
                    8000,
                    7000,
                    10000,
                    3000,
                    0,
                    0,
                    "CONFIRMED",
                    "QUICK",
                    closed,
                ),
            )
            self.app.conn.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES('fuel_consumption','10')"
            )
            self.app.conn.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES('fuel_price','1000')"
            )

        session = self.app._session_metrics(session_id)
        self.assertEqual(session["revenue"], 25000)
        self.assertEqual(session["uber_fee"], 3000)
        self.assertEqual(session["trips"], 5)
        self.assertEqual(session["cash_expected"], 13000)
        self.assertEqual(session["confidence"], "CONFIRMED")

        period = self.app._range_metrics([date_text])
        self.assertEqual(period["income"], 25000)
        self.assertEqual(period["uber_fee"], 3000)
        self.assertEqual(period["known_billing"], 28000)
        self.assertEqual(period["trips"], 5)
        self.assertEqual(period["km"], 100)
        self.assertEqual(period["fuel_cost"], 10000)
        self.assertEqual(period["profit"], 15000)

    def test_partial_summary_keeps_unknown_cash_explicit(self):
        now = datetime.now().strftime(self.main.DATETIME_FORMAT)
        with self.app.transaction():
            cursor = self.app.conn.execute(
                """
                INSERT INTO work_sessions(
                    opened_at,opening_odometer,current_odometer,opening_cash,status
                ) VALUES(?,?,?,?, 'OPEN')
                """,
                (now, 30000, 30010, 2000),
            )
            session_id = int(cursor.lastrowid)
            self.app.conn.execute(
                """
                INSERT INTO session_summaries(
                    session_id,income_total,trip_count,cash_collected,
                    mp_collected,app_collected,uber_fee,uber_owes,
                    driver_owes,confidence,source_mode,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    session_id, 18000, 0, None, None, None, 0, 0, 0,
                    "PARTIAL", "QUICK", now,
                ),
            )

        metrics = self.app._session_metrics(session_id)
        self.assertFalse(metrics["cash_reconciliation_known"])
        self.assertEqual(metrics["confidence"], "PARTIAL")

    def test_goal_progress_messages_are_short_and_encouraging(self):
        self.assertEqual(
            "Primer paso: sumá tu primer viaje.",
            self.app._goal_progress_message(0, 20000, 0),
        )
        self.assertIn(
            "Buen comienzo",
            self.app._goal_progress_message(20, 16000, 1),
        )
        self.assertIn(
            "Vas tomando ritmo",
            self.app._goal_progress_message(45, 11000, 3),
        )
        self.assertIn(
            "Último tramo",
            self.app._goal_progress_message(85, 3000, 7),
        )
        self.assertEqual(
            "¡Meta cumplida! Gran jornada.",
            self.app._goal_progress_message(100, 0, 8),
        )


if __name__ == "__main__":
    unittest.main()
