"""Exportación segura y completa de Driver Control a un libro de Excel."""

from datetime import datetime
from pathlib import Path

import xlsxwriter

from finance_core import register_sqlite_finance_functions, calculate_session_metrics


DATETIME_FORMATS = (
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)

SENSITIVE_SETTING_KEYS = {"ai_access_token"}

REPORT_LABELS = {
    "CLOSED": "Cerrada", "OPEN": "Abierta", "CLOSE": "Al cierre",
    "LIVE": "En curso", "LEGACY_RECONSTRUCTED": "Histórico estimado",
    "PARTIAL": "Parcial", "CONFIRMED": "Confirmado",
    "QUICK": "Carga rápida", "DETAILED": "Con detalle", "OCR": "Lectura OCR",
}


def _select(connection, sql, params=()):
    cursor = connection.execute(sql, params)
    columns = [item[0] for item in cursor.description]
    result = []
    for row in cursor.fetchall():
        if hasattr(row, "keys"):
            result.append(dict(row))
        else:
            result.append(dict(zip(columns, row)))
    return result


def _table_exists(connection, table_name):
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _excel_datetime(value):
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for date_format in DATETIME_FORMATS:
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    return text


def _minutes_between(start_value, end_value):
    start = _excel_datetime(start_value)
    end = _excel_datetime(end_value)
    if isinstance(start, datetime) and isinstance(end, datetime):
        return max((end - start).total_seconds() / 60.0, 0.0)
    return None


def _formats(workbook):
    return {
        "title": workbook.add_format(
            {
                "bold": True,
                "font_size": 20,
                "font_color": "#FFFFFF",
                "bg_color": "#173B67",
                "align": "left",
                "valign": "vcenter",
            }
        ),
        "section": workbook.add_format(
            {
                "bold": True,
                "font_size": 13,
                "font_color": "#173B67",
                "bottom": 1,
                "bottom_color": "#9FB4CC",
            }
        ),
        "label": workbook.add_format(
            {"font_color": "#526174", "bold": True, "text_wrap": True}
        ),
        "value": workbook.add_format({"font_color": "#101828"}),
        "money": workbook.add_format(
            {"num_format": '"$"#,##0.00;[Red]-"$"#,##0.00', "align": "right"}
        ),
        "number": workbook.add_format(
            {"num_format": "#,##0.00", "align": "right"}
        ),
        "integer": workbook.add_format(
            {"num_format": "#,##0", "align": "right"}
        ),
        "date": workbook.add_format(
            {"num_format": "dd/mm/yyyy hh:mm", "align": "left"}
        ),
        "text": workbook.add_format({"text_wrap": True, "valign": "top"}),
        "note": workbook.add_format(
            {
                "font_color": "#526174",
                "bg_color": "#EEF3F9",
                "text_wrap": True,
                "valign": "top",
            }
        ),
        "warning": workbook.add_format(
            {
                "font_color": "#8A4B00",
                "bg_color": "#FFF4DE",
                "bold": True,
            }
        ),
    }


def _cell_format(formats, kind):
    return formats.get(kind, formats["text"])


def _prepare_value(value, kind):
    if kind == "date":
        return _excel_datetime(value)
    if value is None:
        return "Sin informar" if kind in {"money", "number", "integer"} else ""
    if kind in {"money", "number"}:
        return _as_float(value)
    if kind == "integer":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return REPORT_LABELS.get(value, value) if kind == "text" else value


def _write_data_sheet(workbook, formats, title, table_name, columns, rows):
    worksheet = workbook.add_worksheet(title)
    worksheet.freeze_panes(1, 0)
    worksheet.set_tab_color("#356FA8")

    for column_index, (_key, _header, kind, width) in enumerate(columns):
        worksheet.set_column(
            column_index,
            column_index,
            width,
            _cell_format(formats, kind),
        )

    headers = [
        {"header": header, "format": _cell_format(formats, kind)}
        for _key, header, kind, _width in columns
    ]

    if not rows:
        worksheet.write_row(0, 0, [item[1] for item in columns], formats["label"])
        worksheet.merge_range(
            1,
            0,
            1,
            max(len(columns) - 1, 0),
            "Sin datos registrados",
            formats["note"],
        )
        return

    data = [
        [
            _prepare_value(row.get(key), kind)
            for key, _header, kind, _width in columns
        ]
        for row in rows
    ]
    worksheet.add_table(
        0,
        0,
        len(data),
        len(columns) - 1,
        {
            "name": table_name,
            "style": "Table Style Medium 2",
            "data": data,
            "columns": headers,
            "autofilter": True,
        },
    )


