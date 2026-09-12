import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from excel_exporter import _session_summary, export_driver_control_xlsx


SCHEMA = """
CREATE TABLE trips(
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    amount REAL NOT NULL,
    payment TEXT NOT NULL,
    km REAL NOT NULL,
    duration INTEGER NOT NULL,
    cash_received REAL,
    change_given REAL,
    session_id INTEGER,
    uber_fee REAL NOT NULL DEFAULT 0
);
CREATE TABLE expenses(
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    amount REAL NOT NULL,
    session_id INTEGER,
    payment TEXT
);
CREATE TABLE fuel(
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    amount REAL NOT NULL,
    liters REAL NOT NULL,
    odometer REAL NOT NULL,
    session_id INTEGER,
    payment TEXT
);
CREATE TABLE work_sessions(
    id INTEGER PRIMARY KEY,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    opening_odometer REAL NOT NULL,
    current_odometer REAL,
    closing_odometer REAL,
    opening_cash REAL NOT NULL,
    closing_cash REAL,
    cash_expected REAL,
    cash_difference REAL,
    status TEXT NOT NULL
);
CREATE TABLE session_summaries(
    session_id INTEGER PRIMARY KEY,
    income_total REAL NOT NULL,
    trip_count INTEGER NOT NULL,
    cash_collected REAL,
    mp_collected REAL,
    app_collected REAL,
    uber_fee REAL NOT NULL,
    uber_owes REAL NOT NULL,
    driver_owes REAL NOT NULL,
    confidence TEXT NOT NULL,
    source_mode TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE driver_breaks(
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT
);
CREATE TABLE fatigue_checkins(
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    level INTEGER NOT NULL
);
CREATE TABLE trip_assessments(
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    fare REAL NOT NULL,
    pickup_min REAL NOT NULL,
    pickup_km REAL NOT NULL,
    trip_min REAL NOT NULL,
    trip_km REAL NOT NULL,
    total_min REAL NOT NULL,
    total_km REAL NOT NULL,
    fuel_cost REAL NOT NULL,
    net_est REAL NOT NULL,
    hourly_est REAL NOT NULL,
    per_km_est REAL NOT NULL,
    score REAL NOT NULL,
    recommendation TEXT NOT NULL,
    destination_rating TEXT NOT NULL,
    decision TEXT
);
CREATE TABLE maintenance_records(
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    odometer REAL NOT NULL,
    amount REAL NOT NULL,
    next_due_date TEXT,
    next_due_odometer REAL,
    payment TEXT,
    session_id INTEGER,
    expense_id INTEGER,
    status TEXT NOT NULL
);
"""


class ExcelExporterTest(unittest.TestCase):
    def test_exports_all_operational_tables_and_hides_token(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO work_sessions VALUES(1,?,?,?,?,?,?,?,?,?,?)",
            (
                "09/09/2026 18:00",
                "09/09/2026 22:00",
                77000,
                77076.1,
                77076.1,
                0,
                33600,
                33600,
                0,
                "CLOSED",
            ),
        )
        connection.execute(
            "INSERT INTO trips VALUES(1,?,?,?,?,?,?,?,?,?)",
            ("09/09/2026 18:29", 8708, "Efectivo", 11.2, 23, 8600, 0, 1, 950),
        )
        connection.execute(
            "INSERT INTO session_summaries VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                1, 33600, 12, 9000, 4600, 20000, 4200, 0, 0,
                "CONFIRMED", "QUICK", "09/09/2026 22:00",
            ),
        )
        connection.execute(
            "INSERT INTO expenses VALUES(1,?,?,?,?,?,?)",
            ("09/09/2026 21:53", "Combustible", "Carga 13.70 L", 30000, 1, "Efectivo"),
        )
        connection.execute(
            "INSERT INTO fuel VALUES(1,?,?,?,?,?,?)",
            ("09/09/2026 21:53", 30000, 13.70, 77076.1, 1, "Efectivo"),
        )
        connection.executemany(
            "INSERT INTO settings(key,value) VALUES(?,?)",
            (
                ("fuel_consumption", "8"),
                ("fuel_price", "2048"),
                ("vehicle", "Volkswagen Gol Trend 2015"),
                ("ai_access_token", "secret-token-must-not-leak"),
            ),
        )
        connection.execute(
            "INSERT INTO driver_breaks VALUES(1,1,?,?)",
            ("09/09/2026 20:00", "09/09/2026 20:15"),
        )
        connection.execute(
            "INSERT INTO fatigue_checkins VALUES(1,1,?,3)",
            ("09/09/2026 21:00",),
        )
        connection.execute(
            "INSERT INTO trip_assessments VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "09/09/2026 18:25",
                8708,
                4,
                1.8,
                23,
                11.2,
                27,
                13,
                2129.92,
                6578.08,
                14617.96,
                506.01,
                82,
                "CONVIENE",
                "NEUTRAL",
                "ACEPTADO",
            ),
        )
        connection.execute(
            "INSERT INTO maintenance_records VALUES(1,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "09/09/2026 17:00", "Aceite y filtros", "Cambio completo",
                77000, 45000, "09/03/2027", 87000, "Mercado Pago",
                1, None, "COMPLETED",
            ),
        )
        connection.commit()

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "driver_control.xlsx"
            counts = export_driver_control_xlsx(connection, output, "5.9.0")
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 10_000)
            self.assertEqual(counts["jornadas"], 1)
            self.assertEqual(counts["viajes"], 1)
            self.assertEqual(counts["gastos"], 1)
            self.assertEqual(counts["cargas"], 1)
            self.assertEqual(counts["mantenimientos"], 1)
            self.assertEqual(counts["cierres"], 1)

            summaries = _session_summary(connection, {
                "fuel_consumption": "8", "fuel_price": "2048"
            })
            self.assertEqual(summaries[0]["amount"], 33600)
            self.assertEqual(summaries[0]["trips"], 12)
            self.assertEqual(summaries[0]["confidence"], "CONFIRMED")

            with zipfile.ZipFile(output) as archive:
                self.assertIn("xl/workbook.xml", archive.namelist())
                content = b"\n".join(
                    archive.read(name)
                    for name in archive.namelist()
                    if name.endswith(".xml")
                ).decode("utf-8")

            for sheet_name in (
                "Resumen",
                "Jornadas",
                "Cierres",
                "Viajes",
                "Gastos",
                "Combustible",
                "Evaluaciones",
                "Pausas",
                "Fatiga",
                "Mantenimiento",
                "Configuración",
            ):
                self.assertIn(sheet_name, content)
            self.assertIn("No exportado por seguridad", content)
            self.assertNotIn("secret-token-must-not-leak", content)


if __name__ == "__main__":
    unittest.main()
