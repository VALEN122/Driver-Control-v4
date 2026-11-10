"""Reglas financieras puras compartidas por la app y sus exportaciones."""

import json
import re
import sqlite3
import unicodedata
from datetime import datetime


FUEL_CATEGORY_ALIASES = frozenset(
    {
        "combustible",
        "carga combustible",
        "carga de combustible",
        "carga de gnc",
        "carga de nafta",
        "combustibles",
        "diesel",
        "fuel",
        "gasolina",
        "gasoil",
        "gnc",
        "nafta",
        "naftas",
    }
)
GENERIC_EXPENSE_CATEGORIES = frozenset(
    {"", "gasto", "gastos", "otro", "otros", "varios"}
)
FUEL_DESCRIPTION_TERMS = frozenset(
    {
        "combustible",
        "combustibles",
        "diesel",
        "fuel",
        "gasolina",
        "gasoil",
        "gnc",
        "nafta",
        "naftas",
    }
)


def normalize_financial_label(value):
    """Normaliza etiquetas humanas sin alterar el valor guardado por el usuario."""

    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(
        character for character in text if not unicodedata.combining(character)
    )
    text = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
    return " ".join(text.split())


def is_fuel_purchase(category, description=None):
    """Indica si un gasto es una compra de combustible, sin inferir importes."""

    normalized_category = normalize_financial_label(category)
    if normalized_category in FUEL_CATEGORY_ALIASES:
        return True
    if normalized_category not in GENERIC_EXPENSE_CATEGORIES:
        return False

    description_words = set(normalize_financial_label(description).split())
    return bool(description_words & FUEL_DESCRIPTION_TERMS)


def register_sqlite_finance_functions(connection):
    """Expone las reglas puras a las consultas SQLite de esta conexión."""

    connection.create_function(
        "is_fuel_purchase",
        2,
        lambda category, description: int(is_fuel_purchase(category, description)),
    )


# No Kivy dependency: this is also the financial source for Excel.


def _query(connection, sql, parameters=()):
    cursor = connection.cursor()
    cursor.row_factory = sqlite3.Row
    return cursor.execute(sql, parameters)


def _has_table(connection, table):
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _optional_summary(connection, session_id):
    if not _has_table(connection, "session_summaries"):
        return None
    return _query(connection, "SELECT * FROM session_summaries WHERE session_id=?",
                  (session_id,)).fetchone()


def read_financial_snapshot(connection, session_id):
    if not _has_table(connection, "session_financial_snapshots"):
        return None
    row = _query(connection, "SELECT metrics_json, basis FROM session_financial_snapshots "
                 "WHERE session_id=?", (session_id,)).fetchone()
    if row is None:
        return None
    metrics = json.loads(row["metrics_json"])
    metrics["snapshot_basis"] = row["basis"]
    return metrics


def freeze_session_metrics(connection, session_id, metrics, basis="CLOSE"):
    # Caller owns the transaction so a failed snapshot rolls back the close too.
    connection.execute(
        "INSERT INTO session_financial_snapshots(session_id, metrics_json, basis, created_at) "
        "VALUES(?,?,?,?)",
        (session_id, json.dumps(metrics, allow_nan=False, ensure_ascii=False), basis,
         datetime.now().isoformat(timespec="seconds")),
    )


