"""Exportación segura y completa de Driver Control a un libro de Excel."""

from datetime import datetime
from pathlib import Path

import xlsxwriter


DATETIME_FORMATS = (
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)

SENSITIVE_SETTING_KEYS = {"ai_access_token"}


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
            {"font_color": "#526174", "bold": True}
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
        return ""
    if kind in {"money", "number"}:
        return _as_float(value)
    if kind == "integer":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    return value


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
    if not _table_exists(connection, "work_sessions"):
        return []

    consumption = _as_float(settings.get("fuel_consumption"), 8.0)
    fuel_price = _as_float(settings.get("fuel_price"), 0.0)
    sessions = _select(
        connection,
        """
        SELECT id, opened_at, closed_at, status, opening_odometer,
               closing_odometer, opening_cash, closing_cash,
               cash_expected, cash_difference
          FROM work_sessions
         ORDER BY id
        """,
    )

    output = []
    for session in sessions:
        session_id = session["id"]
        trip = _select(
            connection,
            """
            SELECT COUNT(*) AS trips,
                   COALESCE(SUM(amount), 0) AS amount,
                   COALESCE(SUM(km), 0) AS trip_km
              FROM trips
             WHERE session_id=?
            """,
            (session_id,),
        )[0]
        expense = _select(
            connection,
            """
            SELECT COALESCE(SUM(CASE WHEN lower(category)!='combustible'
                                     THEN amount ELSE 0 END), 0) AS operating
              FROM expenses
             WHERE session_id=?
            """,
            (session_id,),
        )[0]

        opening_odometer = _as_float(session.get("opening_odometer"))
        closing_odometer = session.get("closing_odometer")
        if closing_odometer is None:
            worked_km = _as_float(trip.get("trip_km"))
        else:
            worked_km = max(_as_float(closing_odometer) - opening_odometer, 0.0)

        amount = _as_float(trip.get("amount"))
        operating = _as_float(expense.get("operating"))
        fuel_cost = worked_km * consumption / 100.0 * fuel_price
        output.append(
            {
                "id": session_id,
                "opened_at": session.get("opened_at"),
                "closed_at": session.get("closed_at"),
                "status": session.get("status"),
                "trips": trip.get("trips"),
                "amount": amount,
                "worked_km": worked_km,
                "operating": operating,
                "fuel_cost": fuel_cost,
                "estimated_result": amount - operating - fuel_cost,
                "cash_expected": session.get("cash_expected"),
                "cash_difference": session.get("cash_difference"),
            }
        )
    return output


def _write_summary(workbook, formats, connection, app_version, settings, summaries):
    worksheet = workbook.add_worksheet("Resumen")
    worksheet.set_tab_color("#173B67")
    worksheet.set_column("A:A", 31)
    worksheet.set_column("B:B", 20)
    worksheet.set_column("C:L", 17)
    worksheet.set_row(0, 34)
    worksheet.merge_range("A1:L1", "Driver Control - Exportación completa", formats["title"])

    trip_stats = _select(
        connection,
        "SELECT COUNT(*) AS count, COALESCE(SUM(amount),0) AS amount, "
        "COALESCE(SUM(km),0) AS km FROM trips",
    )[0]
    incomplete = _select(
        connection,
        "SELECT COUNT(*) AS count FROM trips WHERE km<=0 OR duration<=0",
    )[0]
    expense_stats = _select(
        connection,
        "SELECT COALESCE(SUM(CASE WHEN lower(category)!='combustible' "
        "THEN amount ELSE 0 END),0) AS operating FROM expenses",
    )[0]
    fuel_stats = _select(
        connection,
        "SELECT COALESCE(SUM(amount),0) AS amount, "
        "COALESCE(SUM(liters),0) AS liters FROM fuel",
    )[0]

    overview = [
        ("Generado", datetime.now(), "date"),
        ("Versión de la app", app_version, "text"),
        ("Jornadas registradas", len(summaries), "integer"),
        ("Viajes registrados", trip_stats["count"], "integer"),
        ("Importe registrado en viajes", trip_stats["amount"], "money"),
        ("Kilómetros cargados en viajes", trip_stats["km"], "number"),
        ("Otros gastos", expense_stats["operating"], "money"),
        ("Cargas de combustible", fuel_stats["amount"], "money"),
        ("Litros cargados", fuel_stats["liters"], "number"),
    ]
    worksheet.write("A3", "Resumen general", formats["section"])
    for row_index, (label, value, kind) in enumerate(overview, start=3):
        worksheet.write(row_index, 0, label, formats["label"])
        worksheet.write(row_index, 1, _prepare_value(value, kind), _cell_format(formats, kind))

    note_row = 13
    if int(incomplete["count"] or 0) > 0:
        worksheet.merge_range(
            note_row,
            0,
            note_row,
            11,
            f"Revisar {int(incomplete['count'])} viaje(s) con kilómetros o duración en cero.",
            formats["warning"],
        )
        note_row += 1

    worksheet.merge_range(
        note_row,
        0,
        note_row + 1,
        11,
        "Los importes se exportan tal como fueron registrados. El resultado operativo es una estimación: "
        "requiere que el monto de cada viaje represente el ingreso real del conductor. El costo de combustible "
        "usa el consumo y el precio configurados al momento de exportar.",
        formats["note"],
    )

    start_row = note_row + 4
    worksheet.write(start_row, 0, "Resumen por jornada", formats["section"])
    columns = [
        ("id", "Jornada", "integer"),
        ("opened_at", "Apertura", "date"),
        ("closed_at", "Cierre", "date"),
        ("status", "Estado", "text"),
        ("trips", "Viajes", "integer"),
        ("amount", "Importe registrado", "money"),
        ("worked_km", "Km trabajados", "number"),
        ("operating", "Otros gastos", "money"),
        ("fuel_cost", "Combustible consumido", "money"),
        ("estimated_result", "Resultado estimado", "money"),
        ("cash_expected", "Efectivo esperado", "money"),
        ("cash_difference", "Diferencia de caja", "money"),
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
                    ("closing_odometer", "Odómetro final", "number", 18),
                    ("opening_cash", "Efectivo inicial", "money", 18),
                    ("closing_cash", "Efectivo final", "money", 18),
                    ("cash_expected", "Efectivo esperado", "money", 20),
                    ("cash_difference", "Diferencia de caja", "money", 20),
                ],
                _select(
                    connection,
                    "SELECT id, opened_at, closed_at, status, opening_odometer, "
                    "closing_odometer, opening_cash, closing_cash, cash_expected, "
                    "cash_difference FROM work_sessions ORDER BY id",
                ),
            )
        )
        trip_rows = _select(
            connection,
            "SELECT id, session_id, created_at, amount, payment, km, duration, "
            "cash_received, change_given FROM trips ORDER BY id",
        )
        sheets.append(
            (
                "Viajes",
                "Viajes",
                [
                    ("id", "ID", "integer", 9),
                    ("session_id", "Jornada", "integer", 11),
                    ("created_at", "Fecha", "date", 19),
                    ("amount", "Monto registrado", "money", 19),
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

        setting_labels = {
            "daily_goal": "Meta diaria",
            "weekly_goal": "Meta semanal",
            "vehicle": "Vehículo",
            "fuel_consumption": "Consumo (L/100 km)",
            "fuel_price": "Precio de nafta ($/L)",
            "assistant_min_hourly": "Mínimo por hora",
            "assistant_min_per_km": "Mínimo por kilómetro",
            "assistant_max_pickup_km": "Pickup máximo (km)",
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
            "viajes_incompletos": summary_stats["incomplete_trip_count"],
        }
    finally:
        workbook.close()
