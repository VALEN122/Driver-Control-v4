import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from excel_exporter import export_driver_control_xlsx


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
    session_id INTEGER
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
    closing_odometer REAL,
    opening_cash REAL NOT NULL,
    closing_cash REAL,
    cash_expected REAL,
    cash_difference REAL,
    status TEXT NOT NULL
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
"""


class ExcelExporterTest(unittest.TestCase):
    def test_exports_all_operational_tables_and_hides_token(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript(SCHEMA)
        connection.execute(
            "INSERT INTO work_sessions VALUES(1,?,?,?,?,?,?,?,?,?)",
            (
                "09/09/2026 18:00",
                "09/09/2026 22:00",
                77000,
                77076.1,
                0,
                33600,
                33600,
                0,
                "CLOSED",
            ),
        )
        connection.execute(
            "INSERT INTO trips VALUES(1,?,?,?,?,?,?,?,?)",
            ("09/09/2026 18:29", 8708, "Efectivo", 11.2, 23, 8600, 0, 1),
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
        connection.commit()

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "driver_control.xlsx"
            counts = export_driver_control_xlsx(connection, output, "5.8.0")
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 10_000)
            self.assertEqual(counts["jornadas"], 1)
            self.assertEqual(counts["viajes"], 1)
            self.assertEqual(counts["gastos"], 1)
            self.assertEqual(counts["cargas"], 1)

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
                "Viajes",
                "Gastos",
                "Combustible",
                "Evaluaciones",
                "Pausas",
                "Fatiga",
                "Configuración",
            ):
                self.assertIn(sheet_name, content)
            self.assertIn("No exportado por seguridad", content)
            self.assertNotIn("secret-token-must-not-leak", content)


if __name__ == "__main__":
    unittest.main()