def _load_settings(connection):
    if not _table_exists(connection, "settings"):
        return {}
    return {
        str(row["key"]): str(row["value"])
        for row in _select(connection, "SELECT key, value FROM settings")
    }


def _session_summary(connection, settings):
    register_sqlite_finance_functions(connection)
    if not _table_exists(connection, "work_sessions"):
        return []

    consumption = _as_float(settings.get("fuel_consumption"), 8.0)
    fuel_price = _as_float(settings.get("fuel_price"), 0.0)
    sessions = _select(
        connection,
        """
        SELECT id, opened_at, closed_at, status, opening_odometer,
               current_odometer, closing_odometer, opening_cash, closing_cash,
               cash_expected, cash_difference
          FROM work_sessions
         ORDER BY id
        """,
    )

    output = []
    for session in sessions:
        session_id = session["id"]
        metrics = calculate_session_metrics(connection, session_id, consumption, fuel_price)
        fee_known = metrics.get("uber_fee_known", metrics["uber_fee"] > 0)
        output.append(
            {
                "id": session_id,
                "opened_at": session.get("opened_at"),
                "closed_at": session.get("closed_at"),
                "status": session.get("status"),
                "trips": metrics["trips"],
                "amount": metrics["revenue"],
                "uber_fee": metrics["uber_fee"] if fee_known else None,
                "uber_fee_known": fee_known,
                "known_billing": metrics["known_billing"] if fee_known else None,
                "worked_km": metrics["worked_km"],
                "operating": metrics["operating_expenses"],
                "fuel_purchases": metrics["fuel_purchase_amount"],
                "fuel_cost": metrics["fuel_cost"],
                "fuel_price": metrics["fuel_price"],
                "fuel_consumption": metrics["fuel_consumption"],
                "fuel_liters": metrics["fuel_liters"],
                "estimated_result": metrics["net"],
                "opening_cash": metrics.get("opening_cash", session.get("opening_cash")),
                "cash_collected": metrics.get("cash_collected"),
                "cash_paid": metrics.get("cash_paid"),
                "closing_cash": session.get("closing_cash"),
                "cash_expected": metrics["cash_expected"] if metrics["cash_reconciliation_known"] else None,
                "cash_difference": session.get("cash_difference"),
                "confidence": metrics["confidence"],
                "source_mode": metrics["source_mode"],
                "snapshot_basis": metrics["snapshot_basis"],
            }
        )
    return output


