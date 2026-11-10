import sqlite3
import unittest

from finance_core import is_fuel_purchase, register_sqlite_finance_functions


class ExpenseClassificationTest(unittest.TestCase):
    def test_recognizes_common_fuel_names(self):
        for category in (
            "Combustible",
            "NAFTA",
            "Naftas",
            "Carga de nafta",
            "Diésel",
            "Gasolina",
            "GNC",
            "Fuel",
        ):
            with self.subTest(category=category):
                self.assertTrue(is_fuel_purchase(category, ""))

    def test_recognizes_fuel_in_generic_description_only(self):
        self.assertTrue(is_fuel_purchase("Otro", "Carga de nafta del día"))
        self.assertFalse(is_fuel_purchase("Peaje", "Estación de combustible"))
        self.assertFalse(is_fuel_purchase("Otro", "Lavado del auto"))

    def test_sqlite_uses_the_same_rule(self):
        connection = sqlite3.connect(":memory:")
        register_sqlite_finance_functions(connection)
        result = connection.execute(
            "SELECT is_fuel_purchase(?, ?)",
            ("Nafta", "Carga del tanque"),
        ).fetchone()[0]
        connection.close()
        self.assertEqual(1, result)


if __name__ == "__main__":
    unittest.main()