def calculate_session_metrics(connection, session_id, consumption, fuel_price,
                              closing_odometer=None):
    session = _query(connection,
        "SELECT * FROM work_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if session is None:
        raise ValueError("No se encontró la jornada.")

    if session["status"] == "CLOSED" and closing_odometer is None:
        saved = read_financial_snapshot(connection, session_id)
        if saved is not None:
            return saved

    trip = _query(connection,
        """
        SELECT COALESCE(SUM(amount),0) revenue,
               COALESCE(SUM(uber_fee),0) uber_fee,
               COALESCE(SUM(km),0) trip_km,
               COUNT(*) trips,
               COALESCE(SUM(CASE WHEN payment=? THEN amount ELSE 0 END),0) cash_sales
        FROM trips WHERE session_id=?
        """,
        ("Efectivo", session_id),
    ).fetchone()
    exp = _query(connection,
        """
        SELECT COALESCE(SUM(CASE WHEN is_fuel_purchase(category,description)=0 THEN amount ELSE 0 END),0) operating,
               COALESCE(SUM(CASE WHEN is_fuel_purchase(category,description)=1 THEN amount ELSE 0 END),0) fuel_purchases,
               COALESCE(SUM(CASE WHEN payment=? THEN amount ELSE 0 END),0) cash_paid
        FROM expenses WHERE session_id=?
        """,
        ("Efectivo", session_id),
    ).fetchone()
    loaded = _query(connection,
        "SELECT COALESCE(SUM(amount),0) amount, COALESCE(SUM(liters),0) liters FROM fuel WHERE session_id=?",
        (session_id,),
    ).fetchone()
    summary = _optional_summary(connection, session_id)

    end_odo = closing_odometer
    if end_odo is None:
        end_odo = session["closing_odometer"]
    if end_odo is None:
        end_odo = session["current_odometer"]
    if end_odo is not None:
        worked_km = max(float(end_odo) - float(session["opening_odometer"]), 0.0)
    else:
        worked_km = float(trip["trip_km"] or 0.0)

    fuel_liters = worked_km * consumption / 100.0
    fuel_cost = fuel_liters * fuel_price
    operating_expenses = float(exp["operating"] or 0.0)
    revenue = float(
        summary["income_total"] if summary is not None else trip["revenue"] or 0.0
    )
    uber_fee = float(
        summary["uber_fee"] if summary is not None else trip["uber_fee"] or 0.0
    )
    trips = int(
        summary["trip_count"] if summary is not None else trip["trips"] or 0
    )
    net = revenue - operating_expenses - fuel_cost
    fuel_purchase_amount = float(exp["fuel_purchases"] or 0.0)
    summary_cash = summary["cash_collected"] if summary is not None else None
    cash_sales = (
        float(summary_cash)
        if summary_cash is not None
        else float(trip["cash_sales"] or 0.0)
    )
    cash_reconciliation_known = (
        summary is None
        or summary_cash is not None
    )
    cash_expected = (
        float(session["opening_cash"] or 0.0)
        + cash_sales
        - float(exp["cash_paid"] or 0.0)
    )
    return {
        "fuel_price": fuel_price,
        "fuel_consumption": consumption,
        "snapshot_basis": "LIVE",
        "revenue": revenue,
        "uber_fee": uber_fee,
        # Older records used zero for both missing and explicit zero fees.
        # Smart close preserves the explicit input flag in its frozen snapshot.
        "uber_fee_known": uber_fee > 0,
        "known_billing": revenue + uber_fee,
        "trips": trips,
        "worked_km": worked_km,
        "operating_expenses": operating_expenses,
        "fuel_liters": fuel_liters,
        "fuel_cost": fuel_cost,
        "fuel_loaded_amount": float(loaded["amount"] or 0.0),
        "fuel_loaded_liters": float(loaded["liters"] or 0.0),
        "fuel_purchase_amount": fuel_purchase_amount,
        "recorded_payment_balance": (
            revenue - operating_expenses - fuel_purchase_amount
        ),
        "net": net,
        "cash_expected": cash_expected,
        "opening_cash": float(session["opening_cash"] or 0.0),
        "cash_collected": cash_sales if cash_reconciliation_known else None,
        "cash_paid": float(exp["cash_paid"] or 0.0),
        "cash_reconciliation_known": cash_reconciliation_known,
        "confidence": summary["confidence"] if summary is not None else "CONFIRMED",
        "source_mode": summary["source_mode"] if summary is not None else "DETAILED",
    }


def hourly_estimate(net, worked_minutes):
    """Avoid presenting a few-minute registration as a useful hourly result."""
    if worked_minutes < 10:
        return None
    return net * 60.0 / worked_minutes