def _write_summary(workbook, formats, connection, app_version, settings, summaries):
    worksheet = workbook.add_worksheet("Resumen")
    worksheet.set_tab_color("#173B67")
    worksheet.set_column("A:A", 42)
    worksheet.set_column("B:B", 24)
    worksheet.hide_gridlines(2)
    worksheet.freeze_panes(3, 0)
    worksheet.set_row(0, 34)
    worksheet.merge_range("A1:B1", "Driver Control - Resumen", formats["title"])

    trip_stats = _select(
        connection,
        "SELECT COUNT(*) AS count, COALESCE(SUM(amount),0) AS amount, "
        "COALESCE(SUM(uber_fee),0) AS uber_fee, "
        "COALESCE(SUM(km),0) AS km FROM trips",
    )[0]
    incomplete = _select(
        connection,
        "SELECT COUNT(*) AS count FROM trips WHERE km<=0 OR duration<=0",
    )[0]
    expense_stats = _select(
        connection,
        "SELECT COALESCE(SUM(CASE WHEN is_fuel_purchase(category,description)=0 "
        "THEN amount ELSE 0 END),0) AS operating, "
        "COALESCE(SUM(CASE WHEN is_fuel_purchase(category,description)=1 "
        "THEN amount ELSE 0 END),0) AS fuel_purchases FROM expenses",
    )[0]
    fuel_stats = _select(
        connection,
        "SELECT COALESCE(SUM(amount),0) AS amount, "
        "COALESCE(SUM(liters),0) AS liters FROM fuel",
    )[0]
    maintenance_stats = {"count": 0, "amount": 0.0}
    if _table_exists(connection, "maintenance_records"):
        maintenance_stats = _select(
            connection,
            "SELECT COUNT(*) AS count, COALESCE(SUM(amount),0) AS amount "
            "FROM maintenance_records",
        )[0]
    estimated_session_result = sum(
        _as_float(row.get("estimated_result")) for row in summaries
    )
    orphan_stats = _select(
        connection,
        "SELECT COUNT(*) AS count, COALESCE(SUM(amount),0) AS amount, "
        "COALESCE(SUM(uber_fee),0) AS uber_fee, "
        "COALESCE(SUM(CASE WHEN uber_fee<=0 THEN 1 ELSE 0 END),0) AS fee_unknown "
        "FROM trips WHERE session_id IS NULL",
    )[0]
    total_income = sum(_as_float(row.get("amount")) for row in summaries) + _as_float(
        orphan_stats.get("amount")
    )
    total_uber_fee = sum(_as_float(row.get("uber_fee")) for row in summaries) + _as_float(
        orphan_stats.get("uber_fee")
    )
    total_trip_count = sum(int(row.get("trips") or 0) for row in summaries) + int(
        orphan_stats.get("count") or 0
    )
    fee_complete = all(row["uber_fee_known"] for row in summaries) and not orphan_stats["fee_unknown"]
    any_fee_known = any(row["uber_fee_known"] for row in summaries) or orphan_stats["uber_fee"] > 0

    overview = [
        ("Generado", datetime.now(), "date"),
        ("Versión de la app", app_version, "text"),
        ("Jornadas registradas", len(summaries), "integer"),
        ("Viajes informados", total_trip_count, "integer"),
        ("Viajes con detalle individual", trip_stats["count"], "integer"),
        ("Ingresos registrados", total_income, "money"),
        ("Comisión Uber informada", total_uber_fee if any_fee_known else None, "money"),
        ("Datos de comisión", "Completos" if fee_complete and any_fee_known else "Parciales o sin informar", "text"),
        (
            "Facturación conocida (ingresos + comisión)",
            total_income + total_uber_fee if fee_complete and any_fee_known else None,
            "money",
        ),
        ("Ganancia estimada de jornadas", estimated_session_result, "money"),
        ("Kilómetros trabajados en jornadas", sum(row["worked_km"] for row in summaries), "number"),
        ("Kilómetros cargados en viajes", trip_stats["km"], "number"),
        ("Otros gastos", expense_stats["operating"], "money"),
        ("Cargas de combustible", expense_stats["fuel_purchases"], "money"),
        ("Litros cargados", fuel_stats["liters"], "number"),
        ("Mantenimientos registrados", maintenance_stats["count"], "integer"),
        ("Costo de mantenimiento", maintenance_stats["amount"], "money"),
    ]
    worksheet.write("A3", "Resumen general", formats["section"])
    for row_index, (label, value, kind) in enumerate(overview, start=3):
        worksheet.set_row(row_index, 32)
        worksheet.write(row_index, 0, label, formats["label"])
        worksheet.write(row_index, 1, _prepare_value(value, kind), _cell_format(formats, kind))

    note_row = 3 + len(overview) + 1
    if int(incomplete["count"] or 0) > 0:
        worksheet.merge_range(
            note_row,
            0,
            note_row,
            1,
            f"Revisar {int(incomplete['count'])} viaje(s) con kilómetros o duración en cero.",
            formats["warning"],
        )
        note_row += 1

    worksheet.merge_range(
        note_row,
        0,
        note_row + 4,
        1,
        "Ingresos es el monto que el conductor registró. La comisión Uber informada se muestra aparte y no se "
        "descuenta nuevamente. Facturación conocida es ingresos más comisión informada. La ganancia estimada "
        "resta otros gastos y combustible consumido según kilometraje, consumo y precio configurados. Cuando "
        "hay un cierre inteligente, sus totales prevalecen sobre el detalle para evitar duplicaciones. "
        "Sin informar no significa cero. Ver el desglose en Resultados.",
        formats["note"],
    )

    for row_index in range(note_row, note_row + 5):
        worksheet.set_row(row_index, 30)
    worksheet = workbook.add_worksheet("Resultados")
    worksheet.set_tab_color("#356FA8")
    worksheet.set_column("A:Z", 23)
    worksheet.set_row(1, 42)
    start_row = 0
    worksheet.write(start_row, 0, "Resumen por jornada", formats["section"])
    columns = [
        ("id", "Jornada", "integer"),
        ("opened_at", "Apertura", "date"),
        ("closed_at", "Cierre", "date"),
        ("status", "Estado", "text"),
        ("trips", "Viajes", "integer"),
        ("amount", "Ingresos registrados", "money"),
        ("uber_fee", "Comisión informada", "money"),
        ("known_billing", "Facturación conocida", "money"),
        ("worked_km", "Km trabajados", "number"),
        ("operating", "Otros gastos", "money"),
        ("fuel_purchases", "Cargas de combustible", "money"),
        ("fuel_cost", "Combustible consumido", "money"),
        ("snapshot_basis", "Base del cálculo", "text"),
        ("estimated_result", "Resultado estimado", "money"),
        ("cash_expected", "Efectivo esperado", "money"),
        ("cash_difference", "Diferencia de caja", "money"),
        ("confidence", "Confianza", "text"),
        ("source_mode", "Origen", "text"),
        ("opening_cash", "Efectivo inicial", "money"),
        ("cash_collected", "Cobros en efectivo", "money"),
        ("cash_paid", "Pagos en efectivo", "money"),
        ("closing_cash", "Efectivo contado", "money"),
        ("fuel_price", "Nafta usada ($/L)", "money"),
        ("fuel_consumption", "Consumo (L/100 km)", "number"),
        ("fuel_liters", "Litros consumidos estimados", "number"),
    ]
    if summaries:
        table_data = [
            [_prepare_value(row.get(key), kind) for key, _header, kind in columns]
            for row in summaries
        ]
        worksheet.add_table(
            start_row + 1,
            0,
            start_row + len(table_data) + 1,
            len(columns) - 1,
            {
                "name": "ResumenJornadas",
                "style": "Table Style Medium 2",
                "data": table_data,
                "columns": [
                    {"header": header, "format": _cell_format(formats, kind)}
                    for _key, header, kind in columns
                ],
            },
        )
        worksheet.freeze_panes(start_row + 2, 0)
    else:
        worksheet.write(start_row + 1, 0, "Sin jornadas registradas", formats["note"])

    return {
        "trip_count": int(trip_stats["count"] or 0),
        "incomplete_trip_count": int(incomplete["count"] or 0),
    }


def export_driver_control_xlsx(connection, destination, app_version):
    """Crea un XLSX con todos los datos operativos disponibles."""

    register_sqlite_finance_functions(connection)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    settings = _load_settings(connection)
    summaries = _session_summary(connection, settings)

    workbook = xlsxwriter.Workbook(
        str(destination),
        {"nan_inf_to_errors": True, "strings_to_urls": False},
    )
    workbook.set_properties(
        {
            "title": "Datos de Driver Control",
            "subject": "Jornadas, viajes, gastos y operación del vehículo",
            "author": "Driver Control",
            "company": "Driver Control",
            "comments": f"Exportado desde Driver Control {app_version}",
        }
    )
    formats = _formats(workbook)

    try:
        summary_stats = _write_summary(
            workbook, formats, connection, app_version, settings, summaries
        )

        sheets = []
        sheets.append(
            (
                "Jornadas",
                "Jornadas",
                [
                    ("id", "ID", "integer", 9),
                    ("opened_at", "Apertura", "date", 19),
                    ("closed_at", "Cierre", "date", 19),
                    ("status", "Estado", "text", 13),
                    ("opening_odometer", "Odómetro inicial", "number", 18),
                    ("current_odometer", "Último odómetro", "number", 18),
                    ("closing_odometer", "Odómetro final", "number", 18),
                    ("opening_cash", "Efectivo inicial", "money", 18),
                    ("closing_cash", "Efectivo final", "money", 18),
                    ("cash_expected", "Efectivo esperado", "money", 20),
                    ("cash_difference", "Diferencia de caja", "money", 20),
                ],
                _select(
                    connection,
                    "SELECT id, opened_at, closed_at, status, opening_odometer, "
                    "current_odometer, closing_odometer, opening_cash, closing_cash, cash_expected, "
                    "cash_difference FROM work_sessions ORDER BY id",
                ),
            )
        )
        close_rows = []
        if _table_exists(connection, "session_summaries"):
            close_rows = _select(
                connection,
                "SELECT session_id,income_total,trip_count,cash_collected,mp_collected,"
                "app_collected,uber_fee,uber_owes,driver_owes,confidence,source_mode,updated_at "
                "FROM session_summaries ORDER BY session_id",
            )
        summary_by_id = {row["id"]: row for row in summaries}
        for row in close_rows:
            if not summary_by_id.get(row["session_id"], {}).get("uber_fee_known", row["uber_fee"] > 0):
                row["uber_fee"] = None
        sheets.append(
            (
                "Cierres",
                "CierresInteligentes",
                [
                    ("session_id", "Jornada", "integer", 11),
                    ("income_total", "Ingresos registrados", "money", 21),
                    ("trip_count", "Viajes informados", "integer", 18),
                    ("cash_collected", "Cobrado en efectivo", "money", 20),
                    ("mp_collected", "Cobrado por Mercado Pago", "money", 25),
                    ("app_collected", "Cobrado por aplicación", "money", 22),
                    ("uber_fee", "Comisión Uber", "money", 18),
                    ("uber_owes", "Uber debe", "money", 16),
                    ("driver_owes", "Deuda con Uber", "money", 18),
                    ("confidence", "Confianza", "text", 15),
                    ("source_mode", "Origen", "text", 15),
                    ("updated_at", "Actualizado", "date", 19),
                ],
                close_rows,
            )
        )
        trip_rows = _select(
            connection,
            "SELECT id, session_id, created_at, amount, uber_fee, payment, km, duration, "
            "cash_received, change_given FROM trips ORDER BY id",
        )
        for row in trip_rows:
            row["known_billing"] = _as_float(row.get("amount")) + _as_float(row.get("uber_fee"))
        sheets.append(
            (
                "Viajes",
                "Viajes",
                [
                    ("id", "ID", "integer", 9),
                    ("session_id", "Jornada", "integer", 11),
                    ("created_at", "Fecha", "date", 19),
                    ("amount", "Ingreso registrado", "money", 19),
                    ("uber_fee", "Comisión Uber informada", "money", 23),
                    ("known_billing", "Facturación conocida", "money", 21),
                    ("payment", "Medio de cobro", "text", 19),
                    ("km", "Kilómetros", "number", 14),
                    ("duration", "Duración (min)", "integer", 16),
                    ("cash_received", "Dinero recibido", "money", 18),
                    ("change_given", "Vuelto entregado", "money", 18),
                ],
                trip_rows,
            )
        )
        expense_rows = _select(
            connection,
            "SELECT id, session_id, created_at, category, description, amount, "
            "payment FROM expenses ORDER BY id",
        )
        sheets.append(
            (
                "Gastos",
                "Gastos",
                [
                    ("id", "ID", "integer", 9),
                    ("session_id", "Jornada", "integer", 11),
                    ("created_at", "Fecha", "date", 19),
                    ("category", "Categoría", "text", 18),
                    ("description", "Descripción", "text", 30),
                    ("amount", "Monto", "money", 17),
                    ("payment", "Medio de pago", "text", 18),
                ],
                expense_rows,
            )
        )
        fuel_rows = _select(
            connection,
            "SELECT id, session_id, created_at, amount, liters, odometer, payment "
            "FROM fuel ORDER BY id",
        )
        for row in fuel_rows:
            liters = _as_float(row.get("liters"))
            row["unit_price"] = _as_float(row.get("amount")) / liters if liters else None
        sheets.append(
            (
                "Combustible",
                "Combustible",
                [
                    ("id", "ID", "integer", 9),
                    ("session_id", "Jornada", "integer", 11),
                    ("created_at", "Fecha", "date", 19),
                    ("amount", "Importe cargado", "money", 19),
                    ("liters", "Litros", "number", 13),
                    ("unit_price", "Precio por litro", "money", 18),
                    ("odometer", "Odómetro", "number", 15),
                    ("payment", "Medio de pago", "text", 18),
                ],
                fuel_rows,
            )
        )

        assessments = _select(
            connection,
            "SELECT id, created_at, fare, pickup_min, pickup_km, trip_min, trip_km, "
            "total_min, total_km, fuel_cost, net_est, hourly_est, per_km_est, score, "
            "recommendation, destination_rating, decision "
            "FROM trip_assessments ORDER BY id",
        )
        sheets.append(
            (
                "Evaluaciones",
                "Evaluaciones",
                [
                    ("id", "ID", "integer", 9),
                    ("created_at", "Fecha", "date", 19),
                    ("fare", "Oferta", "money", 15),
                    ("pickup_min", "Pickup (min)", "number", 15),
                    ("pickup_km", "Pickup (km)", "number", 15),
                    ("trip_min", "Viaje (min)", "number", 15),
                    ("trip_km", "Viaje (km)", "number", 15),
                    ("total_min", "Total (min)", "number", 14),
                    ("total_km", "Total (km)", "number", 14),
                    ("fuel_cost", "Costo combustible", "money", 20),
                    ("net_est", "Neto estimado", "money", 18),
                    ("hourly_est", "Estimado por hora", "money", 20),
                    ("per_km_est", "Estimado por km", "money", 19),
                    ("score", "Puntaje", "number", 12),
                    ("recommendation", "Recomendación", "text", 24),
                    ("destination_rating", "Destino", "text", 18),
                    ("decision", "Decisión", "text", 16),
                ],
                assessments,
            )
        )

        breaks = _select(
            connection,
            "SELECT id, session_id, started_at, ended_at FROM driver_breaks ORDER BY id",
        )
        for row in breaks:
            row["duration"] = _minutes_between(row.get("started_at"), row.get("ended_at"))
        sheets.append(
            (
                "Pausas",
                "Pausas",
                [
                    ("id", "ID", "integer", 9),
                    ("session_id", "Jornada", "integer", 11),
                    ("started_at", "Inicio", "date", 19),
                    ("ended_at", "Fin", "date", 19),
                    ("duration", "Duración (min)", "number", 17),
                ],
                breaks,
            )
        )
        fatigue = _select(
            connection,
            "SELECT id, session_id, created_at, level FROM fatigue_checkins ORDER BY id",
        )
        sheets.append(
            (
                "Fatiga",
                "Fatiga",
                [
                    ("id", "ID", "integer", 9),
                    ("session_id", "Jornada", "integer", 11),
                    ("created_at", "Fecha", "date", 19),
                    ("level", "Nivel (1 a 5)", "integer", 17),
                ],
                fatigue,
            )
        )

        maintenance_rows = []
        if _table_exists(connection, "maintenance_records"):
            maintenance_rows = _select(
                connection,
                "SELECT id,session_id,created_at,category,description,odometer,amount,"
                "next_due_date,next_due_odometer,payment,expense_id,status "
                "FROM maintenance_records ORDER BY id",
            )
        sheets.append(
            (
                "Mantenimiento",
                "Mantenimiento",
                [
                    ("id", "ID", "integer", 9),
                    ("session_id", "Jornada", "integer", 11),
                    ("created_at", "Fecha", "date", 19),
                    ("category", "Tipo", "text", 22),
                    ("description", "Detalle", "text", 32),
                    ("odometer", "Odómetro", "number", 15),
                    ("amount", "Costo", "money", 17),
                    ("next_due_date", "Próxima fecha", "text", 17),
                    ("next_due_odometer", "Próximo kilometraje", "number", 21),
                    ("payment", "Medio de pago", "text", 18),
                    ("expense_id", "Gasto vinculado", "integer", 17),
                    ("status", "Estado", "text", 16),
                ],
                maintenance_rows,
            )
        )

        setting_labels = {
            "daily_goal": "Meta diaria",
            "weekly_goal": "Meta semanal",
            "vehicle": "Vehículo",
            "fuel_consumption": "Consumo (L/100 km)",
            "fuel_price": "Precio de nafta ($/L)",
            "assistant_min_hourly": "Mínimo por hora",
            "assistant_min_per_km": "Mínimo por kilómetro",
            "assistant_max_pickup_km": "Pickup máximo (km)",
            "tank_capacity": "Capacidad del tanque (L)",
            "dark_mode": "Modo oscuro",
            "ai_server_url": "Servidor de IA",
            "ai_access_token": "Código de acceso de IA",
        }
        setting_rows = [
            {
                "setting": setting_labels.get(key, key),
                "value": "No exportado por seguridad"
                if key in SENSITIVE_SETTING_KEYS
                else settings[key],
            }
            for key in sorted(settings)
        ]
        sheets.append(
            (
                "Configuración",
                "Configuracion",
                [
                    ("setting", "Configuración", "text", 31),
                    ("value", "Valor", "text", 48),
                ],
                setting_rows,
            )
        )

        for title, table_name, columns, rows in sheets:
            _write_data_sheet(workbook, formats, title, table_name, columns, rows)

        return {
            "jornadas": len(summaries),
            "viajes": len(trip_rows),
            "gastos": len(expense_rows),
            "cargas": len(fuel_rows),
            "evaluaciones": len(assessments),
            "mantenimientos": len(maintenance_rows),
            "cierres": len(close_rows),
            "viajes_incompletos": summary_stats["incomplete_trip_count"],
        }
    finally:
        workbook.close()
