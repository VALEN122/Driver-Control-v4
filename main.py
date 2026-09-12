import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from kivy.lang import Builder
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget
from kivy.utils import platform
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import TwoLineListItem
from kivymd.uix.textfield import MDTextField

from insight_engine import rank_financial_insights


# ============================================================
# Driver Control v6.0.0
# Mejoras aplicadas:
# - Valor actual de nafta dinámico y persistente con respaldo histórico.
# - Exportación completa de datos operativos a un libro Excel.
# - Verificación preventiva de recursos gráficos (assets de billetes).
# - Prevención de micro-cortes y optimización en la gestión de jornadas.
# ============================================================

APP_NAME = "Driver Control"
APP_VERSION = "6.0.0"
DB_FILE = "driver_control.db"
DB_SCHEMA_VERSION = 2
DATE_FORMAT = "%d/%m/%Y"
DATETIME_FORMAT = "%d/%m/%Y %H:%M"
WEEKDAYS_ES = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)

DEFAULT_DAILY_GOAL = 70000.0
DEFAULT_WEEKLY_GOAL = 400000.0
DEFAULT_VEHICLE = "Volkswagen Gol Trend 2015"
DEFAULT_FUEL_CONSUMPTION = 8.0  # L/100 km
DEFAULT_FUEL_PRICE = 2048.0  # $/L; editable en Configuración
DEFAULT_ASSISTANT_MIN_HOURLY = 15000.0
DEFAULT_ASSISTANT_MIN_PER_KM = 300.0
DEFAULT_ASSISTANT_MAX_PICKUP_KM = 3.0
DEFAULT_TANK_CAPACITY = 55.0
DEFAULT_AI_SERVER_URL = ""
DEFAULT_AI_ACCESS_TOKEN = ""

PAYMENT_CASH = "Efectivo"
PAYMENT_MP = "Mercado Pago"
PAYMENT_UBER = "Uber"
PAYMENT_OTHER = "Otro"
PAYMENT_METHODS = (PAYMENT_CASH, PAYMENT_MP, PAYMENT_UBER, PAYMENT_OTHER)

MAX_HISTORY_ITEMS = 100

LOG_FILE = "driver_control.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)
LOGGER = logging.getLogger(APP_NAME)


KV = """
#:import dp kivy.metrics.dp

<StatCard@MDCard>:
    orientation: "vertical"
    padding: dp(14)
    spacing: dp(4)
    radius: [16,16,16,16]
    elevation: 1
    md_bg_color: app.card_color
    size_hint_y: None
    height: dp(105)

<MainNav>:
    active_screen: ""
    size_hint_y: None
    height: dp(68)
    padding: [dp(4), dp(4), dp(4), dp(6)]
    spacing: dp(0)
    md_bg_color: app.card_color

    MDFlatButton:
        text: "Inicio"
        size_hint_x: 1
        theme_text_color: "Custom"
        text_color: app.accent_color if root.active_screen == "dashboard" else app.muted_color
        on_release: app.go("dashboard")
    MDFlatButton:
        text: "Jornada"
        size_hint_x: 1
        theme_text_color: "Custom"
        text_color: app.accent_color if root.active_screen == "cash" else app.muted_color
        on_release: app.go_jornada()
    MDFlatButton:
        text: "Historial"
        size_hint_x: 1
        theme_text_color: "Custom"
        text_color: app.accent_color if root.active_screen == "trips" else app.muted_color
        on_release: app.go("trips")
    MDFlatButton:
        text: "Vehículo"
        size_hint_x: 1
        theme_text_color: "Custom"
        text_color: app.accent_color if root.active_screen == "wellness_map" else app.muted_color
        on_release: app.go("wellness_map")
    MDFlatButton:
        text: "Ajustes"
        size_hint_x: 1
        theme_text_color: "Custom"
        text_color: app.accent_color if root.active_screen == "settings" else app.muted_color
        on_release: app.go("settings")

ScreenManager:
    DashboardScreen:
    TripEntryScreen:
    TripsScreen:
    ExpensesScreen:
    FuelScreen:
    CashScreen:
    SmartCloseScreen:
    DayStoryScreen:
    SessionsScreen:
    TripAssistantScreen:
    WellnessMapScreen:
    MaintenanceScreen:
    SettingsScreen:

<DashboardScreen>:
    name: "dashboard"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Driver Control"
            md_bg_color: app.bg_color
            right_action_items: [["shield-check", lambda x: app.go("assistant")]]

        ScrollView:
            MDBoxLayout:
                orientation: "vertical"
                padding: [dp(16), dp(8), dp(16), dp(24)]
                spacing: dp(12)
                adaptive_height: True

                MDBoxLayout:
                    size_hint_y: None
                    height: dp(64)
                    spacing: dp(8)
                    MDBoxLayout:
                        orientation: "vertical"
                        size_hint_x: .62
                        MDLabel:
                            text: "Tu día al volante"
                            bold: True
                            font_style: "H6"
                            size_hint_y: None
                            height: dp(34)
                        MDLabel:
                            text: root.current_datetime_text
                            theme_text_color: "Custom"
                            text_color: app.muted_color
                            font_style: "Caption"
                            size_hint_y: None
                            height: dp(26)
                    MDFlatButton:
                        text: "HOY"
                        size_hint_x: .18
                        theme_text_color: "Custom"
                        text_color: app.accent_color if root.period_mode == "today" else app.muted_color
                        on_release: app.set_dashboard_period("today")
                    MDFlatButton:
                        text: "7 DÍAS"
                        size_hint_x: .20
                        theme_text_color: "Custom"
                        text_color: app.accent_color if root.period_mode == "week" else app.muted_color
                        on_release: app.set_dashboard_period("week")

                MDCard:
                    orientation: "vertical"
                    padding: dp(18)
                    spacing: dp(4)
                    radius: [22,22,22,22]
                    md_bg_color: app.primary_color
                    size_hint_y: None
                    height: dp(190)

                    MDLabel:
                        text: "GANANCIA REAL ESTIMADA · " + root.period_label.upper()
                        theme_text_color: "Custom"
                        text_color: app.primary_muted_text_color
                        font_style: "Caption"
                        size_hint_y: None
                        height: dp(24)

                    MDLabel:
                        text: root.net_text
                        theme_text_color: "Custom"
                        text_color: app.primary_text_color
                        font_style: "H3"
                        bold: True
                        size_hint_y: None
                        height: dp(62)

                    MDLabel:
                        text: root.net_explanation_text
                        theme_text_color: "Custom"
                        text_color: app.primary_muted_text_color
                        size_hint_y: None
                        text_size: self.width, None
                        height: dp(42)

                    MDLabel:
                        text: root.efficiency_text
                        theme_text_color: "Custom"
                        text_color: app.primary_text_color
                        bold: True
                        size_hint_y: None
                        height: dp(28)

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(6)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(374)

                    MDLabel:
                        text: "Así se forma tu ganancia"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(32)
                    MDBoxLayout:
                        orientation: "vertical"
                        spacing: dp(0)
                        size_hint_y: None
                        height: dp(240)

                        MDBoxLayout:
                            size_hint_y: None
                            height: dp(40)
                            MDLabel:
                                text: "Facturación conocida"
                                size_hint_x: .72
                                theme_text_color: "Custom"
                                text_color: app.muted_color
                            MDLabel:
                                text: root.revenue_text
                                size_hint_x: .28
                                halign: "right"
                                bold: True
                        MDBoxLayout:
                            size_hint_y: None
                            height: dp(40)
                            MDLabel:
                                text: "Ingresos registrados"
                                size_hint_x: .72
                                theme_text_color: "Custom"
                                text_color: app.muted_color
                            MDLabel:
                                text: root.income_text
                                size_hint_x: .28
                                halign: "right"
                                bold: True
                        MDBoxLayout:
                            size_hint_y: None
                            height: dp(40)
                            MDLabel:
                                text: "Comisión de Uber"
                                size_hint_x: .72
                                theme_text_color: "Custom"
                                text_color: app.muted_color
                            MDLabel:
                                text: root.commission_text
                                size_hint_x: .28
                                halign: "right"
                        MDBoxLayout:
                            size_hint_y: None
                            height: dp(40)
                            MDLabel:
                                text: "Nafta consumida"
                                size_hint_x: .72
                                theme_text_color: "Custom"
                                text_color: app.muted_color
                            MDLabel:
                                text: "− " + root.fuel_cost_text
                                size_hint_x: .28
                                halign: "right"
                        MDBoxLayout:
                            size_hint_y: None
                            height: dp(40)
                            MDLabel:
                                text: "Otros gastos"
                                size_hint_x: .72
                                theme_text_color: "Custom"
                                text_color: app.muted_color
                            MDLabel:
                                text: "− " + root.expenses_text
                                size_hint_x: .28
                                halign: "right"
                        MDBoxLayout:
                            size_hint_y: None
                            height: dp(40)
                            MDLabel:
                                text: "Viajes · kilómetros"
                                size_hint_x: .72
                                theme_text_color: "Custom"
                                text_color: app.muted_color
                            MDLabel:
                                text: root.trips_text + " · " + root.km_text
                                size_hint_x: .28
                                halign: "right"
                    MDLabel:
                        text: root.commission_help_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        text_size: self.width, None
                        size_hint_y: None
                        height: dp(54)

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(6)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(226)

                    MDLabel:
                        text: "Jornada"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(32)

                    MDLabel:
                        text: root.session_status_text
                        bold: True
                        size_hint_y: None
                        height: dp(30)
                    MDLabel:
                        text: root.session_time_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        size_hint_y: None
                        height: dp(32)
                    MDRaisedButton:
                        text: root.session_action_text
                        size_hint_y: None
                        height: dp(50)
                        md_bg_color: app.accent_color
                        on_release: app.toggle_work_session()
                    MDFlatButton:
                        text: "ACTUALIZAR ODÓMETRO"
                        size_hint_y: None
                        height: dp(42)
                        on_release: app.open_current_odometer_dialog()

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(5)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(246)

                    MDLabel:
                        text: "Ingresos de los últimos 7 días"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(32)
                    WeeklyBarChart:
                        values: root.week_values
                        selected_index: root.chart_selected_index
                        size_hint_y: None
                        height: dp(116)
                    MDGridLayout:
                        cols: 7
                        size_hint_y: None
                        height: dp(24)
                        MDLabel:
                            text: "L"
                            halign: "center"
                            font_style: "Caption"
                        MDLabel:
                            text: "M"
                            halign: "center"
                            font_style: "Caption"
                        MDLabel:
                            text: "X"
                            halign: "center"
                            font_style: "Caption"
                        MDLabel:
                            text: "J"
                            halign: "center"
                            font_style: "Caption"
                        MDLabel:
                            text: "V"
                            halign: "center"
                            font_style: "Caption"
                        MDLabel:
                            text: "S"
                            halign: "center"
                            font_style: "Caption"
                        MDLabel:
                            text: "D"
                            halign: "center"
                            font_style: "Caption"
                    MDLabel:
                        text: root.chart_detail_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        size_hint_y: None
                        height: dp(32)

                MDGridLayout:
                    cols: 2
                    spacing: dp(10)
                    size_hint_y: None
                    height: dp(118)
                    MDRaisedButton:
                        text: "¿ME CONVIENE?"
                        md_bg_color: app.accent_color
                        on_release: app.go("assistant")
                    MDRaisedButton:
                        text: "+ SUMAR VIAJE"
                        on_release: app.open_trip_dialog()
                    MDFlatButton:
                        text: "+ GASTO"
                        on_release: app.open_expense_dialog()
                    MDFlatButton:
                        text: "VUELTO / CAJA"
                        on_release: app.go("cash")

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(142)
                    MDLabel:
                        text: "Meta " + root.period_label.lower()
                        font_style: "H6"
                        bold: True
                    MDLabel:
                        text: root.goal_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                    MDProgressBar:
                        value: root.goal_percent
                        max: 100
                        size_hint_y: None
                        height: dp(7)
                    MDLabel:
                        text: root.daily_remaining_text
                        theme_text_color: "Custom"
                        text_color: root.goal_message_color
                        bold: True

        MainNav:
            active_screen: "dashboard"


<BanknoteTile>:
    orientation: "vertical"
    padding: dp(6)
    spacing: dp(4)
    radius: [14,14,14,14]
    md_bg_color: app.card_color
    size_hint_y: None
    height: dp(132)
    elevation: 1

    Image:
        source: root.image_source
        allow_stretch: True
        keep_ratio: True

    MDLabel:
        text: root.label_text
        halign: "center"
        bold: True
        size_hint_y: None
        height: dp(28)


<TripEntryScreen>:
    name: "new_trip"

    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Nuevo viaje"
            left_action_items: [["arrow-left", lambda x: app.cancel_new_trip()]]
            md_bg_color: app.bg_color

        ScrollView:
            do_scroll_x: False

            MDBoxLayout:
                orientation: "vertical"
                padding: [dp(14), dp(14), dp(14), dp(28)]
                spacing: dp(14)
                size_hint_y: None
                height: self.minimum_height

                MDLabel:
                    text: "Importe del viaje"
                    font_style: "H6"
                    bold: True
                    size_hint_y: None
                    height: dp(30)

                MDTextField:
                    id: trip_amount
                    hint_text: "Ingreso del conductor (ej: 7350)"
                    helper_text: "El monto que queda para vos, antes de nafta y gastos"
                    helper_text_mode: "on_focus"
                    input_filter: "float"
                    size_hint_y: None
                    height: dp(58)

                MDTextField:
                    id: trip_uber_fee
                    hint_text: "Comisión informada por Uber (opcional)"
                    helper_text: "Sirve para explicar la facturación; no se descuenta otra vez"
                    helper_text_mode: "on_focus"
                    input_filter: "float"
                    size_hint_y: None
                    height: dp(58)

                MDLabel:
                    text: "Método de pago"
                    font_style: "H6"
                    bold: True
                    size_hint_y: None
                    height: dp(30)

                MDGridLayout:
                    cols: 2
                    spacing: dp(8)
                    size_hint_y: None
                    height: dp(108)

                    MDRaisedButton:
                        text: "Efectivo"
                        md_bg_color: app.accent_color if root.payment_method == "Efectivo" else app.card_color
                        on_release: app.select_trip_payment("Efectivo")

                    MDRaisedButton:
                        text: "Mercado Pago"
                        md_bg_color: app.accent_color if root.payment_method == "Mercado Pago" else app.card_color
                        on_release: app.fast_save_payment("Mercado Pago")

                    MDRaisedButton:
                        text: "Uber"
                        md_bg_color: app.accent_color if root.payment_method == "Uber" else app.card_color
                        on_release: app.fast_save_payment("Uber")

                    MDRaisedButton:
                        text: "Otro"
                        md_bg_color: app.accent_color if root.payment_method == "Otro" else app.card_color
                        on_release: app.fast_save_payment("Otro")

                MDCard:
                    orientation: "vertical"
                    padding: dp(12)
                    spacing: dp(10)
                    radius: [16,16,16,16]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: self.minimum_height
                    opacity: 1 if root.payment_method == "Efectivo" else 0
                    disabled: root.payment_method != "Efectivo"

                    MDLabel:
                        text: "Cobro en efectivo"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(30)

                    MDRaisedButton:
                        text: "IMPORTE EXACTO"
                        size_hint_y: None
                        height: dp(52)
                        on_release: app.cash_exact_and_save()

                    MDLabel:
                        text: root.cash_received_text
                        font_style: "H4"
                        bold: True
                        size_hint_y: None
                        height: dp(48)

                    MDLabel:
                        text: root.change_preview_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "H6"
                        size_hint_y: None
                        height: dp(34)

                    MDGridLayout:
                        cols: 2
                        spacing: dp(8)
                        size_hint_y: None
                        height: dp(280)
                        row_default_height: dp(64)
                        row_force_default: True

                        MDRaisedButton:
                            text: "$1.000"
                            on_release: app.add_banknote(1000)
                        MDRaisedButton:
                            text: "$2.000"
                            on_release: app.add_banknote(2000)
                        MDRaisedButton:
                            text: "$10.000"
                            on_release: app.add_banknote(10000)
                        MDRaisedButton:
                            text: "$20.000"
                            on_release: app.add_banknote(20000)
                        MDFlatButton:
                            text: "$100"
                            on_release: app.add_banknote(100)
                        MDFlatButton:
                            text: "$200"
                            on_release: app.add_banknote(200)
                        MDFlatButton:
                            text: "$500"
                            on_release: app.add_banknote(500)
                        MDFlatButton:
                            text: "DESHACER"
                            on_release: app.undo_last_banknote()

                    MDRaisedButton:
                        text: "LISTO"
                        size_hint_y: None
                        height: dp(54)
                        on_release: app.save_trip_screen()

                MDLabel:
                    text: "Uber, Mercado Pago y Otro se guardan al tocarlos. La comisión queda separada del ingreso."
                    theme_text_color: "Custom"
                    text_color: app.muted_color
                    size_hint_y: None
                    text_size: self.width, None
                    height: self.texture_size[1] + dp(8)

                MDFlatButton:
                    text: "CANCELAR"
                    size_hint_y: None
                    height: dp(48)
                    on_release: app.cancel_new_trip()



<TripsScreen>:
    name: "trips"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Historial"
            md_bg_color: app.bg_color

        MDBoxLayout:
            size_hint_y: None
            height: dp(58)
            padding: [dp(12), dp(6), dp(12), dp(6)]
            spacing: dp(6)
            MDFlatButton:
                text: "VIAJES"
                theme_text_color: "Custom"
                text_color: app.accent_color
            MDFlatButton:
                text: "GASTOS"
                on_release: app.go("expenses")
            MDFlatButton:
                text: "JORNADAS"
                on_release: app.go("sessions")
            MDRaisedButton:
                text: "+ VIAJE"
                md_bg_color: app.accent_color
                on_release: app.open_trip_dialog()

        ScrollView:
            MDList:
                id: trips_list
                adaptive_height: True

        MainNav:
            active_screen: "trips"


<ExpensesScreen>:
    name: "expenses"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Gastos"
            left_action_items: [["arrow-left", lambda x: app.go("trips")]]
            md_bg_color: app.bg_color

        MDRaisedButton:
            text: "+ Cargar gasto"
            size_hint_y: None
            height: dp(48)
            on_release: app.open_expense_dialog()

        ScrollView:
            MDList:
                id: expenses_list
                adaptive_height: True


<FuelScreen>:
    name: "fuel"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Combustible"
            left_action_items: [["arrow-left", lambda x: app.go("wellness_map")]]
            md_bg_color: app.bg_color

        MDRaisedButton:
            text: "+ Cargar combustible"
            size_hint_y: None
            height: dp(48)
            on_release: app.open_fuel_dialog()

        MDFlatButton:
            text: "BORRAR ÚLTIMA CARGA"
            size_hint_y: None
            height: dp(44)
            on_release: app.confirm_delete_latest_fuel()

        MDLabel:
            text: "También podés tocar cualquier carga del historial para eliminarla."
            theme_text_color: "Custom"
            text_color: app.muted_color
            font_style: "Caption"
            size_hint_y: None
            height: dp(34)
            halign: "center"

        ScrollView:
            MDList:
                id: fuel_list
                adaptive_height: True


<CashScreen>:
    name: "cash"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Jornada"
            md_bg_color: app.bg_color

        ScrollView:
            do_scroll_x: False

            MDBoxLayout:
                orientation: "vertical"
                padding: [dp(16), dp(16), dp(16), dp(28)]
                spacing: dp(12)
                size_hint_y: None
                height: self.minimum_height

                MDLabel:
                    text: "Tu dinero de hoy"
                    font_style: "H5"
                    bold: True
                    size_hint_y: None
                    height: dp(44)

                MDCard:
                    orientation: "vertical"
                    padding: dp(18)
                    spacing: dp(5)
                    radius: [22,22,22,22]
                    md_bg_color: app.primary_color
                    size_hint_y: None
                    height: dp(150)
                    MDLabel:
                        text: "GANANCIA REAL ESTIMADA"
                        theme_text_color: "Custom"
                        text_color: app.primary_muted_text_color
                        font_style: "Caption"
                    MDLabel:
                        text: root.profit_text
                        theme_text_color: "Custom"
                        text_color: app.primary_text_color
                        font_style: "H3"
                        bold: True
                    MDLabel:
                        text: root.profit_detail_text
                        theme_text_color: "Custom"
                        text_color: app.primary_muted_text_color
                        font_style: "Caption"

                MDLabel:
                    text: "Cobros por método"
                    font_style: "H6"
                    bold: True
                    size_hint_y: None
                    height: dp(36)

                StatCard:
                    MDLabel:
                        text: "EFECTIVO"
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        size_hint_y: None
                        height: dp(28)
                    MDLabel:
                        text: root.cash_text
                        font_style: "H5"
                        bold: True
                        size_hint_y: None
                        height: dp(42)

                StatCard:
                    MDLabel:
                        text: "MERCADO PAGO"
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        size_hint_y: None
                        height: dp(28)
                    MDLabel:
                        text: root.mp_text
                        font_style: "H5"
                        bold: True
                        size_hint_y: None
                        height: dp(42)

                StatCard:
                    MDLabel:
                        text: "UBER"
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        size_hint_y: None
                        height: dp(28)
                    MDLabel:
                        text: root.uber_text
                        font_style: "H5"
                        bold: True
                        size_hint_y: None
                        height: dp(42)

                StatCard:
                    MDLabel:
                        text: "OTROS"
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        size_hint_y: None
                        height: dp(28)
                    MDLabel:
                        text: root.other_text
                        font_style: "H5"
                        bold: True
                        size_hint_y: None
                        height: dp(42)

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [16,16,16,16]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(252)

                    MDLabel:
                        text: "Detalle de efectivo"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(34)

                    MDLabel:
                        text: root.cash_received_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        size_hint_y: None
                        height: dp(30)

                    MDLabel:
                        text: root.change_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        size_hint_y: None
                        height: dp(30)

                    MDLabel:
                        text: root.cash_kept_text
                        bold: True
                        size_hint_y: None
                        height: dp(36)

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [16,16,16,16]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(116)

                    MDLabel:
                        text: "Ingresos registrados del día"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(34)

                    MDLabel:
                        text: root.total_text
                        font_style: "H5"
                        bold: True
                        size_hint_y: None
                        height: dp(42)

                MDLabel:
                    text: root.reconciliation_text
                    theme_text_color: "Custom"
                    text_color: app.accent_color if "Falta" in root.reconciliation_text else app.muted_color
                    bold: "Falta" in root.reconciliation_text
                    size_hint_y: None
                    text_size: self.width, None
                    height: self.texture_size[1] + dp(16)

                MDLabel:
                    text: "Cobrado indica por dónde entró el dinero. Ganancia real descuenta combustible y gastos; la comisión informada se muestra aparte."
                    theme_text_color: "Custom"
                    text_color: app.muted_color
                    size_hint_y: None
                    text_size: self.width, None
                    height: self.texture_size[1] + dp(20)

                MDRaisedButton:
                    text: root.session_action_text
                    size_hint_y: None
                    height: dp(52)
                    md_bg_color: app.accent_color
                    on_release: app.toggle_work_session()

                MDFlatButton:
                    text: "ACTUALIZAR ODÓMETRO"
                    size_hint_y: None
                    height: dp(48)
                    on_release: app.open_current_odometer_dialog()

        MainNav:
            active_screen: "cash"


<SmartCloseScreen>:
    name: "smart_close"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Cierre inteligente"
            left_action_items: [["arrow-left", lambda x: app.cancel_smart_close()]]
            md_bg_color: app.bg_color

        ScrollView:
            do_scroll_x: False

            MDBoxLayout:
                orientation: "vertical"
                padding: [dp(16), dp(12), dp(16), dp(32)]
                spacing: dp(12)
                size_hint_y: None
                height: self.minimum_height

                MDLabel:
                    text: "Cerrá tu día en menos de 90 segundos"
                    font_style: "H5"
                    bold: True
                    size_hint_y: None
                    height: dp(42)

                MDLabel:
                    text: "Usá los totales de Uber. No necesitás cargar ni entender cada viaje."
                    theme_text_color: "Custom"
                    text_color: app.muted_color
                    text_size: self.width, None
                    size_hint_y: None
                    height: self.texture_size[1] + dp(8)

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(330)

                    MDLabel:
                        text: "1 · Lo que generaste"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(34)

                    MDLabel:
                        text: "Buscá 'Tus ganancias' en Uber, no la facturación bruta."
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        text_size: self.width, None
                        size_hint_y: None
                        height: dp(42)

                    MDTextField:
                        id: close_income
                        hint_text: "Total que dice Uber ($)"
                        helper_text: "Puede ser el total del día, aunque no tengas los viajes"
                        helper_text_mode: "on_focus"
                        input_filter: "float"
                        size_hint_y: None
                        height: dp(58)

                    MDTextField:
                        id: close_trip_count
                        hint_text: "Cantidad de viajes (opcional)"
                        input_filter: "int"
                        size_hint_y: None
                        height: dp(58)

                    MDTextField:
                        id: close_cash_collected
                        hint_text: "Cobrado en efectivo (opcional)"
                        helper_text: "Es parte del total; no se suma dos veces"
                        helper_text_mode: "on_focus"
                        input_filter: "float"
                        size_hint_y: None
                        height: dp(58)

                MDRaisedButton:
                    text: "AGREGAR DETALLES" if not root.show_details else "OCULTAR DETALLES"
                    size_hint_y: None
                    height: dp(48)
                    on_release: app.toggle_smart_close_details()

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(466) if root.show_details else 0
                    opacity: 1 if root.show_details else 0
                    disabled: not root.show_details

                    MDLabel:
                        text: "Detalle opcional"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(34)

                    MDTextField:
                        id: close_mp_collected
                        hint_text: "Mercado Pago de esos viajes"
                        input_filter: "float"
                        size_hint_y: None
                        height: dp(58)

                    MDTextField:
                        id: close_app_collected
                        hint_text: "Transferido por Uber / la app"
                        helper_text: "Dejalo vacío si no aparece claramente"
                        helper_text_mode: "on_focus"
                        input_filter: "float"
                        size_hint_y: None
                        height: dp(58)

                    MDTextField:
                        id: close_uber_fee
                        hint_text: "Comisión que informa Uber"
                        helper_text: "Solo si aparece separada; no se descuenta otra vez"
                        helper_text_mode: "on_focus"
                        input_filter: "float"
                        size_hint_y: None
                        height: dp(58)

                    MDTextField:
                        id: close_uber_owes
                        hint_text: "Uber te debe ($)"
                        input_filter: "float"
                        size_hint_y: None
                        height: dp(58)

                    MDTextField:
                        id: close_driver_owes
                        hint_text: "Vos debés pagarle a Uber ($)"
                        input_filter: "float"
                        size_hint_y: None
                        height: dp(58)

                    MDLabel:
                        text: "Completá solo lo que reconozcas. Podés dejar cualquier detalle vacío."
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        text_size: self.width, None
                        size_hint_y: None
                        height: dp(50)

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(326)

                    MDLabel:
                        text: "2 · Kilómetros y caja"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(34)

                    MDLabel:
                        text: root.registered_costs_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        text_size: self.width, None
                        size_hint_y: None
                        height: dp(54)

                    MDTextField:
                        id: close_odometer
                        hint_text: "Odómetro final"
                        input_filter: "float"
                        size_hint_y: None
                        height: dp(58)

                    MDTextField:
                        id: close_cash_counted
                        hint_text: "Efectivo contado (opcional)"
                        helper_text: "Dejalo vacío si hoy no querés conciliar la caja"
                        helper_text_mode: "on_focus"
                        input_filter: "float"
                        size_hint_y: None
                        height: dp(58)

                    MDGridLayout:
                        cols: 2
                        spacing: dp(8)
                        size_hint_y: None
                        height: dp(52)

                        MDFlatButton:
                            text: "+ GASTO"
                            on_release: app.open_expense_dialog()

                        MDFlatButton:
                            text: "+ NAFTA"
                            on_release: app.open_fuel_dialog()

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(190)

                    MDLabel:
                        text: "3 · ¿Qué tan completo quedó?"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(34)

                    MDLabel:
                        text: "Elegí “Parcial” si Uber no muestra algún dato. El cierre se guarda igual."
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        text_size: self.width, None
                        size_hint_y: None
                        height: dp(50)

                    MDGridLayout:
                        cols: 2
                        spacing: dp(8)
                        size_hint_y: None
                        height: dp(52)

                        MDRaisedButton:
                            text: "COMPLETO"
                            md_bg_color: app.accent_color if root.data_confidence == "CONFIRMED" else app.card_color
                            on_release: app.select_close_confidence("CONFIRMED")

                        MDRaisedButton:
                            text: "PARCIAL"
                            md_bg_color: app.accent_color if root.data_confidence == "PARTIAL" else app.card_color
                            on_release: app.select_close_confidence("PARTIAL")

                MDRaisedButton:
                    text: "CERRAR Y VER MI RESULTADO"
                    size_hint_y: None
                    height: dp(56)
                    md_bg_color: app.accent_color
                    on_release: app.save_smart_close()

                MDFlatButton:
                    text: "VOLVER SIN CERRAR"
                    size_hint_y: None
                    height: dp(48)
                    on_release: app.cancel_smart_close()


<DayStoryScreen>:
    name: "day_story"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Tu jornada"
            md_bg_color: app.bg_color

        ScrollView:
            do_scroll_x: False

            MDBoxLayout:
                orientation: "vertical"
                padding: [dp(16), dp(12), dp(16), dp(32)]
                spacing: dp(12)
                size_hint_y: None
                height: self.minimum_height

                MDLabel:
                    text: root.title_text
                    font_style: "H5"
                    bold: True
                    size_hint_y: None
                    height: dp(44)

                MDCard:
                    orientation: "vertical"
                    padding: dp(18)
                    spacing: dp(6)
                    radius: [22,22,22,22]
                    md_bg_color: app.primary_color
                    size_hint_y: None
                    height: dp(206)

                    MDLabel:
                        text: root.confidence_text
                        theme_text_color: "Custom"
                        text_color: app.primary_muted_text_color
                        font_style: "Caption"
                        size_hint_y: None
                        height: dp(26)

                    MDLabel:
                        text: root.net_text
                        theme_text_color: "Custom"
                        text_color: app.primary_text_color
                        font_style: "H3"
                        bold: True
                        size_hint_y: None
                        height: dp(64)

                    MDLabel:
                        text: "Esto quedó realmente para vos"
                        theme_text_color: "Custom"
                        text_color: app.primary_text_color
                        bold: True
                        size_hint_y: None
                        height: dp(30)

                    MDLabel:
                        text: root.equation_text
                        theme_text_color: "Custom"
                        text_color: app.primary_muted_text_color
                        font_style: "Caption"
                        text_size: self.width, None
                        size_hint_y: None
                        height: dp(50)

                MDGridLayout:
                    cols: 2
                    spacing: dp(10)
                    size_hint_y: None
                    height: dp(105)

                    StatCard:
                        MDLabel:
                            text: "POR HORA"
                            theme_text_color: "Custom"
                            text_color: app.muted_color
                            font_style: "Caption"
                        MDLabel:
                            text: root.hourly_text
                            font_style: "H6"
                            bold: True

                    StatCard:
                        MDLabel:
                            text: "POR KM"
                            theme_text_color: "Custom"
                            text_color: app.muted_color
                            font_style: "Caption"
                        MDLabel:
                            text: root.per_km_text
                            font_style: "H6"
                            bold: True

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(196)

                    MDLabel:
                        text: root.insight_title
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(38)

                    MDLabel:
                        text: root.insight_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        text_size: self.width, None
                        size_hint_y: None
                        height: dp(58)

                    MDLabel:
                        text: root.next_action_text
                        bold: True
                        text_size: self.width, None
                        size_hint_y: None
                        height: dp(58)

                MDLabel:
                    text: root.why_text
                    theme_text_color: "Custom"
                    text_color: app.muted_color
                    font_style: "Caption"
                    text_size: self.width, None
                    size_hint_y: None
                    height: self.texture_size[1] + dp(12)

                MDRaisedButton:
                    text: "VOLVER AL INICIO"
                    size_hint_y: None
                    height: dp(56)
                    md_bg_color: app.accent_color
                    on_release: app.finish_day_story()


<SessionsScreen>:
    name: "sessions"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Jornadas"
            left_action_items: [["arrow-left", lambda x: app.go("trips")]]
            md_bg_color: app.bg_color

        MDBoxLayout:
            orientation: "vertical"
            padding: [dp(16), dp(10), dp(16), dp(6)]
            spacing: dp(4)
            size_hint_y: None
            height: dp(72)

            MDLabel:
                text: "Cada jornada tiene su propio resumen"
                bold: True
            MDLabel:
                text: "Tocá una jornada para ver caja, km, nafta y ganancia."
                theme_text_color: "Custom"
                text_color: app.muted_color
                font_style: "Caption"

        ScrollView:
            MDList:
                id: sessions_list



<TripAssistantScreen>:
    name: "assistant"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Asistente de viajes"
            left_action_items: [["arrow-left", lambda x: app.go("dashboard")]]
            md_bg_color: app.bg_color

        ScrollView:
            MDBoxLayout:
                orientation: "vertical"
                padding: dp(16)
                spacing: dp(12)
                adaptive_height: True

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(6)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(112)

                    MDLabel:
                        text: "Evaluación rápida"
                        font_style: "H6"
                        bold: True
                    MDLabel:
                        text: "Cargá los datos que muestra Uber. Driver Control calcula costo, $/h y $/km."
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"

                MDCard:
                    orientation: "vertical"
                    padding: dp(18)
                    spacing: dp(5)
                    radius: [22,22,22,22]
                    md_bg_color: root.recommendation_surface_color
                    size_hint_y: None
                    height: dp(184)
                    MDLabel:
                        text: "DECISIÓN DEL VIAJE"
                        theme_text_color: "Custom"
                        text_color: app.primary_muted_text_color
                        font_style: "Caption"
                    MDLabel:
                        text: root.recommendation_text
                        font_style: "H4"
                        bold: True
                        theme_text_color: "Custom"
                        text_color: app.primary_text_color
                    MDLabel:
                        text: root.summary_text
                        theme_text_color: "Custom"
                        text_color: app.primary_text_color
                        bold: True
                    MDLabel:
                        text: "Factor decisivo: " + root.reason_text
                        theme_text_color: "Custom"
                        text_color: app.primary_muted_text_color
                        font_style: "Caption"
                        text_size: self.width, None

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(392)

                    MDLabel:
                        text: "Flotante compacto sobre Uber"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(34)

                    MDLabel:
                        text: "Muestra decisión, ganancia, $/km, $/hora y el factor principal sin tapar los controles. Configurá esto con el vehículo detenido."
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        size_hint_y: None
                        height: dp(66)

                    MDRaisedButton:
                        text: "ACTIVAR ASISTENTE + VUELTO"
                        size_hint_y: None
                        height: dp(50)
                        on_release: app.request_uber_overlay_access()

                    MDRaisedButton:
                        text: "LECTURA VISUAL AUTOMÁTICA"
                        size_hint_y: None
                        height: dp(50)
                        on_release: app.request_uber_accessibility()

                    MDRaisedButton:
                        text: "LECTURA VISUAL CON GEMINI"
                        size_hint_y: None
                        height: dp(50)
                        on_release: app.request_gemini_visual_accessibility()

                    MDFlatButton:
                        text: "DETENER FLOTANTE"
                        size_hint_y: None
                        height: dp(44)
                        on_release: app.stop_driver_overlay()

                MDTextField:
                    id: assistant_fare
                    hint_text: "Tarifa ofrecida ($)"
                    input_filter: "float"

                MDGridLayout:
                    cols: 2
                    adaptive_height: True
                    spacing: dp(10)

                    MDTextField:
                        id: assistant_pickup_min
                        hint_text: "Min para buscar"
                        input_filter: "float"

                    MDTextField:
                        id: assistant_pickup_km
                        hint_text: "Km para buscar"
                        input_filter: "float"

                    MDTextField:
                        id: assistant_trip_min
                        hint_text: "Min del viaje"
                        input_filter: "float"

                    MDTextField:
                        id: assistant_trip_km
                        hint_text: "Km del viaje"
                        input_filter: "float"

                MDLabel:
                    text: "Zona de destino"
                    bold: True
                    size_hint_y: None
                    height: dp(28)

                MDBoxLayout:
                    adaptive_height: True
                    spacing: dp(8)

                    MDFlatButton:
                        text: "Mala"
                        on_release: app.set_assistant_destination("Mala")
                    MDFlatButton:
                        text: "Normal"
                        on_release: app.set_assistant_destination("Normal")
                    MDFlatButton:
                        text: "Buena"
                        on_release: app.set_assistant_destination("Buena")

                MDLabel:
                    text: "Seleccionada: " + root.destination_rating
                    theme_text_color: "Custom"
                    text_color: app.muted_color
                    size_hint_y: None
                    height: dp(26)

                MDRaisedButton:
                    text: "ANALIZAR VIAJE"
                    size_hint_y: None
                    height: dp(54)
                    on_release: app.analyze_trip_offer()

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(300)

                    MDLabel:
                        text: "IA avanzada"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(34)

                    MDLabel:
                        text: root.ai_status_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        size_hint_y: None
                        height: dp(38)

                    MDTextField:
                        id: assistant_ai_question
                        hint_text: "Pregunta para el asistente"
                        text: "¿Conviene aceptar este viaje y por qué?"

                    MDRaisedButton:
                        text: "CONSULTAR IA"
                        size_hint_y: None
                        height: dp(52)
                        md_bg_color: app.accent_color
                        on_release: app.analyze_trip_with_ai()

                    MDLabel:
                        text: root.ai_response_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        size_hint_y: None
                        height: dp(100)

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(7)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(260)

                    MDLabel:
                        text: "Detalle del cálculo"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(40)

                    MDLabel:
                        text: root.summary_text
                        bold: True
                        size_hint_y: None
                        height: dp(34)

                    MDLabel:
                        text: root.metrics_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        size_hint_y: None
                        height: dp(94)

                    MDLabel:
                        text: root.reason_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        size_hint_y: None
                        height: dp(68)

                MDLabel:
                    text: "La recomendación es orientativa. Vos decidís si aceptar o rechazar."
                    theme_text_color: "Custom"
                    text_color: app.muted_color
                    font_style: "Caption"
                    size_hint_y: None
                    height: dp(34)

                Widget:
                    size_hint_y: None
                    height: dp(28)


<WellnessMapScreen>:
    name: "wellness_map"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Vehículo"
            md_bg_color: app.bg_color

        ScrollView:
            MDBoxLayout:
                orientation: "vertical"
                padding: [dp(16), dp(8), dp(16), dp(24)]
                spacing: dp(12)
                adaptive_height: True

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(5)
                    radius: [22,22,22,22]
                    md_bg_color: app.primary_color
                    size_hint_y: None
                    height: dp(142)
                    MDLabel:
                        text: "TU AUTO"
                        theme_text_color: "Custom"
                        text_color: app.primary_muted_text_color
                        font_style: "Caption"
                    MDLabel:
                        text: root.vehicle_text
                        theme_text_color: "Custom"
                        text_color: app.primary_text_color
                        font_style: "H5"
                        bold: True
                    MDLabel:
                        text: root.vehicle_cost_text
                        theme_text_color: "Custom"
                        text_color: app.primary_muted_text_color

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(286)
                    MDLabel:
                        text: "¿Cuánto cargar?"
                        font_style: "H6"
                        bold: True
                    MDLabel:
                        text: "Indicá lo que marca el tablero. La cuenta usa la capacidad y el precio configurados."
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                    MDTextField:
                        id: tank_percent
                        hint_text: "Combustible actual (%)"
                        input_filter: "float"
                    MDBoxLayout:
                        size_hint_y: None
                        height: dp(44)
                        spacing: dp(6)
                        MDFlatButton:
                            text: "25%"
                            on_release: app.set_tank_percent(25)
                        MDFlatButton:
                            text: "50%"
                            on_release: app.set_tank_percent(50)
                        MDFlatButton:
                            text: "75%"
                            on_release: app.set_tank_percent(75)
                    MDRaisedButton:
                        text: "CALCULAR CARGA"
                        size_hint_y: None
                        height: dp(48)
                        md_bg_color: app.accent_color
                        on_release: app.calculate_refuel()
                    MDLabel:
                        text: root.refuel_result_text
                        bold: True
                        size_hint_y: None
                        height: dp(34)

                MDGridLayout:
                    cols: 2
                    spacing: dp(10)
                    size_hint_y: None
                    height: dp(108)
                    MDRaisedButton:
                        text: "+ CARGA"
                        on_release: app.open_fuel_dialog()
                    MDRaisedButton:
                        text: "VER CARGAS"
                        on_release: app.go("fuel")
                    MDFlatButton:
                        text: "ESTACIONES CERCA"
                        on_release: app.open_map("estaciones de servicio cercanas")
                    MDFlatButton:
                        text: "ÁREA DE DESCANSO"
                        on_release: app.open_map("área de descanso cercana")

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(168)
                    MDLabel:
                        text: "Mantenimiento"
                        font_style: "H6"
                        bold: True
                    MDLabel:
                        text: root.next_maintenance_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        text_size: self.width, None
                    MDRaisedButton:
                        text: "ABRIR MANTENIMIENTO"
                        size_hint_y: None
                        height: dp(50)
                        on_release: app.go("maintenance")

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(7)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(194)

                    MDLabel:
                        text: root.fatigue_title
                        font_style: "H6"
                        bold: True
                    MDLabel:
                        text: root.fatigue_message
                        theme_text_color: "Custom"
                        text_color: root.fatigue_color
                    MDLabel:
                        text: root.work_time_text
                        bold: True
                    MDLabel:
                        text: root.break_time_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color

                MDRaisedButton:
                    text: root.break_action_text
                    size_hint_y: None
                    height: dp(58)
                    md_bg_color: root.break_action_color
                    on_release: app.toggle_break()

                MDLabel:
                    text: "¿Cómo te sentís ahora?"
                    font_style: "H6"
                    bold: True
                    size_hint_y: None
                    height: dp(34)

                MDGridLayout:
                    cols: 3
                    spacing: dp(8)
                    adaptive_height: True
                    MDRaisedButton:
                        text: "Bien"
                        height: dp(52)
                        on_release: app.record_fatigue(1)
                    MDRaisedButton:
                        text: "Cansado"
                        height: dp(52)
                        on_release: app.record_fatigue(3)
                    MDRaisedButton:
                        text: "Muy cansado"
                        height: dp(52)
                        md_bg_color: (0.85, 0.35, 0.2, 1)
                        on_release: app.record_fatigue(5)

        MainNav:
            active_screen: "wellness_map"

<MaintenanceScreen>:
    name: "maintenance"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Mantenimiento"
            left_action_items: [["arrow-left", lambda x: app.go("wellness_map")]]
            md_bg_color: app.bg_color

        MDCard:
            orientation: "vertical"
            padding: dp(16)
            spacing: dp(5)
            radius: [0,0,18,18]
            md_bg_color: app.primary_color
            size_hint_y: None
            height: dp(126)
            MDLabel:
                text: "PRÓXIMO CONTROL"
                theme_text_color: "Custom"
                text_color: app.primary_muted_text_color
                font_style: "Caption"
            MDLabel:
                text: root.next_due_text
                theme_text_color: "Custom"
                text_color: app.primary_text_color
                font_style: "H6"
                bold: True
            MDLabel:
                text: "Registrá aceite, filtros, frenos, cubiertas y reparaciones."
                theme_text_color: "Custom"
                text_color: app.primary_muted_text_color
                font_style: "Caption"

        MDRaisedButton:
            text: "+ REGISTRAR MANTENIMIENTO"
            size_hint_y: None
            height: dp(54)
            md_bg_color: app.accent_color
            on_release: app.open_maintenance_dialog()

        ScrollView:
            MDList:
                id: maintenance_list
                adaptive_height: True

<SettingsScreen>:
    name: "settings"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Ajustes"
            md_bg_color: app.bg_color

        ScrollView:
            MDBoxLayout:
                orientation: "vertical"
                padding: dp(16)
                spacing: dp(12)
                adaptive_height: True

                MDLabel:
                    text: "Objetivos"
                    font_style: "H6"
                    bold: True
                    size_hint_y: None
                    height: dp(34)

                MDTextField:
                    id: daily_goal
                    hint_text: "Meta diaria ($)"
                    input_filter: "float"

                MDTextField:
                    id: weekly_goal
                    hint_text: "Meta semanal ($)"
                    input_filter: "float"

                MDTextField:
                    id: vehicle
                    hint_text: "Vehículo"

                MDTextField:
                    id: fuel_consumption
                    hint_text: "Consumo del auto (L/100 km)"
                    input_filter: "float"

                MDTextField:
                    id: fuel_price
                    hint_text: "Precio actual de nafta ($/L)"
                    helper_text: "Actualizado automáticamente en cálculos"
                    helper_text_mode: "on_focus"
                    input_filter: "float"

                MDTextField:
                    id: tank_capacity
                    hint_text: "Capacidad del tanque (L)"
                    helper_text: "Se usa solamente para calcular cuánto cargar"
                    helper_text_mode: "on_focus"
                    input_filter: "float"

                MDLabel:
                    text: "Asistente de viajes"
                    font_style: "H6"
                    bold: True
                    size_hint_y: None
                    height: dp(34)

                MDTextField:
                    id: assistant_min_hourly
                    hint_text: "Mínimo deseado por hora ($/h)"
                    input_filter: "float"

                MDTextField:
                    id: assistant_min_per_km
                    hint_text: "Mínimo deseado por km ($/km)"
                    input_filter: "float"

                MDTextField:
                    id: assistant_max_pickup_km
                    hint_text: "Pickup máximo deseado (km)"
                    input_filter: "float"

                MDLabel:
                    text: "Conexión con IA"
                    font_style: "H6"
                    bold: True
                    size_hint_y: None
                    height: dp(34)

                MDTextField:
                    id: ai_server_url
                    hint_text: "Dirección segura del servidor de IA"
                    helper_text: "Ejemplo: https://tu-servidor.com"
                    helper_text_mode: "on_focus"

                MDTextField:
                    id: ai_access_token
                    hint_text: "Código de acceso del dispositivo"
                    password: True
                    helper_text: "No es la clave de OpenAI"
                    helper_text_mode: "on_focus"

                MDLabel:
                    text: "Apariencia y permisos"
                    font_style: "H6"
                    bold: True
                    size_hint_y: None
                    height: dp(34)

                MDFlatButton:
                    text: root.theme_action_text
                    size_hint_y: None
                    height: dp(48)
                    on_release: app.toggle_theme()

                MDGridLayout:
                    cols: 2
                    spacing: dp(8)
                    size_hint_y: None
                    height: dp(104)
                    MDFlatButton:
                        text: "PERMISO FLOTANTE"
                        on_release: app.request_uber_overlay_access()
                    MDFlatButton:
                        text: "LECTURA DE UBER"
                        on_release: app.request_uber_accessibility()
                    MDFlatButton:
                        text: "GEMINI VISUAL"
                        on_release: app.request_gemini_visual_accessibility()
                    MDFlatButton:
                        text: "DETENER FLOTANTE"
                        on_release: app.stop_driver_overlay()

                MDRaisedButton:
                    text: "Guardar configuración"
                    on_release: app.save_settings()

                MDRaisedButton:
                    text: "EXPORTAR Y COMPARTIR EXCEL"
                    md_bg_color: app.accent_color
                    on_release: app.export_database_to_xlsx()

                Widget:
                    size_hint_y: None
                    height: dp(40)

        MainNav:
            active_screen: "settings"
"""


class MainNav(MDBoxLayout):
    active_screen = StringProperty("")


class WeeklyBarChart(Widget):
    """Gráfico liviano de siete barras, apto para teléfonos económicos."""

    values = ListProperty([0.0] * 7)
    selected_index = NumericProperty(6)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(
            pos=self._schedule_redraw,
            size=self._schedule_redraw,
            values=self._schedule_redraw,
            selected_index=self._schedule_redraw,
        )
        Clock.schedule_once(self._redraw, 0)

    def _schedule_redraw(self, *_args):
        Clock.schedule_once(self._redraw, 0)

    def _redraw(self, *_args):
        if self.width <= 0 or self.height <= 0:
            return
        values = [max(0.0, float(value or 0.0)) for value in self.values[:7]]
        values += [0.0] * (7 - len(values))
        peak = max(max(values), 1.0)
        gap = dp(8)
        bar_width = max(dp(8), (self.width - gap * 8) / 7.0)
        usable_height = max(dp(20), self.height - dp(12))
        app = MDApp.get_running_app()
        normal = getattr(app, "chart_color", (0.34, 0.68, 0.82, 1))
        selected = getattr(app, "accent_color", (0.0, 0.62, 0.86, 1))
        self.canvas.clear()
        with self.canvas:
            for index, value in enumerate(values):
                height = max(dp(8), usable_height * value / peak)
                rgba = selected if index == int(self.selected_index) else normal
                Color(*rgba)
                RoundedRectangle(
                    pos=(self.x + gap + index * (bar_width + gap), self.y),
                    size=(bar_width, height),
                    radius=[dp(5)],
                )

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        relative_x = max(0.0, min(touch.x - self.x, self.width - 1))
        index = min(6, int(relative_x / max(self.width / 7.0, 1.0)))
        app = MDApp.get_running_app()
        if app is not None:
            app.select_chart_day(index)
        return True


class DashboardScreen(Screen):
    current_datetime_text = StringProperty("")
    period_mode = StringProperty("today")
    period_label = StringProperty("Hoy")
    session_status_text = StringProperty("Jornada cerrada")
    session_time_text = StringProperty("Abrí una jornada para empezar")
    session_action_text = StringProperty("ABRIR JORNADA")
    fuel_used_text = StringProperty("Consumido: 0,00 L · $0")
    fuel_reserve_text = StringProperty("A reponer: $0")
    revenue_text = StringProperty("$0")
    income_text = StringProperty("$0")
    commission_text = StringProperty("$0")
    commission_help_text = StringProperty("Cargá la comisión solo si Uber te la informa.")
    fuel_cost_text = StringProperty("$0")
    expenses_text = StringProperty("$0")
    net_text = StringProperty("$0")
    net_explanation_text = StringProperty("Ingresos menos combustible y otros gastos")
    efficiency_text = StringProperty("$0 por hora · $0 por km")
    km_text = StringProperty("0 km")
    trips_text = StringProperty("0")
    goal_text = StringProperty("$0 / $0")
    goal_percent = NumericProperty(0)
    daily_remaining_text = StringProperty("Faltan $0")
    goal_message_color = ListProperty([0.32, 0.38, 0.45, 1])
    weekly_goal_text = StringProperty("$0 / $0")
    weekly_goal_percent = NumericProperty(0)
    weekly_remaining_text = StringProperty("Faltan $0")
    week_values = ListProperty([0.0] * 7)
    chart_selected_index = NumericProperty(6)
    chart_detail_text = StringProperty("Tocá una barra para ver el día")


class BanknoteTile(MDCard):
    image_source = StringProperty("")
    label_text = StringProperty("")
    value = NumericProperty(0)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            app = MDApp.get_running_app()
            if app is not None:
                app.add_banknote(self.value)
            return True
        return super().on_touch_down(touch)


class TripEntryScreen(Screen):
    payment_method = StringProperty(PAYMENT_UBER)
    cash_received_value = NumericProperty(0)
    cash_received_text = StringProperty("$0")
    change_preview_text = StringProperty("Vuelto: $0")
    cash_bill_stack = []

    def on_pre_enter(self, *args):
        self.cash_received_text = self._format_cash(self.cash_received_value)

    @staticmethod
    def _format_cash(value):
        return f"${float(value):,.0f}".replace(",", ".")


class TripsScreen(Screen):
    pass


class ExpensesScreen(Screen):
    pass


class FuelScreen(Screen):
    pass


class CashScreen(Screen):
    cash_text = StringProperty("$0")
    mp_text = StringProperty("$0")
    uber_text = StringProperty("$0")
    other_text = StringProperty("$0")
    cash_received_text = StringProperty("Recibido: $0")
    change_text = StringProperty("Vuelto entregado: $0")
    cash_kept_text = StringProperty("Efectivo neto por viajes: $0")
    total_text = StringProperty("$0")
    profit_text = StringProperty("$0")
    profit_detail_text = StringProperty("Ingresos menos combustible y gastos")
    reconciliation_text = StringProperty("Todos los cobros conocidos están clasificados.")
    session_action_text = StringProperty("ABRIR JORNADA")


class SmartCloseScreen(Screen):
    show_details = BooleanProperty(False)
    data_confidence = StringProperty("PARTIAL")
    registered_costs_text = StringProperty(
        "Todavía no hay gastos ni cargas registrados en esta jornada."
    )


class DayStoryScreen(Screen):
    title_text = StringProperty("¡Jornada cerrada!")
    confidence_text = StringProperty("CIERRE PARCIAL · NAFTA ESTIMADA")
    net_text = StringProperty("$0")
    equation_text = StringProperty("$0 ingresos − $0 nafta − $0 gastos")
    hourly_text = StringProperty("$0/h")
    per_km_text = StringProperty("$0/km")
    insight_title = StringProperty("Ya sabés qué te quedó")
    insight_text = StringProperty("Tu jornada quedó guardada.")
    next_action_text = StringProperty("Usá este resultado como referencia mañana.")
    why_text = StringProperty("Te mostramos esto porque acabás de cerrar la jornada.")


class SessionsScreen(Screen):
    pass


class TripAssistantScreen(Screen):
    destination_rating = StringProperty("Normal")
    recommendation_text = StringProperty("Cargá un viaje para analizar")
    summary_text = StringProperty("Todavía no hay evaluación")
    metrics_text = StringProperty("Tarifa · tiempo · kilómetros · combustible")
    reason_text = StringProperty("La app comparará el viaje con tus objetivos.")
    recommendation_color = ListProperty([0.10, 0.55, 0.25, 1])
    recommendation_surface_color = ListProperty([0.08, 0.16, 0.26, 1])
    ai_status_text = StringProperty("Configurá el servidor para activar la IA.")
    ai_response_text = StringProperty("La IA explicará la decisión sin aceptar el viaje por vos.")


class WellnessMapScreen(Screen):
    vehicle_text = StringProperty(DEFAULT_VEHICLE)
    vehicle_cost_text = StringProperty("8,0 L/100 km · $0 por litro")
    refuel_result_text = StringProperty("Elegí un nivel para calcular")
    next_maintenance_text = StringProperty("Todavía no hay controles registrados.")
    fatigue_title = StringProperty("Sin jornada activa")
    fatigue_message = StringProperty("Abrí una jornada para activar el acompañamiento.")
    fatigue_color = ListProperty([0.34, 0.40, 0.46, 1])
    work_time_text = StringProperty("Tiempo efectivo: 00:00 h")
    break_time_text = StringProperty("Pausas: 00:00 h")
    break_action_text = StringProperty("INICIAR PAUSA")
    break_action_color = ListProperty([0.00, 0.62, 0.86, 1])


class MaintenanceScreen(Screen):
    next_due_text = StringProperty("Sin próximos controles")



class SettingsScreen(Screen):
    theme_action_text = StringProperty("ACTIVAR MODO OSCURO")


class ValidationError(ValueError):
    """Expected user input error. Safe to display to the user."""


class DriverControlApp(MDApp):
    bg_color = ListProperty([0.965, 0.976, 0.988, 1])
    card_color = ListProperty([1, 1, 1, 1])
    muted_color = ListProperty([0.32, 0.38, 0.45, 1])
    accent_color = ListProperty([0.02, 0.60, 0.64, 1])
    primary_color = ListProperty([0.055, 0.12, 0.20, 1])
    # Kivy reserves names prefixed with ``on_`` for change callbacks. Keeping
    # display colors outside that namespace prevents a theme change from
    # trying to call an ObservableList as though it were a function.
    primary_text_color = ListProperty([1, 1, 1, 1])
    primary_muted_text_color = ListProperty([0.76, 0.84, 0.90, 1])
    chart_color = ListProperty([0.44, 0.75, 0.77, 1])

    def build(self):
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "LightBlue"
        self.payment_menu = None

        data_dir = Path(self.user_data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(data_dir / DB_FILE))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")

        self._create_or_migrate_db()
        self._apply_theme(self.setting("dark_mode", "0") == "1")
        return Builder.load_string(KV)

    def on_start(self):
        try:
            self._clock_event = Clock.schedule_interval(self._tick_clock, 1)
            self._wellness_event = Clock.schedule_interval(
                lambda _dt: self.refresh_wellness(), 60
            )
            self._tick_clock(0)
            self.refresh_all()
            self._sync_android_assistant_settings()
            LOGGER.info("Application started successfully. Version=%s", APP_VERSION)
        except Exception:
            LOGGER.exception("Fatal error during application startup.")
            raise

    def on_stop(self):
        event = getattr(self, "_clock_event", None)
        if event is not None:
            event.cancel()
            self._clock_event = None
        wellness_event = getattr(self, "_wellness_event", None)
        if wellness_event is not None:
            wellness_event.cancel()
            self._wellness_event = None
        connection = getattr(self, "conn", None)
        self.conn = None
        if connection is not None:
            try:
                connection.commit()
                connection.close()
                LOGGER.info("Database connection closed cleanly.")
            except Exception:
                LOGGER.exception("Error while closing database.")

    @contextmanager
    def transaction(self):
        try:
            self.conn.execute("BEGIN")
            yield
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            LOGGER.exception("Transaction rolled back.")
            raise

    def _create_or_migrate_db(self):
        current_version = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
        if current_version > DB_SCHEMA_VERSION:
            raise RuntimeError(
                "La base de datos fue creada por una versión más nueva de Driver Control."
            )
        with self.transaction():
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trips(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    amount REAL NOT NULL CHECK(amount >= 0),
                    payment TEXT NOT NULL,
                    km REAL NOT NULL DEFAULT 0 CHECK(km >= 0),
                    duration INTEGER NOT NULL DEFAULT 0 CHECK(duration >= 0),
                    cash_received REAL,
                    change_given REAL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS expenses(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    amount REAL NOT NULL CHECK(amount >= 0)
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fuel(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    amount REAL NOT NULL CHECK(amount >= 0),
                    liters REAL NOT NULL CHECK(liters >= 0),
                    odometer REAL NOT NULL CHECK(odometer >= 0)
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS work_sessions(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    opening_odometer REAL NOT NULL CHECK(opening_odometer >= 0),
                    current_odometer REAL,
                    closing_odometer REAL,
                    opening_cash REAL NOT NULL DEFAULT 0 CHECK(opening_cash >= 0),
                    closing_cash REAL,
                    cash_expected REAL,
                    cash_difference REAL,
                    status TEXT NOT NULL DEFAULT 'OPEN'
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings(
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_summaries(
                    session_id INTEGER PRIMARY KEY,
                    income_total REAL NOT NULL DEFAULT 0 CHECK(income_total >= 0),
                    trip_count INTEGER NOT NULL DEFAULT 0 CHECK(trip_count >= 0),
                    cash_collected REAL CHECK(cash_collected >= 0),
                    mp_collected REAL CHECK(mp_collected >= 0),
                    app_collected REAL CHECK(app_collected >= 0),
                    uber_fee REAL NOT NULL DEFAULT 0 CHECK(uber_fee >= 0),
                    uber_owes REAL NOT NULL DEFAULT 0 CHECK(uber_owes >= 0),
                    driver_owes REAL NOT NULL DEFAULT 0 CHECK(driver_owes >= 0),
                    confidence TEXT NOT NULL DEFAULT 'PARTIAL'
                        CHECK(confidence IN ('CONFIRMED','PARTIAL')),
                    source_mode TEXT NOT NULL DEFAULT 'QUICK'
                        CHECK(source_mode IN ('QUICK','DETAILED','OCR')),
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES work_sessions(id) ON DELETE CASCADE
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS driver_breaks(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    FOREIGN KEY(session_id) REFERENCES work_sessions(id)
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS fatigue_checkins(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 5),
                    FOREIGN KEY(session_id) REFERENCES work_sessions(id)
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS maintenance_records(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    odometer REAL NOT NULL DEFAULT 0 CHECK(odometer >= 0),
                    amount REAL NOT NULL DEFAULT 0 CHECK(amount >= 0),
                    next_due_date TEXT,
                    next_due_odometer REAL,
                    payment TEXT,
                    session_id INTEGER,
                    expense_id INTEGER,
                    status TEXT NOT NULL DEFAULT 'COMPLETED'
                )
                """
            )

            self._ensure_column("trips", "cash_received", "REAL")
            self._ensure_column("trips", "change_given", "REAL")
            self._ensure_column("trips", "session_id", "INTEGER")
            self._ensure_column("trips", "uber_fee", "REAL NOT NULL DEFAULT 0")
            self._ensure_column("expenses", "session_id", "INTEGER")
            self._ensure_column("expenses", "payment", "TEXT")
            self._ensure_column("fuel", "session_id", "INTEGER")
            self._ensure_column("fuel", "payment", "TEXT")
            self._ensure_column("work_sessions", "current_odometer", "REAL")

            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trips_created_at ON trips(created_at)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_expenses_created_at ON expenses(created_at)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fuel_created_at ON fuel(created_at)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_breaks_session ON driver_breaks(session_id)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_fatigue_session ON fatigue_checkins(session_id)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_maintenance_created_at ON maintenance_records(created_at)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_maintenance_due_km ON maintenance_records(next_due_odometer)"
            )

            self.conn.execute(
                "UPDATE trips SET payment=? WHERE lower(trim(payment)) IN ('efectivo','cash')",
                (PAYMENT_CASH,),
            )
            self.conn.execute(
                "UPDATE trips SET payment=? WHERE lower(replace(trim(payment),' ','')) IN ('mercadopago','mp')",
                (PAYMENT_MP,),
            )
            self.conn.execute(
                "UPDATE trips SET payment=? WHERE lower(trim(payment))='uber'",
                (PAYMENT_UBER,),
            )

            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trip_assessments(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                )
                """
            )
            self._ensure_column("trip_assessments", "decision", "TEXT")

            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES('daily_goal',?)",
                (str(DEFAULT_DAILY_GOAL),),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES('weekly_goal',?)",
                (str(DEFAULT_WEEKLY_GOAL),),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES('vehicle',?)",
                (DEFAULT_VEHICLE,),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES('fuel_consumption',?)",
                (str(DEFAULT_FUEL_CONSUMPTION),),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES('fuel_price',?)",
                (str(DEFAULT_FUEL_PRICE),),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES('assistant_min_hourly',?)",
                (str(DEFAULT_ASSISTANT_MIN_HOURLY),),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES('assistant_min_per_km',?)",
                (str(DEFAULT_ASSISTANT_MIN_PER_KM),),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES('assistant_max_pickup_km',?)",
                (str(DEFAULT_ASSISTANT_MAX_PICKUP_KM),),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES('tank_capacity',?)",
                (str(DEFAULT_TANK_CAPACITY),),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES('dark_mode','0')"
            )
            self.conn.execute(f"PRAGMA user_version={DB_SCHEMA_VERSION}")
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES('ai_server_url',?)",
                (DEFAULT_AI_SERVER_URL,),
            )
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key,value) VALUES('ai_access_token',?)",
                (DEFAULT_AI_ACCESS_TOKEN,),
            )

    def _ensure_column(self, table: str, column: str, sql_type: str):
        rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {row["name"] for row in rows}
        if column not in existing:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
            LOGGER.info("DB migration: added %s.%s", table, column)

    def go(self, name: str):
        if not self.root.has_screen(name):
            LOGGER.error("Attempt to navigate to unknown screen: %s", name)
            return
        self.root.current = name
        self.refresh_all()

    def go_jornada(self):
        """La pestaña Jornada abre la caja activa; el historial queda a un toque."""
        self.go("cash")

    @staticmethod
    def _duration_text(seconds: float) -> str:
        total_minutes = max(0, int(seconds // 60))
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours:02d}:{minutes:02d} h"

    def _active_break(self, session_id: int):
        return self.conn.execute(
            """
            SELECT * FROM driver_breaks
            WHERE session_id=? AND ended_at IS NULL
            ORDER BY id DESC LIMIT 1
            """,
            (session_id,),
        ).fetchone()

    def toggle_break(self):
        try:
            session_id = self._require_active_session()
            active = self._active_break(session_id)
            now = datetime.now().strftime(DATETIME_FORMAT)
            with self.transaction():
                if active is None:
                    self.conn.execute(
                        "INSERT INTO driver_breaks(session_id,started_at) VALUES(?,?)",
                        (session_id, now),
                    )
                    message = "Pausa iniciada. Descansá, hidratate y evitá mirar pedidos."
                else:
                    self.conn.execute(
                        "UPDATE driver_breaks SET ended_at=? WHERE id=?",
                        (now, int(active["id"])),
                    )
                    message = "Pausa finalizada. Retomá solamente si te sentís en condiciones."
            self.refresh_wellness()
            self.show_message("Bienestar", message)
        except ValidationError as exc:
            self.show_message("Bienestar", str(exc))
        except Exception:
            LOGGER.exception("Could not toggle driver break")
            self.show_message("Bienestar", "No se pudo registrar la pausa.")

    def record_fatigue(self, level: int):
        try:
            session_id = self._require_active_session()
            level = max(1, min(5, int(level)))
            with self.transaction():
                self.conn.execute(
                    "INSERT INTO fatigue_checkins(session_id,created_at,level) VALUES(?,?,?)",
                    (session_id, datetime.now().strftime(DATETIME_FORMAT), level),
                )
            self.refresh_wellness()
            if level >= 5:
                self.show_message(
                    "Detenete en un lugar seguro",
                    "Marcaste fatiga alta. Driver Control recomienda terminar o hacer una pausa prolongada.",
                )
            elif level >= 3:
                self.show_message("Hacé una pausa", "Un descanso corto puede reducir errores y tensión.")
            else:
                self.show_message("Estado registrado", "Seguiremos teniendo en cuenta tu tiempo de jornada.")
        except ValidationError as exc:
            self.show_message("Bienestar", str(exc))
        except Exception:
            LOGGER.exception("Could not save fatigue check-in")
            self.show_message("Bienestar", "No se pudo guardar tu estado.")

    def open_map(self, query: str):
        if platform != "android":
            self.show_message("Mapa", "Esta acción abre la aplicación de mapas en Android.")
            return
        try:
            session = self._active_session()
            if session is not None and self._active_break(int(session["id"])) is None:
                self.show_message(
                    "Primero detenete",
                    "Iniciá una pausa antes de abrir el mapa. Usalo con el vehículo detenido.",
                )
                return
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            URLEncoder = autoclass("java.net.URLEncoder")
            current = PythonActivity.mActivity
            encoded = URLEncoder.encode(query, "UTF-8")
            intent = Intent(Intent.ACTION_VIEW, Uri.parse("geo:0,0?q=" + encoded))
            current.startActivity(intent)
        except Exception:
            LOGGER.exception("Could not open map")
            self.show_message("Mapa", "No encontré una aplicación de mapas instalada.")

    def refresh_wellness(self):
        if not getattr(self, "root", None):
            return
        screen = self.root.get_screen("wellness_map")
        session = self._active_session()
        if session is None:
            screen.fatigue_title = "Sin jornada activa"
            screen.fatigue_message = "Abrí una jornada para activar pausas y seguimiento."
            screen.fatigue_color = self.muted_color
            screen.work_time_text = "Tiempo efectivo: 00:00 h"
            screen.break_time_text = "Pausas: 00:00 h"
            screen.break_action_text = "INICIAR PAUSA"
            self._sync_android_wellness_state(0, False)
            return

        session_id = int(session["id"])
        now = datetime.now()
        opened = datetime.strptime(session["opened_at"], DATETIME_FORMAT)
        rows = self.conn.execute(
            "SELECT started_at,ended_at FROM driver_breaks WHERE session_id=?",
            (session_id,),
        ).fetchall()
        break_seconds = 0.0
        last_effective_resume = opened
        active_break = None
        for row in rows:
            started = datetime.strptime(row["started_at"], DATETIME_FORMAT)
            ended = datetime.strptime(row["ended_at"], DATETIME_FORMAT) if row["ended_at"] else now
            break_seconds += max(0.0, (ended - started).total_seconds())
            if row["ended_at"]:
                last_effective_resume = max(last_effective_resume, ended)
            else:
                active_break = row

        elapsed = max(0.0, (now - opened).total_seconds())
        effective = max(0.0, elapsed - break_seconds)
        continuous = 0.0 if active_break else max(0.0, (now - last_effective_resume).total_seconds())
        checkin = self.conn.execute(
            "SELECT level FROM fatigue_checkins WHERE session_id=? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        reported = int(checkin["level"]) if checkin else 1

        if reported >= 5 or effective >= 6 * 3600:
            risk = 2
            screen.fatigue_title = "Prioridad: detenerse"
            screen.fatigue_message = "La fatiga puede volver insegura una oferta aunque sea rentable."
            screen.fatigue_color = [0.85, 0.25, 0.20, 1]
        elif reported >= 3 or continuous >= 2 * 3600 or effective >= 4 * 3600:
            risk = 1
            screen.fatigue_title = "Pausa recomendada"
            screen.fatigue_message = "Buscá un lugar seguro antes de continuar."
            screen.fatigue_color = [0.88, 0.55, 0.10, 1]
        else:
            risk = 0
            screen.fatigue_title = "Ritmo saludable"
            screen.fatigue_message = "La jornada sigue dentro de los límites configurados."
            screen.fatigue_color = [0.10, 0.60, 0.32, 1]

        screen.work_time_text = f"Tiempo efectivo: {self._duration_text(effective)}"
        screen.break_time_text = f"Pausas acumuladas: {self._duration_text(break_seconds)}"
        screen.break_action_text = "FINALIZAR PAUSA" if active_break else "INICIAR PAUSA"
        screen.break_action_color = (
            [0.12, 0.62, 0.34, 1] if active_break else [0.00, 0.62, 0.86, 1]
        )
        self._sync_android_wellness_state(risk, active_break is not None)

    def setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key=?",
            (key,),
        ).fetchone()
        return row["value"] if row else default

    def _setting_float(self, key: str, default: float) -> float:
        raw = self.setting(key, str(default))
        try:
            value = float(raw)
            if value <= 0:
                raise ValueError
            return value
        except (TypeError, ValueError):
            LOGGER.warning("Invalid numeric setting %s=%r. Using default.", key, raw)
            return default

    def _apply_theme(self, dark: bool):
        self.theme_cls.theme_style = "Dark" if dark else "Light"
        if dark:
            self.bg_color = [0.035, 0.055, 0.078, 1]
            self.card_color = [0.075, 0.105, 0.14, 1]
            self.muted_color = [0.65, 0.71, 0.77, 1]
            self.accent_color = [0.18, 0.82, 0.73, 1]
            self.primary_color = [0.03, 0.20, 0.22, 1]
            self.primary_muted_text_color = [0.72, 0.90, 0.88, 1]
            self.chart_color = [0.16, 0.45, 0.48, 1]
        else:
            self.bg_color = [0.965, 0.976, 0.988, 1]
            self.card_color = [1, 1, 1, 1]
            self.muted_color = [0.32, 0.38, 0.45, 1]
            self.accent_color = [0.02, 0.60, 0.64, 1]
            self.primary_color = [0.055, 0.12, 0.20, 1]
            self.primary_muted_text_color = [0.76, 0.84, 0.90, 1]
            self.chart_color = [0.44, 0.75, 0.77, 1]
        self.primary_text_color = [1, 1, 1, 1]
        if getattr(self, "root", None):
            settings = self.root.get_screen("settings")
            settings.theme_action_text = (
                "ACTIVAR MODO CLARO" if dark else "ACTIVAR MODO OSCURO"
            )

    def toggle_theme(self):
        previous_dark = self.setting("dark_mode", "0") == "1"
        dark = not previous_dark
        try:
            # Apply first: a rendering error must never persist a theme that
            # could prevent the next startup from completing.
            self._apply_theme(dark)
            with self.transaction():
                self.conn.execute(
                    "INSERT OR REPLACE INTO settings(key,value) VALUES('dark_mode',?)",
                    ("1" if dark else "0",),
                )
            self.refresh_all()
        except Exception:
            LOGGER.exception("Could not switch application theme.")
            try:
                with self.transaction():
                    self.conn.execute(
                        "INSERT OR REPLACE INTO settings(key,value) VALUES('dark_mode',?)",
                        ("1" if previous_dark else "0",),
                    )
                self._apply_theme(previous_dark)
            except Exception:
                LOGGER.exception("Could not restore the previous theme.")
            self.show_message(
                "No se pudo cambiar el tema",
                "La app conservó el modo anterior y puede seguir usándose.",
            )

    def money(self, value: float) -> str:
        return f"${float(value):,.0f}".replace(",", ".")

    def _goal_progress_message(self, percent: float, remaining: float, trips: int) -> str:
        """Celebrate progress without adding distracting animation while driving."""
        if percent >= 100:
            return "¡Meta cumplida! Gran jornada."
        if trips <= 0:
            return "Primer paso: sumá tu primer viaje."
        if percent < 25:
            return f"Buen comienzo · faltan {self.money(remaining)}"
        if percent < 60:
            return f"Vas tomando ritmo · faltan {self.money(remaining)}"
        return f"Último tramo · faltan {self.money(remaining)}"

    def _parse_non_negative_float(
        self,
        raw: str,
        field_name: str,
        *,
        allow_zero: bool = True,
    ) -> float:
        try:
            value = float((raw or "").strip().replace(",", "."))
        except (TypeError, ValueError):
            raise ValidationError(f"{field_name}: ingresá un número válido.")

        if value < 0 or (not allow_zero and value == 0):
            comparator = "mayor que 0" if not allow_zero else "0 o más"
            raise ValidationError(f"{field_name}: el valor debe ser {comparator}.")
        return value

    def _parse_non_negative_int(
        self,
        raw: str,
        field_name: str,
        *,
        allow_zero: bool = True,
    ) -> int:
        value = self._parse_non_negative_float(
            raw,
            field_name,
            allow_zero=allow_zero,
        )
        if not value.is_integer():
            raise ValidationError(f"{field_name}: ingresá un número entero.")
        return int(value)

    def _parse_optional_non_negative_float(
        self,
        raw: str,
        field_name: str,
    ) -> Optional[float]:
        if not (raw or "").strip():
            return None
        return self._parse_non_negative_float(raw, field_name)

    def _parse_optional_non_negative_int(
        self,
        raw: str,
        field_name: str,
    ) -> Optional[int]:
        if not (raw or "").strip():
            return None
        return self._parse_non_negative_int(raw, field_name)

    def _normalize_payment(self, raw: str) -> str:
        normalized = (raw or "").strip().casefold()
        aliases = {
            "efectivo": PAYMENT_CASH,
            "cash": PAYMENT_CASH,
            "mercado pago": PAYMENT_MP,
            "mercadopago": PAYMENT_MP,
            "mp": PAYMENT_MP,
            "uber": PAYMENT_UBER,
            "otro": PAYMENT_OTHER,
            "otros": PAYMENT_OTHER,
        }
        if normalized in aliases:
            return aliases[normalized]
        raise ValidationError(
            "Método de pago inválido. Usá: Efectivo, Mercado Pago, Uber u Otro."
        )

    def _active_session(self):
        return self.conn.execute(
            "SELECT * FROM work_sessions WHERE status='OPEN' ORDER BY id DESC LIMIT 1"
        ).fetchone()

    def _require_active_session(self) -> int:
        row = self._active_session()
        if row is None:
            raise ValidationError("Primero abrí una jornada. Así ningún movimiento queda suelto.")
        return int(row["id"])

    def _tick_clock(self, _dt):
        if not getattr(self, "root", None):
            return
        dashboard = self.root.get_screen("dashboard")
        now = datetime.now()
        weekday = WEEKDAYS_ES[now.weekday()].capitalize()
        dashboard.current_datetime_text = f"{weekday} {now:%d/%m/%Y} · {now:%H:%M}"
        session = self._active_session()
        if session:
            try:
                opened = datetime.strptime(session["opened_at"], DATETIME_FORMAT)
                delta = max(now - opened, timedelta(0))
                hours, rem = divmod(int(delta.total_seconds()), 3600)
                minutes = rem // 60
                dashboard.session_time_text = (
                    f"Abierta {session['opened_at']} · {hours:02d}:{minutes:02d} h"
                )
            except Exception:
                dashboard.session_time_text = f"Abierta {session['opened_at']}"

    def toggle_work_session(self):
        if self._active_session() is None:
            self.open_session_dialog()
        else:
            self.close_session_dialog()

    def open_session_dialog(self):
        fields = [
            ("odometer", "Odómetro inicial", True),
            ("cash", "Efectivo inicial en caja", True),
        ]
        self.input_dialog("Abrir jornada", fields, self.save_open_session)

    def save_open_session(self, dialog, widgets):
        try:
            if self._active_session() is not None:
                raise ValidationError("Ya hay una jornada abierta.")
            odometer = self._parse_non_negative_float(
                widgets["odometer"].text, "Odómetro inicial"
            )
            opening_cash = self._parse_non_negative_float(
                widgets["cash"].text or "0", "Efectivo inicial"
            )
            now = datetime.now().strftime(DATETIME_FORMAT)
            with self.transaction():
                self.conn.execute(
                    """
                    INSERT INTO work_sessions(
                        opened_at, opening_odometer, current_odometer,
                        opening_cash, status
                    ) VALUES(?,?,?,?,'OPEN')
                    """,
                    (now, odometer, odometer, opening_cash),
                )
            dialog.dismiss()
            self.refresh_all()
            self.show_message("Jornada abierta", f"Inicio: {now}\nOdómetro: {odometer:.0f} km")
        except ValidationError as exc:
            self.show_message("Revisá los datos", str(exc))
        except Exception:
            LOGGER.exception("Could not open work session")
            self.show_message("Error", "No se pudo abrir la jornada.")

    def close_session_dialog(self):
        self.open_smart_close()

    def _session_summary(self, session_id: int):
        return self.conn.execute(
            "SELECT * FROM session_summaries WHERE session_id=?",
            (session_id,),
        ).fetchone()

    def open_smart_close(self):
        session = self._active_session()
        if session is None:
            self.show_message("Cierre inteligente", "No hay una jornada abierta.")
            return

        session_id = int(session["id"])
        trip = self.conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) income,
                   COALESCE(SUM(uber_fee),0) uber_fee,
                   COUNT(*) trips,
                   COALESCE(SUM(CASE WHEN payment=? THEN amount ELSE 0 END),0) cash_total,
                   COALESCE(SUM(CASE WHEN payment=? THEN amount ELSE 0 END),0) mp_total
            FROM trips WHERE session_id=?
            """,
            (PAYMENT_CASH, PAYMENT_MP, session_id),
        ).fetchone()
        summary = self._session_summary(session_id)
        screen = self.root.get_screen("smart_close")

        def field_value(value, *, blank_zero=False):
            if value is None or (blank_zero and float(value) == 0):
                return ""
            return self._compact_number(float(value))

        income = summary["income_total"] if summary else trip["income"]
        trip_count = summary["trip_count"] if summary else trip["trips"]
        cash_collected = summary["cash_collected"] if summary else trip["cash_total"]
        mp_collected = summary["mp_collected"] if summary else trip["mp_total"]
        uber_fee = summary["uber_fee"] if summary else trip["uber_fee"]

        screen.ids.close_income.text = field_value(income)
        screen.ids.close_trip_count.text = field_value(trip_count, blank_zero=True)
        screen.ids.close_cash_collected.text = field_value(cash_collected, blank_zero=True)
        screen.ids.close_mp_collected.text = field_value(mp_collected, blank_zero=True)
        screen.ids.close_app_collected.text = field_value(
            summary["app_collected"] if summary else None,
            blank_zero=True,
        )
        screen.ids.close_uber_fee.text = field_value(uber_fee, blank_zero=True)
        screen.ids.close_uber_owes.text = field_value(
            summary["uber_owes"] if summary else None,
            blank_zero=True,
        )
        screen.ids.close_driver_owes.text = field_value(
            summary["driver_owes"] if summary else None,
            blank_zero=True,
        )
        current_odometer = max(
            float(session["opening_odometer"] or 0.0),
            float(session["current_odometer"] or 0.0),
        )
        screen.ids.close_odometer.text = field_value(current_odometer)
        screen.ids.close_cash_counted.text = field_value(
            session["closing_cash"],
            blank_zero=True,
        )
        screen.show_details = bool(summary)
        screen.data_confidence = summary["confidence"] if summary else "PARTIAL"
        self._refresh_smart_close_costs(session_id)
        self.root.current = "smart_close"

    def _refresh_smart_close_costs(self, session_id: int):
        screen = self.root.get_screen("smart_close")
        expenses = self.conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) value
            FROM expenses
            WHERE session_id=? AND lower(category)!='combustible'
            """,
            (session_id,),
        ).fetchone()["value"]
        fuel = self.conn.execute(
            """
            SELECT COALESCE(SUM(liters),0) liters, COALESCE(SUM(amount),0) amount
            FROM fuel WHERE session_id=?
            """,
            (session_id,),
        ).fetchone()
        screen.registered_costs_text = (
            f"Ya cargado: {self.money(float(expenses or 0))} en otros gastos · "
            f"{float(fuel['liters'] or 0):.2f} L de nafta "
            f"({self.money(float(fuel['amount'] or 0))})."
        )

    def toggle_smart_close_details(self):
        screen = self.root.get_screen("smart_close")
        screen.show_details = not screen.show_details

    def select_close_confidence(self, confidence: str):
        if confidence in ("CONFIRMED", "PARTIAL"):
            self.root.get_screen("smart_close").data_confidence = confidence

    def cancel_smart_close(self):
        self.root.current = "cash"
        self.refresh_all()

    def save_smart_close(self):
        screen = self.root.get_screen("smart_close")
        try:
            session = self._active_session()
            if session is None:
                raise ValidationError("No hay una jornada abierta.")
            session_id = int(session["id"])
            income = self._parse_non_negative_float(
                screen.ids.close_income.text or "0",
                "Total de Uber",
            )
            trip_count = self._parse_optional_non_negative_int(
                screen.ids.close_trip_count.text,
                "Cantidad de viajes",
            )
            cash_collected = self._parse_optional_non_negative_float(
                screen.ids.close_cash_collected.text,
                "Efectivo cobrado",
            )
            mp_collected = self._parse_optional_non_negative_float(
                screen.ids.close_mp_collected.text,
                "Mercado Pago",
            )
            app_collected = self._parse_optional_non_negative_float(
                screen.ids.close_app_collected.text,
                "Transferido por Uber",
            )
            uber_fee = self._parse_optional_non_negative_float(
                screen.ids.close_uber_fee.text,
                "Comisión Uber",
            )
            uber_owes = self._parse_optional_non_negative_float(
                screen.ids.close_uber_owes.text,
                "Uber te debe",
            )
            driver_owes = self._parse_optional_non_negative_float(
                screen.ids.close_driver_owes.text,
                "Deuda con Uber",
            )
            closing_cash = self._parse_optional_non_negative_float(
                screen.ids.close_cash_counted.text,
                "Efectivo contado",
            )
            closing_odometer = self._parse_non_negative_float(
                screen.ids.close_odometer.text,
                "Odómetro final",
            )

            minimum_odometer = max(
                float(session["opening_odometer"] or 0.0),
                float(session["current_odometer"] or 0.0),
            )
            if closing_odometer < minimum_odometer:
                raise ValidationError(
                    f"El odómetro no puede bajar de {minimum_odometer:.0f} km."
                )
            known_breakdown = sum(
                value
                for value in (cash_collected, mp_collected, app_collected)
                if value is not None
            )
            if known_breakdown > income + 0.01:
                raise ValidationError(
                    "Los cobros forman parte del total de Uber: juntos no pueden superarlo."
                )
            if (uber_owes or 0) > 0 and (driver_owes or 0) > 0:
                raise ValidationError(
                    "Elegí solo un saldo: Uber te debe o vos debés pagarle a Uber."
                )

            confidence = screen.data_confidence
            source_mode = "DETAILED" if screen.show_details else "QUICK"
            now = datetime.now().strftime(DATETIME_FORMAT)

            with self.transaction():
                self.conn.execute(
                    """
                    INSERT INTO session_summaries(
                        session_id,income_total,trip_count,cash_collected,
                        mp_collected,app_collected,uber_fee,uber_owes,
                        driver_owes,confidence,source_mode,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        income_total=excluded.income_total,
                        trip_count=excluded.trip_count,
                        cash_collected=excluded.cash_collected,
                        mp_collected=excluded.mp_collected,
                        app_collected=excluded.app_collected,
                        uber_fee=excluded.uber_fee,
                        uber_owes=excluded.uber_owes,
                        driver_owes=excluded.driver_owes,
                        confidence=excluded.confidence,
                        source_mode=excluded.source_mode,
                        updated_at=excluded.updated_at
                    """,
                    (
                        session_id,
                        income,
                        int(trip_count or 0),
                        cash_collected,
                        mp_collected,
                        app_collected,
                        float(uber_fee or 0.0),
                        float(uber_owes or 0.0),
                        float(driver_owes or 0.0),
                        confidence,
                        source_mode,
                        now,
                    ),
                )
                metrics = self._session_metrics(session_id, closing_odometer)
                difference = None
                if closing_cash is not None and metrics["cash_reconciliation_known"]:
                    difference = closing_cash - metrics["cash_expected"]
                self.conn.execute(
                    """
                    UPDATE driver_breaks
                    SET ended_at=?
                    WHERE session_id=? AND ended_at IS NULL
                    """,
                    (now, session_id),
                )
                self.conn.execute(
                    """
                    UPDATE work_sessions
                    SET closed_at=?,closing_odometer=?,closing_cash=?,
                        current_odometer=?,cash_expected=?,cash_difference=?,
                        status='CLOSED'
                    WHERE id=?
                    """,
                    (
                        now,
                        closing_odometer,
                        closing_cash,
                        closing_odometer,
                        metrics["cash_expected"],
                        difference,
                        session_id,
                    ),
                )

            self.refresh_all()
            self._prepare_day_story(session_id)
        except ValidationError as exc:
            self.show_message("Revisá el cierre", str(exc))
        except Exception:
            LOGGER.exception("Could not save smart close")
            self.show_message(
                "No se pudo cerrar",
                "La jornada sigue abierta y tus datos anteriores están intactos.",
            )

    def _session_worked_minutes(self, session_id: int) -> float:
        session = self.conn.execute(
            "SELECT opened_at,closed_at FROM work_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        if session is None:
            return 0.0
        try:
            opened = datetime.strptime(session["opened_at"], DATETIME_FORMAT)
            closed = (
                datetime.strptime(session["closed_at"], DATETIME_FORMAT)
                if session["closed_at"]
                else datetime.now()
            )
            break_seconds = 0.0
            rows = self.conn.execute(
                "SELECT started_at,ended_at FROM driver_breaks WHERE session_id=?",
                (session_id,),
            ).fetchall()
            for row in rows:
                started = datetime.strptime(row["started_at"], DATETIME_FORMAT)
                ended = (
                    datetime.strptime(row["ended_at"], DATETIME_FORMAT)
                    if row["ended_at"]
                    else closed
                )
                break_seconds += max(0.0, (ended - started).total_seconds())
            elapsed = max(0.0, (closed - opened).total_seconds() - break_seconds)
            return elapsed / 60.0
        except (TypeError, ValueError):
            return 0.0

    def _prepare_day_story(self, session_id: int):
        metrics = self._session_metrics(session_id)
        summary = self._session_summary(session_id)
        session = self.conn.execute(
            "SELECT cash_difference FROM work_sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        confidence = summary["confidence"] if summary else "PARTIAL"
        worked_minutes = self._session_worked_minutes(session_id)
        hourly = (
            metrics["net"] * 60.0 / worked_minutes
            if worked_minutes > 0 else 0.0
        )
        per_km = (
            metrics["net"] / metrics["worked_km"]
            if metrics["worked_km"] > 0 else 0.0
        )
        ranked = rank_financial_insights(
            {
                "income": metrics["revenue"],
                "profit": metrics["net"],
                "fuel_cost": metrics["fuel_cost"],
                "expenses": metrics["operating_expenses"],
            },
            daily_goal=self._setting_float("daily_goal", DEFAULT_DAILY_GOAL),
            confidence=confidence,
            cash_difference=(
                float(session["cash_difference"])
                if session and session["cash_difference"] is not None
                else None
            ),
            limit=1,
        )
        insight = ranked[0]
        story = self.root.get_screen("day_story")
        story.title_text = "¡Jornada cerrada!"
        story.confidence_text = (
            "DATOS CONFIRMADOS · NAFTA ESTIMADA"
            if confidence == "CONFIRMED"
            else "CIERRE PARCIAL · PODÉS COMPLETARLO"
        )
        story.net_text = self.money(metrics["net"])
        story.equation_text = (
            f"{self.money(metrics['revenue'])} ingresos − "
            f"{self.money(metrics['fuel_cost'])} nafta − "
            f"{self.money(metrics['operating_expenses'])} gastos"
        )
        story.hourly_text = f"{self.money(hourly)}/h"
        story.per_km_text = f"{self.money(per_km)}/km"
        story.insight_title = insight.title
        story.insight_text = insight.message
        story.next_action_text = insight.action
        story.why_text = f"Te mostramos esto porque {insight.why[:1].lower() + insight.why[1:]}"
        self.root.current = "day_story"

    def finish_day_story(self):
        self.root.current = "dashboard"
        self.refresh_all()

    def open_current_odometer_dialog(self):
        session = self._active_session()
        if session is None:
            self.show_message("Odómetro", "Abrí una jornada para actualizar los kilómetros.")
            return
        self.input_dialog(
            "Actualizar kilómetros",
            [("odometer", "Odómetro actual", True)],
            self.save_current_odometer,
        )

    def save_current_odometer(self, dialog, widgets):
        try:
            session = self._active_session()
            if session is None:
                raise ValidationError("No hay una jornada abierta.")
            odometer = self._parse_non_negative_float(
                widgets["odometer"].text,
                "Odómetro actual",
            )
            minimum = max(
                float(session["opening_odometer"] or 0.0),
                float(session["current_odometer"] or 0.0),
            )
            if odometer < minimum:
                raise ValidationError(
                    f"El odómetro no puede bajar de {minimum:.0f} km."
                )
            with self.transaction():
                self.conn.execute(
                    "UPDATE work_sessions SET current_odometer=? WHERE id=?",
                    (odometer, int(session["id"])),
                )
            dialog.dismiss()
            self.refresh_all()
        except ValidationError as exc:
            self.show_message("Revisá el odómetro", str(exc))
        except Exception:
            LOGGER.exception("Could not update current odometer")
            self.show_message("Error", "No se pudo actualizar el odómetro.")

    def _session_metrics(self, session_id: int, closing_odometer=None):
        session = self.conn.execute(
            "SELECT * FROM work_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if session is None:
            raise ValidationError("No se encontró la jornada.")

        trip = self.conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) revenue,
                   COALESCE(SUM(uber_fee),0) uber_fee,
                   COALESCE(SUM(km),0) trip_km,
                   COUNT(*) trips,
                   COALESCE(SUM(CASE WHEN payment=? THEN amount ELSE 0 END),0) cash_sales
            FROM trips WHERE session_id=?
            """,
            (PAYMENT_CASH, session_id),
        ).fetchone()
        exp = self.conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN lower(category)!='combustible' THEN amount ELSE 0 END),0) operating,
                   COALESCE(SUM(CASE WHEN payment=? THEN amount ELSE 0 END),0) cash_paid
            FROM expenses WHERE session_id=?
            """,
            (PAYMENT_CASH, session_id),
        ).fetchone()
        loaded = self.conn.execute(
            "SELECT COALESCE(SUM(amount),0) amount, COALESCE(SUM(liters),0) liters FROM fuel WHERE session_id=?",
            (session_id,),
        ).fetchone()
        summary = self._session_summary(session_id)

        end_odo = closing_odometer
        if end_odo is None:
            end_odo = session["closing_odometer"]
        if end_odo is None:
            end_odo = session["current_odometer"]
        if end_odo is not None:
            worked_km = max(float(end_odo) - float(session["opening_odometer"]), 0.0)
        else:
            worked_km = float(trip["trip_km"] or 0.0)

        consumption = self._setting_float("fuel_consumption", DEFAULT_FUEL_CONSUMPTION)
        fuel_price = self._setting_float("fuel_price", DEFAULT_FUEL_PRICE)
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
        summary_cash = summary["cash_collected"] if summary is not None else None
        cash_sales = (
            float(summary_cash)
            if summary_cash is not None
            else float(trip["cash_sales"] or 0.0)
        )
        cash_reconciliation_known = (
            summary is None
            or summary_cash is not None
            or int(trip["trips"] or 0) > 0
        )
        cash_expected = (
            float(session["opening_cash"] or 0.0)
            + cash_sales
            - float(exp["cash_paid"] or 0.0)
        )
        return {
            "revenue": revenue,
            "uber_fee": uber_fee,
            "known_billing": revenue + uber_fee,
            "trips": trips,
            "worked_km": worked_km,
            "operating_expenses": operating_expenses,
            "fuel_liters": fuel_liters,
            "fuel_cost": fuel_cost,
            "fuel_loaded_amount": float(loaded["amount"] or 0.0),
            "fuel_loaded_liters": float(loaded["liters"] or 0.0),
            "net": net,
            "cash_expected": cash_expected,
            "cash_reconciliation_known": cash_reconciliation_known,
            "confidence": summary["confidence"] if summary is not None else "CONFIRMED",
            "source_mode": summary["source_mode"] if summary is not None else "DETAILED",
        }

    def save_close_session(self, dialog, widgets):
        try:
            session = self._active_session()
            if session is None:
                raise ValidationError("No hay una jornada abierta.")
            closing_odometer = self._parse_non_negative_float(
                widgets["odometer"].text, "Odómetro final"
            )
            if closing_odometer < float(session["opening_odometer"]):
                raise ValidationError("El odómetro final no puede ser menor al inicial.")
            closing_cash = self._parse_non_negative_float(
                widgets["cash"].text or "0", "Efectivo contado"
            )
            metrics = self._session_metrics(int(session["id"]), closing_odometer)
            difference = closing_cash - metrics["cash_expected"]
            now = datetime.now().strftime(DATETIME_FORMAT)
            with self.transaction():
                self.conn.execute(
                    "UPDATE driver_breaks SET ended_at=? WHERE session_id=? AND ended_at IS NULL",
                    (now, int(session["id"])),
                )
                self.conn.execute(
                    """
                    UPDATE work_sessions
                    SET closed_at=?, closing_odometer=?, closing_cash=?,
                        current_odometer=?, cash_expected=?, cash_difference=?, status='CLOSED'
                    WHERE id=?
                    """,
                    (
                        now, closing_odometer, closing_cash, closing_odometer,
                        metrics["cash_expected"], difference, session["id"],
                    ),
                )
            dialog.dismiss()
            self.refresh_all()
            sign = "+" if difference >= 0 else "-"
            self.show_message(
                "Jornada cerrada",
                "\n".join([
                    f"Ingresos registrados: {self.money(metrics['revenue'])}",
                    f"Comisión Uber informada: {self.money(metrics['uber_fee'])}",
                    f"Facturación conocida: {self.money(metrics['known_billing'])}",
                    f"Km trabajados: {metrics['worked_km']:.1f} km",
                    f"Nafta consumida: {metrics['fuel_liters']:.2f} L",
                    f"A reponer en nafta: {self.money(metrics['fuel_cost'])}",
                    f"Nafta cargada: {metrics['fuel_loaded_liters']:.2f} L · {self.money(metrics['fuel_loaded_amount'])}",
                    f"Otros gastos: {self.money(metrics['operating_expenses'])}",
                    f"Ganancia real estimada: {self.money(metrics['net'])}",
                    f"Caja esperada: {self.money(metrics['cash_expected'])}",
                    f"Caja contada: {self.money(closing_cash)}",
                    (
                        f"Caja conciliada: +{self.money(abs(difference))}"
                        if difference >= 0 else
                        f"Revisemos la caja: faltan {self.money(abs(difference))}. "
                        "¿Hubo algún gasto en efectivo no registrado?"
                    ),
                ]),
            )
        except ValidationError as exc:
            self.show_message("No se puede cerrar", str(exc))
        except Exception:
            LOGGER.exception("Could not close work session")
            self.show_message("Error", "No se pudo cerrar la jornada.")

    def set_assistant_destination(self, rating: str):
        if rating not in ("Mala", "Normal", "Buena"):
            return
        screen = self.root.get_screen("assistant")
        screen.destination_rating = rating

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def _assistant_result(self, fare, pickup_min, pickup_km, trip_min, trip_km, destination):
        total_min = pickup_min + trip_min
        total_km = pickup_km + trip_km
        if total_min <= 0:
            raise ValidationError("Tiempo total: debe ser mayor que 0.")
        if total_km <= 0:
            raise ValidationError("Kilómetros totales: deben ser mayores que 0.")
        if fare <= 0:
            raise ValidationError("Tarifa ofrecida: debe ser mayor que 0.")

        consumption = self._setting_float("fuel_consumption", DEFAULT_FUEL_CONSUMPTION)
        fuel_price = self._setting_float("fuel_price", DEFAULT_FUEL_PRICE)
        min_hourly = self._setting_float("assistant_min_hourly", DEFAULT_ASSISTANT_MIN_HOURLY)
        min_per_km = self._setting_float("assistant_min_per_km", DEFAULT_ASSISTANT_MIN_PER_KM)
        max_pickup = self._setting_float("assistant_max_pickup_km", DEFAULT_ASSISTANT_MAX_PICKUP_KM)

        fuel_liters = total_km * consumption / 100.0
        fuel_cost = fuel_liters * fuel_price
        net_est = fare - fuel_cost
        hourly_est = net_est * 60.0 / total_min
        per_km_est = net_est / total_km

        hourly_score = self._clamp(hourly_est / min_hourly, 0.0, 1.25) / 1.25 * 30.0
        km_score = self._clamp(per_km_est / min_per_km, 0.0, 1.25) / 1.25 * 25.0
        if pickup_km <= max_pickup:
            pickup_score = 15.0
        else:
            over_ratio = (pickup_km - max_pickup) / max(max_pickup, 0.1)
            pickup_score = 15.0 * self._clamp(1.0 - over_ratio, 0.0, 1.0)
        destination_score = {"Mala": 4.0, "Normal": 10.0, "Buena": 15.0}.get(destination, 10.0)
        fuel_ratio = fuel_cost / fare if fare else 1.0
        fuel_score = 15.0 * self._clamp(1.0 - fuel_ratio, 0.0, 1.0)
        score = self._clamp(hourly_score + km_score + pickup_score + destination_score + fuel_score, 0.0, 100.0)

        # Regla dura configurable: si el viaje queda por debajo del mínimo por km,
        # se rechaza la recomendación aunque el puntaje general sea alto.
        if per_km_est < min_per_km:
            recommendation = "NO CONVIENE"
            color = (0.86, 0.16, 0.18, 1)
        elif score >= 80:
            recommendation = "EXCELENTE"
            color = (0.05, 0.60, 0.26, 1)
        elif score >= 65:
            recommendation = "CONVIENE"
            color = (0.05, 0.60, 0.26, 1)
        elif score >= 45:
            recommendation = "DUDOSO"
            color = (0.92, 0.55, 0.05, 1)
        else:
            recommendation = "NO CONVIENE"
            color = (0.86, 0.16, 0.18, 1)

        reasons = []
        if hourly_est >= min_hourly:
            reasons.append("Buen $/hora")
        else:
            reasons.append("$/hora bajo")
        if per_km_est >= min_per_km:
            reasons.append("Buen $/km")
        else:
            reasons.append("$/km bajo")
        if pickup_km <= max_pickup:
            reasons.append("Pickup razonable")
        else:
            reasons.append("Pickup lejano")
        if destination == "Buena":
            reasons.append("Buen destino")
        elif destination == "Mala":
            reasons.append("Destino poco conveniente")
        if fuel_ratio > 0.25:
            reasons.append("Combustible pesa mucho")

        return {
            "fare": fare,
            "pickup_min": pickup_min,
            "pickup_km": pickup_km,
            "trip_min": trip_min,
            "trip_km": trip_km,
            "total_min": total_min,
            "total_km": total_km,
            "fuel_liters": fuel_liters,
            "fuel_cost": fuel_cost,
            "net_est": net_est,
            "hourly_est": hourly_est,
            "per_km_est": per_km_est,
            "score": score,
            "recommendation": recommendation,
            "destination": destination,
            "color": color,
            "reasons": reasons,
        }

    def _sync_android_assistant_settings(self):
        """Copia al servicio Android parámetros y credenciales del servidor configurado."""
        if platform != "android":
            return
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            prefs = activity.getSharedPreferences("driver_control_overlay", 0)
            editor = prefs.edit()
            editor.putFloat("fuel_consumption", float(self._setting_float("fuel_consumption", DEFAULT_FUEL_CONSUMPTION)))
            editor.putFloat("fuel_price", float(self._setting_float("fuel_price", DEFAULT_FUEL_PRICE)))
            editor.putFloat("min_hourly", float(self._setting_float("assistant_min_hourly", DEFAULT_ASSISTANT_MIN_HOURLY)))
            editor.putFloat("min_per_km", float(self._setting_float("assistant_min_per_km", DEFAULT_ASSISTANT_MIN_PER_KM)))
            editor.putFloat("max_pickup_km", float(self._setting_float("assistant_max_pickup_km", DEFAULT_ASSISTANT_MAX_PICKUP_KM)))
            editor.putString("ai_server_url", self.setting("ai_server_url", DEFAULT_AI_SERVER_URL).strip().rstrip("/"))
            editor.putString("ai_access_token", self.setting("ai_access_token", DEFAULT_AI_ACCESS_TOKEN).strip())
            editor.apply()
        except Exception:
            LOGGER.exception("Could not sync Android overlay settings")

    def _sync_android_wellness_state(self, risk: int, paused: bool):
        """Comparte solo el estado mínimo para ajustar el veredicto flotante."""
        if platform != "android":
            return
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            activity = PythonActivity.mActivity
            editor = activity.getSharedPreferences("driver_control_overlay", 0).edit()
            editor.putInt("fatigue_risk", int(max(0, min(2, risk))))
            editor.putBoolean("driver_paused", bool(paused))
            editor.apply()
        except Exception:
            LOGGER.exception("Could not sync Android wellness state")

    def _start_driver_overlay_service(self) -> bool:
        if platform != "android":
            return False
        try:
            from jnius import autoclass
            Settings = autoclass("android.provider.Settings")
            Intent = autoclass("android.content.Intent")
            BuildVersion = autoclass("android.os.Build$VERSION")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            OverlayService = autoclass("org.drivercontrol.drivercontrol.DriverOverlayService")
            current = PythonActivity.mActivity
            if not Settings.canDrawOverlays(current):
                return False
            intent = Intent(current, OverlayService)
            intent.setAction(OverlayService.ACTION_START)
            if BuildVersion.SDK_INT >= 26:
                current.startForegroundService(intent)
            else:
                current.startService(intent)
            return True
        except Exception:
            LOGGER.exception("Could not start DriverOverlayService")
            return False

    def request_uber_overlay_access(self):
        """Activa el flotante independiente y la burbuja de vuelto."""
        if platform != "android":
            self.show_message("Solo Android", "El flotante sobre Uber funciona únicamente en Android.")
            return
        try:
            from jnius import autoclass
            Settings = autoclass("android.provider.Settings")
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            current = PythonActivity.mActivity
            if Settings.canDrawOverlays(current):
                self._sync_android_assistant_settings()
                if self._start_driver_overlay_service():
                    self.show_message(
                        "Flotante activo",
                        "Vas a ver una burbuja $ sobre Uber para calcular el vuelto. "
                        "El análisis aparecerá cuando el visor local detecte una oferta.",
                    )
                return

            self._pending_overlay_start = True
            intent = Intent(
                Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:" + current.getPackageName()),
            )
            current.startActivity(intent)
        except Exception:
            LOGGER.exception("Could not request overlay permission")
            self.show_message("Permiso", "No se pudo abrir el permiso para mostrar el flotante.")

    def on_resume(self):
        if not getattr(self, "_pending_overlay_start", False):
            return
        self._pending_overlay_start = False

        def _finish(_dt):
            self._sync_android_assistant_settings()
            if self._start_driver_overlay_service():
                self.show_message(
                    "Flotante activo",
                    "Tocá la burbuja $ para abrir el vuelto o arrastrala para moverla.",
                )
            else:
                self.show_message(
                    "Falta permiso",
                    "Activá 'Mostrar sobre otras apps' para Driver Control y tocá otra vez ACTIVAR ASISTENTE + VUELTO.",
                )
        Clock.schedule_once(_finish, 0.35)

    def stop_driver_overlay(self):
        if platform != "android":
            return
        try:
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            OverlayService = autoclass("org.drivercontrol.drivercontrol.DriverOverlayService")
            current = PythonActivity.mActivity
            intent = Intent(current, OverlayService)
            intent.setAction(OverlayService.ACTION_STOP)
            current.startService(intent)
            self.show_message("Flotante detenido", "Se cerró el asistente y la burbuja de vuelto.")
        except Exception:
            LOGGER.exception("Could not stop DriverOverlayService")

    def request_uber_accessibility(self):
        """Abre la autorización de Accesibilidad con botones visibles y comportamiento estable."""
        if platform != "android":
            self.show_message("Solo Android", "La lectura por accesibilidad funciona únicamente en Android.")
            return

        disclosure = (
            "Accesibilidad se usa solo para leer tarifa, minutos y kilómetros visibles en Uber. "
            "No pulsa botones ni acepta viajes. La lectura está limitada para cuidar el rendimiento. "
            "El visor usa una única captura local cuando Uber no expone texto. "
            "Mantené pulsada la burbuja $ para ver el último diagnóstico del lector."
        )
        dialog = None

        def cancel(_button):
            if dialog is not None:
                dialog.dismiss()

        def continue_to_settings(_button):
            if dialog is not None:
                dialog.dismiss()
            self._set_android_gemini_visual_enabled(False)
            self._sync_android_assistant_settings()
            self._start_driver_overlay_service()
            try:
                from jnius import autoclass
                Intent = autoclass("android.content.Intent")
                Settings = autoclass("android.provider.Settings")
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                current = PythonActivity.mActivity
                current.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            except Exception:
                LOGGER.exception("Could not open Android accessibility settings")
                self.show_message("Permiso", "No se pudieron abrir los ajustes de accesibilidad.")

        # Los botones se crean junto con el MDDialog. En algunos Samsung/KivyMD,
        # asignar dialog.buttons después de construirlo deja el área de acciones vacía.
        dialog = MDDialog(
            title="Lectura rápida",
            text=disclosure,
            buttons=[
                MDFlatButton(text="CANCELAR", on_release=cancel),
                MDFlatButton(text="CONTINUAR", on_release=continue_to_settings),
            ],
        )
        dialog.open()

    def _set_android_gemini_visual_enabled(self, enabled: bool):
        if platform != "android":
            return
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            PythonActivity.mActivity.getSharedPreferences("driver_control_overlay", 0).edit().putBoolean(
                "gemini_visual_enabled", bool(enabled)
            ).apply()
        except Exception:
            LOGGER.exception("Could not change Gemini visual mode")

    def request_gemini_visual_accessibility(self):
        """Activa lectura visual remota solo después de un consentimiento explícito."""
        if platform != "android":
            self.show_message("Solo Android", "La lectura visual funciona únicamente en Android.")
            return

        server_url = self.setting("ai_server_url", DEFAULT_AI_SERVER_URL).strip().rstrip("/")
        access_token = self.setting("ai_access_token", DEFAULT_AI_ACCESS_TOKEN).strip()
        if not server_url.startswith("https://") or not access_token:
            self.show_message(
                "Falta configuración",
                "Guardá primero la dirección HTTPS del servidor y el código de acceso.",
            )
            return

        disclosure = (
            "Gemini leerá una captura reducida cuando el visor detecte una oferta de Uber. "
            "La imagen puede incluir ubicación, destino u otros datos visibles. Se enviará por HTTPS "
            "a tu servidor y luego a Google Gemini; Driver Control no la guarda. En el nivel gratuito, "
            "Google puede usar el contenido para mejorar sus productos. No pulsa botones ni acepta viajes."
        )
        dialog = None

        def cancel(_button):
            if dialog is not None:
                dialog.dismiss()

        def continue_to_settings(_button):
            if dialog is not None:
                dialog.dismiss()
            self._set_android_gemini_visual_enabled(True)
            self._sync_android_assistant_settings()
            self._start_driver_overlay_service()
            try:
                from jnius import autoclass
                Intent = autoclass("android.content.Intent")
                Settings = autoclass("android.provider.Settings")
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                PythonActivity.mActivity.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            except Exception:
                LOGGER.exception("Could not open Android accessibility settings")
                self.show_message("Permiso", "No se pudieron abrir los ajustes de accesibilidad.")

        dialog = MDDialog(
            title="Lectura con Gemini",
            text=disclosure,
            buttons=[
                MDFlatButton(text="CANCELAR", on_release=cancel),
                MDFlatButton(text="ACEPTO Y CONTINUAR", on_release=continue_to_settings),
            ],
        )
        dialog.open()

    def analyze_trip_offer(self):
        screen = self.root.get_screen("assistant")
        try:
            fare = self._parse_non_negative_float(screen.ids.assistant_fare.text, "Tarifa", allow_zero=False)
            pickup_min = self._parse_non_negative_float(screen.ids.assistant_pickup_min.text, "Min para buscar")
            pickup_km = self._parse_non_negative_float(screen.ids.assistant_pickup_km.text, "Km para buscar")
            trip_min = self._parse_non_negative_float(screen.ids.assistant_trip_min.text, "Min del viaje")
            trip_km = self._parse_non_negative_float(screen.ids.assistant_trip_km.text, "Km del viaje")
            result = self._assistant_result(
                fare, pickup_min, pickup_km, trip_min, trip_km, screen.destination_rating
            )
            self.last_assistant_result = result
            visible_verdict = {
                "EXCELENTE": "SÍ, EXCELENTE",
                "CONVIENE": "SÍ, CONVIENE",
                "DUDOSO": "REVISÁ",
                "NO CONVIENE": "NO CONVIENE",
            }.get(result["recommendation"], result["recommendation"])
            screen.recommendation_text = f"{visible_verdict} · {result['score']:.0f}/100"
            screen.recommendation_color = result["color"]
            if result["recommendation"] in ("EXCELENTE", "CONVIENE"):
                screen.recommendation_surface_color = [0.02, 0.32, 0.23, 1]
            elif result["recommendation"] == "DUDOSO":
                screen.recommendation_surface_color = [0.42, 0.26, 0.03, 1]
            else:
                screen.recommendation_surface_color = [0.40, 0.08, 0.10, 1]
            screen.summary_text = (
                f"Deja {self.money(result['net_est'])} · {self.money(result['per_km_est'])}/km"
            )
            screen.metrics_text = (
                f"$/hora: {self.money(result['hourly_est'])}/h\n"
                f"$/km: {self.money(result['per_km_est'])}/km\n"
                f"Nafta: {result['fuel_liters']:.2f} L · {self.money(result['fuel_cost'])}"
            )
            screen.reason_text = self._decisive_trip_reason(result)
            self._show_assistant_result_dialog(result)
        except ValidationError as exc:
            self.show_message("Revisá el viaje", str(exc))
        except Exception:
            LOGGER.exception("Could not analyze trip offer")
            self.show_message("Error", "No se pudo analizar el viaje.")

    def _decisive_trip_reason(self, result) -> str:
        min_hourly = self._setting_float("assistant_min_hourly", DEFAULT_ASSISTANT_MIN_HOURLY)
        min_per_km = self._setting_float("assistant_min_per_km", DEFAULT_ASSISTANT_MIN_PER_KM)
        max_pickup = self._setting_float("assistant_max_pickup_km", DEFAULT_ASSISTANT_MAX_PICKUP_KM)
        if result["per_km_est"] < min_per_km:
            return f"deja {self.money(result['per_km_est'])}/km y tu mínimo es {self.money(min_per_km)}/km"
        if result["hourly_est"] < min_hourly:
            return f"deja {self.money(result['hourly_est'])}/h y tu mínimo es {self.money(min_hourly)}/h"
        if result["pickup_km"] > max_pickup:
            return f"el acercamiento es de {result['pickup_km']:.1f} km; tu máximo es {max_pickup:.1f} km"
        if result["destination"] == "Mala":
            return "el destino fue marcado como poco conveniente"
        return f"supera tus mínimos de hora y kilómetro; combustible {self.money(result['fuel_cost'])}"

    def analyze_trip_with_ai(self):
        """Consulta el servidor seguro sin exponer la clave de OpenAI en el APK."""
        screen = self.root.get_screen("assistant")
        try:
            server_url = self.setting("ai_server_url", DEFAULT_AI_SERVER_URL).strip().rstrip("/")
            access_token = self.setting("ai_access_token", DEFAULT_AI_ACCESS_TOKEN).strip()
            if not server_url or not access_token:
                raise ValidationError(
                    "Configurá la dirección del servidor y el código de acceso en Configuración."
                )
            if not server_url.startswith("https://"):
                raise ValidationError("El servidor de IA debe usar una dirección segura https://")

            fare = self._parse_non_negative_float(
                screen.ids.assistant_fare.text, "Tarifa", allow_zero=False
            )
            pickup_min = self._parse_non_negative_float(
                screen.ids.assistant_pickup_min.text, "Min para buscar"
            )
            pickup_km = self._parse_non_negative_float(
                screen.ids.assistant_pickup_km.text, "Km para buscar"
            )
            trip_min = self._parse_non_negative_float(
                screen.ids.assistant_trip_min.text, "Min del viaje"
            )
            trip_km = self._parse_non_negative_float(
                screen.ids.assistant_trip_km.text, "Km del viaje"
            )
            local_result = self._assistant_result(
                fare, pickup_min, pickup_km, trip_min, trip_km, screen.destination_rating
            )
            self.last_assistant_result = local_result
            question = (screen.ids.assistant_ai_question.text or "").strip()
            if not question:
                question = "¿Conviene aceptar este viaje y por qué?"

            payload = {
                "app_version": APP_VERSION,
                "question": question[:500],
                "vehicle": self.setting("vehicle", DEFAULT_VEHICLE),
                "trip": {
                    key: local_result[key]
                    for key in (
                        "fare", "pickup_min", "pickup_km", "trip_min", "trip_km",
                        "total_min", "total_km", "fuel_cost", "net_est",
                        "hourly_est", "per_km_est", "score", "recommendation",
                        "destination",
                    )
                },
                "goals": {
                    "minimum_hourly": self._setting_float(
                        "assistant_min_hourly", DEFAULT_ASSISTANT_MIN_HOURLY
                    ),
                    "minimum_per_km": self._setting_float(
                        "assistant_min_per_km", DEFAULT_ASSISTANT_MIN_PER_KM
                    ),
                    "maximum_pickup_km": self._setting_float(
                        "assistant_max_pickup_km", DEFAULT_ASSISTANT_MAX_PICKUP_KM
                    ),
                },
                "driver_context": self._ai_driver_context(),
                "recent_decisions": self._ai_recent_decisions(),
            }

            screen.ai_status_text = "Consultando IA…"
            screen.ai_response_text = "Analizando rentabilidad, historial y fatiga."
            threading.Thread(
                target=self._ai_request_worker,
                args=(server_url, access_token, payload),
                daemon=True,
            ).start()
        except ValidationError as exc:
            self.show_message("IA", str(exc))
        except Exception:
            LOGGER.exception("Could not prepare AI request")
            self.show_message("IA", "No se pudo preparar la consulta.")

    def _ai_driver_context(self):
        session = self._active_session()
        if session is None:
            return {
                "session_active": False,
                "effective_minutes": 0,
                "on_break": False,
                "reported_fatigue": 1,
            }

        session_id = int(session["id"])
        now = datetime.now()
        opened = datetime.strptime(session["opened_at"], DATETIME_FORMAT)
        breaks = self.conn.execute(
            "SELECT started_at,ended_at FROM driver_breaks WHERE session_id=?",
            (session_id,),
        ).fetchall()
        break_seconds = 0.0
        on_break = False
        for row in breaks:
            started = datetime.strptime(row["started_at"], DATETIME_FORMAT)
            ended = datetime.strptime(row["ended_at"], DATETIME_FORMAT) if row["ended_at"] else now
            break_seconds += max(0.0, (ended - started).total_seconds())
            on_break = on_break or row["ended_at"] is None
        effective_seconds = max(0.0, (now - opened).total_seconds() - break_seconds)
        checkin = self.conn.execute(
            "SELECT level FROM fatigue_checkins WHERE session_id=? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return {
            "session_active": True,
            "effective_minutes": round(effective_seconds / 60.0),
            "break_minutes": round(break_seconds / 60.0),
            "on_break": on_break,
            "reported_fatigue": int(checkin["level"]) if checkin else 1,
        }

    def _ai_recent_decisions(self):
        rows = self.conn.execute(
            """
            SELECT fare,total_min,total_km,hourly_est,per_km_est,
                   score,recommendation,destination_rating,decision
            FROM trip_assessments
            WHERE decision IS NOT NULL
            ORDER BY id DESC LIMIT 30
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def _ai_request_worker(self, server_url: str, access_token: str, payload: dict):
        try:
            import requests

            response = requests.post(
                f"{server_url}/v1/driver/analyze",
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=(6, 35),
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or not data.get("answer"):
                raise ValueError("Invalid AI response")
            Clock.schedule_once(lambda _dt: self._apply_ai_response(data), 0)
        except Exception as exc:
            LOGGER.exception("AI request failed")
            message = "No se pudo conectar con la IA. Revisá internet y la configuración."
            if getattr(exc, "response", None) is not None:
                status = getattr(exc.response, "status_code", 0)
                if status in (401, 403):
                    message = "El código de acceso al servidor no es válido."
                elif status == 429:
                    message = "La IA alcanzó el límite de uso. Intentá nuevamente en unos minutos."
            Clock.schedule_once(lambda _dt, msg=message: self._apply_ai_error(msg), 0)

    def _apply_ai_response(self, data: dict):
        screen = self.root.get_screen("assistant")
        verdict = str(data.get("verdict", "REVISAR")).upper()
        score = int(self._clamp(float(data.get("score", 50)), 0, 100))
        answer = str(data.get("answer", "")).strip()
        reasons = data.get("reasons") or []
        fatigue_advice = str(data.get("fatigue_advice", "")).strip()
        details = answer
        if reasons:
            details += "\n" + " · ".join(str(item) for item in reasons[:3])
        if fatigue_advice:
            details += "\nSeguridad: " + fatigue_advice
        screen.ai_status_text = f"IA: {verdict} · {score}/100"
        screen.ai_response_text = details[:900]

    def _apply_ai_error(self, message: str):
        screen = self.root.get_screen("assistant")
        screen.ai_status_text = "IA no disponible"
        screen.ai_response_text = message
        self.show_message("IA", message)

    def _show_assistant_result_dialog(self, result):
        dialog = None

        def mark(decision):
            self.save_trip_assessment(decision)
            if dialog is not None:
                dialog.dismiss()

        def close(_button):
            if dialog is not None:
                dialog.dismiss()

        dialog = MDDialog(
            title=f"{result['recommendation']} · {result['score']:.0f}/100",
            text="\n".join([
                f"Tarifa: {self.money(result['fare'])}",
                f"Tiempo total: {result['total_min']:.0f} min",
                f"Distancia total: {result['total_km']:.1f} km",
                f"Costo nafta: {self.money(result['fuel_cost'])}",
                f"Ganancia neta est.: {self.money(result['net_est'])}",
                f"$/hora: {self.money(result['hourly_est'])}/h",
                f"$/km: {self.money(result['per_km_est'])}/km",
                "",
                "Por qué: " + " · ".join(result['reasons'][:4]),
            ]),
            buttons=[
                MDFlatButton(text="RECHACÉ", on_release=lambda _x: mark("REJECTED")),
                MDFlatButton(text="CERRAR", on_release=close),
                MDFlatButton(text="ACEPTÉ", on_release=lambda _x: mark("ACCEPTED")),
            ],
        )
        dialog.open()

    def save_trip_assessment(self, decision: str):
        result = getattr(self, "last_assistant_result", None)
        if not result:
            return
        try:
            with self.transaction():
                self.conn.execute(
                    """
                    INSERT INTO trip_assessments(
                        created_at, fare, pickup_min, pickup_km, trip_min, trip_km,
                        total_min, total_km, fuel_cost, net_est, hourly_est, per_km_est,
                        score, recommendation, destination_rating, decision
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        datetime.now().strftime(DATETIME_FORMAT),
                        result["fare"], result["pickup_min"], result["pickup_km"],
                        result["trip_min"], result["trip_km"], result["total_min"],
                        result["total_km"], result["fuel_cost"], result["net_est"],
                        result["hourly_est"], result["per_km_est"], result["score"],
                        result["recommendation"], result["destination"], decision,
                    ),
                )
            label = "aceptado" if decision == "ACCEPTED" else "rechazado"
            self.show_message("Guardado", f"Viaje marcado como {label} para aprender de tus decisiones.")
        except Exception:
            LOGGER.exception("Could not save trip assessment")
            self.show_message("Error", "No se pudo guardar la evaluación.")

    def _refresh_all_legacy(self):
        now = datetime.now()
        today = now.strftime(DATE_FORMAT)
        monday = now.date() - timedelta(days=now.weekday())
        week_dates = [
            (monday + timedelta(days=i)).strftime(DATE_FORMAT)
            for i in range(7)
        ]

        total = self._sum_for_date("trips", "amount", today)
        expenses_row = self.conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS v FROM expenses "
            "WHERE substr(created_at,1,10)=? AND lower(category)!='combustible'",
            (today,),
        ).fetchone()
        expenses = float(expenses_row["v"] or 0.0)
        # Kilómetros del día: priorizar odómetros de jornadas cerradas.
        # Para una jornada abierta, usar los km cargados en sus viajes hasta que se cierre.
        closed_km_row = self.conn.execute(
            """
            SELECT COALESCE(SUM(MAX(closing_odometer-opening_odometer,0)),0) AS v
            FROM work_sessions
            WHERE status='CLOSED' AND substr(opened_at,1,10)=?
            """,
            (today,),
        ).fetchone()
        km = float(closed_km_row["v"] or 0.0)
        open_session_for_km = self._active_session()
        if open_session_for_km is not None and str(open_session_for_km["opened_at"])[:10] == today:
            open_trip_km = self.conn.execute(
                "SELECT COALESCE(SUM(km),0) AS v FROM trips WHERE session_id=?",
                (int(open_session_for_km["id"]),),
            ).fetchone()["v"]
            km += float(open_trip_km or 0.0)
        estimated_fuel_cost_today = (
            km * self._setting_float("fuel_consumption", DEFAULT_FUEL_CONSUMPTION) / 100.0
            * self._setting_float("fuel_price", DEFAULT_FUEL_PRICE)
        )
        trips_count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM trips WHERE substr(created_at,1,10)=?",
            (today,),
        ).fetchone()["c"]

        placeholders = ",".join("?" for _ in week_dates)
        weekly_total = self.conn.execute(
            f"""
            SELECT COALESCE(SUM(amount),0) AS v
            FROM trips
            WHERE substr(created_at,1,10) IN ({placeholders})
            """,
            week_dates,
        ).fetchone()["v"]

        daily_goal = self._setting_float("daily_goal", DEFAULT_DAILY_GOAL)
        weekly_goal = self._setting_float("weekly_goal", DEFAULT_WEEKLY_GOAL)

        dashboard = self.root.get_screen("dashboard")
        session = self._active_session()
        if session is not None:
            dashboard.session_status_text = "Jornada abierta"
            dashboard.session_action_text = "CERRAR JORNADA"
        else:
            dashboard.session_status_text = "Jornada cerrada"
            dashboard.session_time_text = "Abrí una jornada para empezar"
            dashboard.session_action_text = "ABRIR JORNADA"

        # El combustible del dashboard representa TODO EL DÍA, incluso después
        # de cerrar una jornada. Así no vuelve a cero al cerrar.
        consumption_today = self._setting_float("fuel_consumption", DEFAULT_FUEL_CONSUMPTION)
        fuel_price_today = self._setting_float("fuel_price", DEFAULT_FUEL_PRICE)
        fuel_liters_today = km * consumption_today / 100.0
        fuel_cost_today = fuel_liters_today * fuel_price_today
        dashboard.fuel_used_text = (
            f"Consumido: {fuel_liters_today:.2f} L · {self.money(fuel_cost_today)}"
        )
        dashboard.fuel_reserve_text = f"A reponer: {self.money(fuel_cost_today)}"

        dashboard.revenue_text = self.money(total)
        dashboard.net_text = self.money(total - expenses - estimated_fuel_cost_today)
        dashboard.km_text = f"{km:.1f} km"
        dashboard.trips_text = str(trips_count)

        dashboard.goal_text = f"{self.money(total)} / {self.money(daily_goal)}"
        dashboard.goal_percent = self._percent(total, daily_goal)
        daily_remaining = max(daily_goal - total, 0.0)
        dashboard.daily_remaining_text = (
            "Meta alcanzada" if daily_remaining <= 0
            else f"Faltan {self.money(daily_remaining)}"
        )

        dashboard.weekly_goal_text = (
            f"{self.money(weekly_total)} / {self.money(weekly_goal)}"
        )
        dashboard.weekly_goal_percent = self._percent(weekly_total, weekly_goal)

        remaining = max(weekly_goal - weekly_total, 0.0)
        dashboard.weekly_remaining_text = (
            "Meta alcanzada"
            if remaining <= 0
            else f"Faltan {self.money(remaining)}"
        )

        self._refresh_cash_summary(today)
        self.fill_lists()
        self.fill_sessions()
        self.refresh_wellness()

        settings_screen = self.root.get_screen("settings")
        settings_screen.ids.daily_goal.text = self._compact_number(daily_goal)
        settings_screen.ids.weekly_goal.text = self._compact_number(weekly_goal)
        settings_screen.ids.vehicle.text = self.setting("vehicle", DEFAULT_VEHICLE)
        settings_screen.ids.fuel_consumption.text = self._compact_number(
            self._setting_float("fuel_consumption", DEFAULT_FUEL_CONSUMPTION)
        )
        settings_screen.ids.fuel_price.text = self._compact_number(
            self._setting_float("fuel_price", DEFAULT_FUEL_PRICE)
        )
        settings_screen.ids.assistant_min_hourly.text = self._compact_number(
            self._setting_float("assistant_min_hourly", DEFAULT_ASSISTANT_MIN_HOURLY)
        )
        settings_screen.ids.assistant_min_per_km.text = self._compact_number(
            self._setting_float("assistant_min_per_km", DEFAULT_ASSISTANT_MIN_PER_KM)
        )
        settings_screen.ids.assistant_max_pickup_km.text = self._compact_number(
            self._setting_float("assistant_max_pickup_km", DEFAULT_ASSISTANT_MAX_PICKUP_KM)
        )
        settings_screen.ids.ai_server_url.text = self.setting(
            "ai_server_url", DEFAULT_AI_SERVER_URL
        )
        settings_screen.ids.ai_access_token.text = self.setting(
            "ai_access_token", DEFAULT_AI_ACCESS_TOKEN
        )

    def _range_metrics(self, date_texts):
        """Calcula una sola verdad financiera para Inicio, Jornada y Excel."""
        dates = list(dict.fromkeys(date_texts))
        if not dates:
            return {
                "income": 0.0, "uber_fee": 0.0, "expenses": 0.0,
                "km": 0.0, "fuel_liters": 0.0, "fuel_cost": 0.0,
                "profit": 0.0, "trips": 0, "worked_minutes": 0.0,
                "known_billing": 0.0,
            }
        placeholders = ",".join("?" for _ in dates)
        trip = self.conn.execute(
            f"""
            SELECT COALESCE(SUM(amount),0) income,
                   COALESCE(SUM(uber_fee),0) uber_fee,
                   COALESCE(SUM(km),0) trip_km,
                   COUNT(*) trips
            FROM trips
            WHERE substr(created_at,1,10) IN ({placeholders})
              AND (
                    session_id IS NULL
                    OR NOT EXISTS(
                        SELECT 1 FROM session_summaries summary
                        WHERE summary.session_id=trips.session_id
                    )
                  )
            """,
            dates,
        ).fetchone()
        summaries = self.conn.execute(
            f"""
            SELECT COALESCE(SUM(summary.income_total),0) income,
                   COALESCE(SUM(summary.uber_fee),0) uber_fee,
                   COALESCE(SUM(summary.trip_count),0) trips
            FROM session_summaries summary
            JOIN work_sessions session ON session.id=summary.session_id
            WHERE substr(session.opened_at,1,10) IN ({placeholders})
            """,
            dates,
        ).fetchone()
        expense = self.conn.execute(
            f"""
            SELECT COALESCE(SUM(amount),0) expenses
            FROM expenses
            WHERE substr(created_at,1,10) IN ({placeholders})
              AND lower(category)!='combustible'
            """,
            dates,
        ).fetchone()
        sessions = self.conn.execute(
            f"""
            SELECT * FROM work_sessions
            WHERE substr(opened_at,1,10) IN ({placeholders})
            ORDER BY id
            """,
            dates,
        ).fetchall()

        worked_km = 0.0
        worked_seconds = 0.0
        now = datetime.now()
        for session in sessions:
            session_id = int(session["id"])
            if session["closing_odometer"] is not None:
                worked_km += max(
                    float(session["closing_odometer"])
                    - float(session["opening_odometer"] or 0.0),
                    0.0,
                )
            elif session["status"] == "OPEN":
                current_odometer = session["current_odometer"]
                if current_odometer is not None:
                    worked_km += max(
                        float(current_odometer) - float(session["opening_odometer"] or 0.0),
                        0.0,
                    )
                else:
                    session_trip_km = self.conn.execute(
                        "SELECT COALESCE(SUM(km),0) v FROM trips WHERE session_id=?",
                        (session_id,),
                    ).fetchone()["v"]
                    worked_km += float(session_trip_km or 0.0)
            try:
                opened = datetime.strptime(session["opened_at"], DATETIME_FORMAT)
                closed = (
                    datetime.strptime(session["closed_at"], DATETIME_FORMAT)
                    if session["closed_at"] else now
                )
                elapsed = max(0.0, (closed - opened).total_seconds())
                breaks = self.conn.execute(
                    "SELECT started_at,ended_at FROM driver_breaks WHERE session_id=?",
                    (session_id,),
                ).fetchall()
                break_seconds = 0.0
                for pause in breaks:
                    started = datetime.strptime(pause["started_at"], DATETIME_FORMAT)
                    ended = (
                        datetime.strptime(pause["ended_at"], DATETIME_FORMAT)
                        if pause["ended_at"] else now
                    )
                    break_seconds += max(0.0, (ended - started).total_seconds())
                worked_seconds += max(0.0, elapsed - break_seconds)
            except (TypeError, ValueError):
                LOGGER.warning("Could not calculate duration for session %s", session_id)

        # Viajes antiguos sin jornada conservan sus kilómetros cargados.
        orphan_km = self.conn.execute(
            f"""
            SELECT COALESCE(SUM(km),0) v FROM trips
            WHERE session_id IS NULL
              AND substr(created_at,1,10) IN ({placeholders})
            """,
            dates,
        ).fetchone()["v"]
        worked_km += float(orphan_km or 0.0)

        income = float(trip["income"] or 0.0) + float(summaries["income"] or 0.0)
        uber_fee = float(trip["uber_fee"] or 0.0) + float(summaries["uber_fee"] or 0.0)
        trips = int(trip["trips"] or 0) + int(summaries["trips"] or 0)
        expenses = float(expense["expenses"] or 0.0)
        consumption = self._setting_float("fuel_consumption", DEFAULT_FUEL_CONSUMPTION)
        fuel_price = self._setting_float("fuel_price", DEFAULT_FUEL_PRICE)
        fuel_liters = worked_km * consumption / 100.0
        fuel_cost = fuel_liters * fuel_price
        return {
            "income": income,
            "uber_fee": uber_fee,
            "known_billing": income + uber_fee,
            "expenses": expenses,
            "km": worked_km,
            "fuel_liters": fuel_liters,
            "fuel_cost": fuel_cost,
            "profit": income - expenses - fuel_cost,
            "trips": trips,
            "worked_minutes": worked_seconds / 60.0,
        }

    def set_dashboard_period(self, mode: str):
        if mode not in ("today", "week"):
            return
        dashboard = self.root.get_screen("dashboard")
        dashboard.period_mode = mode
        self.refresh_all()

    def select_chart_day(self, index: int):
        dashboard = self.root.get_screen("dashboard")
        dashboard.chart_selected_index = max(0, min(6, int(index)))
        self._refresh_chart_detail()

    def _refresh_chart_detail(self):
        dashboard = self.root.get_screen("dashboard")
        monday = datetime.now().date() - timedelta(days=datetime.now().weekday())
        index = max(0, min(6, int(dashboard.chart_selected_index)))
        selected = monday + timedelta(days=index)
        metrics = self._range_metrics([selected.strftime(DATE_FORMAT)])
        dashboard.chart_detail_text = (
            f"{selected.strftime('%d/%m')} · Ingresos {self.money(metrics['income'])} · "
            f"Ganancia {self.money(metrics['profit'])}"
        )

    def _income_values_for_dates(self, date_texts):
        return [self._range_metrics([date_text])["income"] for date_text in date_texts]

    def _current_odometer(self) -> float:
        values = []
        row = self.conn.execute(
            "SELECT MAX(odometer) v FROM fuel WHERE odometer>0"
        ).fetchone()
        if row and row["v"] is not None:
            values.append(float(row["v"]))
        rows = self.conn.execute(
            "SELECT opening_odometer,current_odometer,closing_odometer FROM work_sessions"
        ).fetchall()
        for item in rows:
            values.append(float(item["opening_odometer"] or 0.0))
            if item["current_odometer"] is not None:
                values.append(float(item["current_odometer"]))
            if item["closing_odometer"] is not None:
                values.append(float(item["closing_odometer"]))
        return max(values or [0.0])

    def _maintenance_status_text(self) -> str:
        rows = self.conn.execute(
            """
            SELECT category,next_due_date,next_due_odometer
            FROM maintenance_records
            WHERE COALESCE(next_due_date,'')!='' OR COALESCE(next_due_odometer,0)>0
            ORDER BY id DESC LIMIT 30
            """
        ).fetchall()
        if not rows:
            return "Todavía no hay próximos controles registrados."
        odometer = self._current_odometer()
        best = None
        for row in rows:
            due_km = float(row["next_due_odometer"] or 0.0)
            distance = due_km - odometer if due_km > 0 else float("inf")
            candidate = (distance, row)
            if best is None or candidate[0] < best[0]:
                best = candidate
        distance, row = best
        details = []
        if row["next_due_odometer"]:
            if distance <= 0:
                details.append(f"vencido por {abs(distance):.0f} km")
            else:
                details.append(f"faltan {distance:.0f} km")
        if row["next_due_date"]:
            details.append(str(row["next_due_date"]))
        return f"{row['category']}: " + " · ".join(details)

    def refresh_all(self):
        now = datetime.now()
        today = now.strftime(DATE_FORMAT)
        monday = now.date() - timedelta(days=now.weekday())
        week_dates = [
            (monday + timedelta(days=index)).strftime(DATE_FORMAT)
            for index in range(7)
        ]

        dashboard = self.root.get_screen("dashboard")
        session = self._active_session()
        selected_dates = [today] if dashboard.period_mode == "today" else week_dates
        metrics = self._range_metrics(selected_dates)
        daily_metrics = self._range_metrics([today])
        weekly_metrics = self._range_metrics(week_dates)
        period_goal = self._setting_float(
            "daily_goal" if dashboard.period_mode == "today" else "weekly_goal",
            DEFAULT_DAILY_GOAL if dashboard.period_mode == "today" else DEFAULT_WEEKLY_GOAL,
        )

        dashboard.period_label = "Hoy" if dashboard.period_mode == "today" else "7 días"
        dashboard.income_text = self.money(metrics["income"])
        dashboard.revenue_text = self.money(metrics["known_billing"])
        dashboard.commission_text = self.money(metrics["uber_fee"])
        dashboard.commission_help_text = (
            "La comisión informada explica la facturación conocida y no se descuenta dos veces."
            if metrics["uber_fee"] > 0 else
            "Comisión no informada: el ingreso registrado se conserva sin inventar descuentos."
        )
        dashboard.fuel_cost_text = self.money(metrics["fuel_cost"])
        dashboard.expenses_text = self.money(metrics["expenses"])
        dashboard.net_text = self.money(metrics["profit"])
        dashboard.net_explanation_text = (
            f"{self.money(metrics['income'])} ingresos − {self.money(metrics['fuel_cost'])} nafta "
            f"− {self.money(metrics['expenses'])} gastos"
        )
        odometer_pending = bool(
            session is not None
            and metrics["trips"] > 0
            and float(session["current_odometer"] or session["opening_odometer"] or 0.0)
            <= float(session["opening_odometer"] or 0.0)
        )
        if odometer_pending:
            dashboard.net_explanation_text += " · Actualizá el odómetro para incluir nafta"
        hourly = (
            metrics["profit"] * 60.0 / metrics["worked_minutes"]
            if metrics["worked_minutes"] > 0 else 0.0
        )
        per_km = metrics["profit"] / metrics["km"] if metrics["km"] > 0 else 0.0
        dashboard.efficiency_text = (
            f"{self.money(hourly)}/h · km pendientes del odómetro"
            if odometer_pending else
            f"{self.money(hourly)}/h · {self.money(per_km)}/km"
        )
        dashboard.km_text = f"{metrics['km']:.1f} km"
        dashboard.trips_text = str(metrics["trips"])
        dashboard.fuel_used_text = (
            f"Consumido: {metrics['fuel_liters']:.2f} L · {self.money(metrics['fuel_cost'])}"
        )
        dashboard.fuel_reserve_text = f"A reponer: {self.money(metrics['fuel_cost'])}"
        dashboard.goal_text = f"{self.money(metrics['income'])} / {self.money(period_goal)}"
        dashboard.goal_percent = self._percent(metrics["income"], period_goal)
        remaining = max(period_goal - metrics["income"], 0.0)
        dashboard.daily_remaining_text = self._goal_progress_message(
            dashboard.goal_percent,
            remaining,
            int(metrics["trips"]),
        )
        dashboard.goal_message_color = (
            list(self.accent_color)
            if dashboard.goal_percent >= 100
            else list(self.muted_color)
        )
        dashboard.weekly_goal_text = (
            f"{self.money(weekly_metrics['income'])} / "
            f"{self.money(self._setting_float('weekly_goal', DEFAULT_WEEKLY_GOAL))}"
        )
        dashboard.weekly_goal_percent = self._percent(
            weekly_metrics["income"],
            self._setting_float("weekly_goal", DEFAULT_WEEKLY_GOAL),
        )
        dashboard.week_values = self._income_values_for_dates(week_dates)
        if not hasattr(self, "_chart_initialized"):
            dashboard.chart_selected_index = now.weekday()
            self._chart_initialized = True
        self._refresh_chart_detail()

        if session is not None:
            dashboard.session_status_text = "Jornada activa"
            dashboard.session_action_text = "CERRAR JORNADA"
        else:
            dashboard.session_status_text = "Jornada cerrada"
            dashboard.session_time_text = "Abrí una jornada para empezar"
            dashboard.session_action_text = "ABRIR JORNADA"

        cash = self.root.get_screen("cash")
        cash.profit_text = self.money(daily_metrics["profit"])
        cash.profit_detail_text = (
            f"{self.money(daily_metrics['income'])} ingresos − "
            f"{self.money(daily_metrics['fuel_cost'])} nafta − "
            f"{self.money(daily_metrics['expenses'])} gastos"
        )
        cash.session_action_text = (
            "CERRAR JORNADA" if session is not None else "ABRIR JORNADA"
        )
        self._refresh_cash_summary(today)

        vehicle = self.root.get_screen("wellness_map")
        vehicle.vehicle_text = self.setting("vehicle", DEFAULT_VEHICLE)
        vehicle.vehicle_cost_text = (
            f"{self._setting_float('fuel_consumption', DEFAULT_FUEL_CONSUMPTION):.1f} L/100 km · "
            f"{self.money(self._setting_float('fuel_price', DEFAULT_FUEL_PRICE))} por litro"
        )
        maintenance_text = self._maintenance_status_text()
        vehicle.next_maintenance_text = maintenance_text
        self.root.get_screen("maintenance").next_due_text = maintenance_text

        self.fill_lists()
        self.fill_sessions()
        self.refresh_wellness()

        daily_goal = self._setting_float("daily_goal", DEFAULT_DAILY_GOAL)
        weekly_goal = self._setting_float("weekly_goal", DEFAULT_WEEKLY_GOAL)
        settings = self.root.get_screen("settings")
        settings.ids.daily_goal.text = self._compact_number(daily_goal)
        settings.ids.weekly_goal.text = self._compact_number(weekly_goal)
        settings.ids.vehicle.text = self.setting("vehicle", DEFAULT_VEHICLE)
        settings.ids.fuel_consumption.text = self._compact_number(
            self._setting_float("fuel_consumption", DEFAULT_FUEL_CONSUMPTION)
        )
        settings.ids.fuel_price.text = self._compact_number(
            self._setting_float("fuel_price", DEFAULT_FUEL_PRICE)
        )
        settings.ids.tank_capacity.text = self._compact_number(
            self._setting_float("tank_capacity", DEFAULT_TANK_CAPACITY)
        )
        settings.ids.assistant_min_hourly.text = self._compact_number(
            self._setting_float("assistant_min_hourly", DEFAULT_ASSISTANT_MIN_HOURLY)
        )
        settings.ids.assistant_min_per_km.text = self._compact_number(
            self._setting_float("assistant_min_per_km", DEFAULT_ASSISTANT_MIN_PER_KM)
        )
        settings.ids.assistant_max_pickup_km.text = self._compact_number(
            self._setting_float("assistant_max_pickup_km", DEFAULT_ASSISTANT_MAX_PICKUP_KM)
        )
        settings.ids.ai_server_url.text = self.setting("ai_server_url", DEFAULT_AI_SERVER_URL)
        settings.ids.ai_access_token.text = self.setting("ai_access_token", DEFAULT_AI_ACCESS_TOKEN)
        settings.theme_action_text = (
            "ACTIVAR MODO CLARO" if self.setting("dark_mode", "0") == "1"
            else "ACTIVAR MODO OSCURO"
        )
        if session is not None and self.root.current == "smart_close":
            self._refresh_smart_close_costs(int(session["id"]))

    def _refresh_cash_summary(self, date_text: str):
        rows = self.conn.execute(
            """
            SELECT
                payment,
                COALESCE(SUM(amount), 0) AS amount_total,
                COALESCE(SUM(cash_received), 0) AS received_total,
                COALESCE(SUM(change_given), 0) AS change_total
            FROM trips
            WHERE substr(created_at,1,10)=?
              AND (
                    session_id IS NULL
                    OR NOT EXISTS(
                        SELECT 1 FROM session_summaries summary
                        WHERE summary.session_id=trips.session_id
                    )
                  )
            GROUP BY payment
            """,
            (date_text,),
        ).fetchall()

        totals = {
            PAYMENT_CASH: 0.0,
            PAYMENT_MP: 0.0,
            PAYMENT_UBER: 0.0,
            PAYMENT_OTHER: 0.0,
        }
        cash_received = 0.0
        change_given = 0.0

        for row in rows:
            payment = self._normalize_payment_for_report(row["payment"])
            totals[payment] = totals.get(payment, 0.0) + float(row["amount_total"] or 0.0)
            if payment == PAYMENT_CASH:
                cash_received += float(row["received_total"] or 0.0)
                change_given += float(row["change_total"] or 0.0)

        summaries = self.conn.execute(
            """
            SELECT summary.cash_collected, summary.mp_collected,
                   summary.app_collected
            FROM session_summaries summary
            JOIN work_sessions session ON session.id=summary.session_id
            WHERE substr(session.opened_at,1,10)=?
            """,
            (date_text,),
        ).fetchall()
        for summary in summaries:
            if summary["cash_collected"] is not None:
                totals[PAYMENT_CASH] += float(summary["cash_collected"])
            if summary["mp_collected"] is not None:
                totals[PAYMENT_MP] += float(summary["mp_collected"])
            if summary["app_collected"] is not None:
                totals[PAYMENT_UBER] += float(summary["app_collected"])

        total_day = self._range_metrics([date_text])["income"]
        classified_total = sum(totals.values())
        unclassified = max(total_day - classified_total, 0.0)
        cash_kept = totals[PAYMENT_CASH]

        screen = self.root.get_screen("cash")
        screen.cash_text = self.money(totals[PAYMENT_CASH])
        screen.mp_text = self.money(totals[PAYMENT_MP])
        screen.uber_text = self.money(totals[PAYMENT_UBER])
        screen.other_text = self.money(totals[PAYMENT_OTHER])
        screen.cash_received_text = f"Recibido: {self.money(cash_received)}"
        screen.change_text = f"Vuelto entregado: {self.money(change_given)}"
        screen.cash_kept_text = f"Efectivo neto por viajes: {self.money(cash_kept)}"
        screen.total_text = self.money(total_day)
        screen.reconciliation_text = (
            f"Falta clasificar {self.money(unclassified)} por medio de cobro. "
            "No lo asignamos automáticamente."
            if unclassified > 0.01
            else "Todos los cobros conocidos están clasificados."
        )

    def _normalize_payment_for_report(self, raw: str) -> str:
        try:
            return self._normalize_payment(raw)
        except ValidationError:
            return PAYMENT_OTHER

    def _sum_for_date(self, table: str, column: str, date_text: str) -> float:
        allowed = {
            ("trips", "amount"),
            ("trips", "km"),
            ("expenses", "amount"),
        }
        if (table, column) not in allowed:
            raise ValueError("Unsafe aggregate query rejected.")

        row = self.conn.execute(
            f"""
            SELECT COALESCE(SUM({column}),0) AS v
            FROM {table}
            WHERE substr(created_at,1,10)=?
            """,
            (date_text,),
        ).fetchone()
        return float(row["v"] or 0.0)

    def _percent(self, value: float, goal: float) -> float:
        if goal <= 0:
            return 0.0
        return min(max((value / goal) * 100.0, 0.0), 100.0)

    def _compact_number(self, value: float) -> str:
        return str(int(value)) if float(value).is_integer() else str(value)

    def fill_sessions(self):
        """Muestra jornadas cerradas por separado, de la más nueva a la más vieja."""
        try:
            screen = self.root.get_screen("sessions")
        except Exception:
            return
        lst = screen.ids.sessions_list
        lst.clear_widgets()
        rows = self.conn.execute(
            "SELECT * FROM work_sessions ORDER BY id DESC LIMIT ?",
            (MAX_HISTORY_ITEMS,),
        ).fetchall()
        if not rows:
            lst.add_widget(TwoLineListItem(
                text="Todavía no hay jornadas",
                secondary_text="Abrí y cerrá una jornada para verla acá.",
            ))
            return
        for row in rows:
            sid = int(row["id"])
            try:
                metrics = self._session_metrics(sid)
            except Exception:
                LOGGER.exception("Could not calculate session %s", sid)
                continue
            status = "Abierta" if row["status"] == "OPEN" else "Cerrada"
            opened = row["opened_at"] or ""
            closed = row["closed_at"] or "en curso"
            item = TwoLineListItem(
                text=f"Jornada #{sid} · {status} · {opened}",
                secondary_text=(
                    f"{self.money(metrics['revenue'])} · {metrics['worked_km']:.1f} km · "
                    f"{metrics['fuel_liters']:.2f} L · Neto {self.money(metrics['net'])}"
                ),
            )
            item.bind(on_release=lambda _item, session_id=sid: self.show_session_summary(session_id))
            lst.add_widget(item)

    def show_session_summary(self, session_id: int):
        try:
            session = self.conn.execute(
                "SELECT * FROM work_sessions WHERE id=?", (session_id,)
            ).fetchone()
            if session is None:
                raise ValidationError("No se encontró la jornada.")
            metrics = self._session_metrics(session_id)
            closing_cash = session["closing_cash"]
            cash_difference = session["cash_difference"]
            lines = [
                f"Inicio: {session['opened_at']}",
                f"Cierre: {session['closed_at'] or 'En curso'}",
                f"Ingresos registrados: {self.money(metrics['revenue'])}",
                f"Comisión Uber informada: {self.money(metrics['uber_fee'])}",
                f"Facturación conocida: {self.money(metrics['known_billing'])}",
                f"Viajes: {metrics['trips']}",
                f"Km trabajados: {metrics['worked_km']:.1f} km",
                f"Nafta consumida: {metrics['fuel_liters']:.2f} L",
                f"A reponer: {self.money(metrics['fuel_cost'])}",
                f"Nafta cargada: {metrics['fuel_loaded_liters']:.2f} L · {self.money(metrics['fuel_loaded_amount'])}",
                f"Otros gastos: {self.money(metrics['operating_expenses'])}",
                f"Ganancia real estimada: {self.money(metrics['net'])}",
                f"Caja esperada: {self.money(metrics['cash_expected'])}",
            ]
            if closing_cash is not None:
                lines.append(f"Caja contada: {self.money(float(closing_cash))}")
            if cash_difference is not None:
                diff = float(cash_difference)
                sign = "+" if diff >= 0 else "-"
                lines.append(f"Diferencia de caja: {sign}{self.money(abs(diff))}")
            self.show_message(f"Resumen · Jornada #{session_id}", "\n".join(lines))
        except ValidationError as exc:
            self.show_message("Jornada", str(exc))
        except Exception:
            LOGGER.exception("Could not show session summary")
            self.show_message("Error", "No se pudo abrir el resumen de la jornada.")

    def fill_lists(self):
        self._fill_trip_list()
        self._fill_expense_list()
        self._fill_fuel_list()
        self._fill_maintenance_list()

    def _fill_trip_list(self):
        target = self.root.get_screen("trips").ids.trips_list
        target.clear_widgets()

        rows = self.conn.execute(
            """
            SELECT id, created_at, amount, payment, km, duration,
                   cash_received, change_given, uber_fee
            FROM trips
            ORDER BY id DESC
            LIMIT ?
            """,
            (MAX_HISTORY_ITEMS,),
        ).fetchall()

        if not rows:
            target.add_widget(
                TwoLineListItem(
                    text="Todavía no hay viajes",
                    secondary_text="Abrí una jornada y cargá tu primer ingreso.",
                )
            )
            return

        for row in rows:
            cash_detail = ""
            if row["payment"] == PAYMENT_CASH and row["cash_received"] is not None:
                cash_detail = (
                    f" · Recibido {self.money(row['cash_received'])}"
                    f" · Vuelto {self.money(row['change_given'] or 0)}"
                )

            item = TwoLineListItem(
                text=(
                    f"{self.money(row['amount'])} ingreso · {row['payment']}"
                    + (f" · Comisión {self.money(row['uber_fee'])}" if row["uber_fee"] else "")
                ),
                secondary_text=(
                    f"{row['created_at']} · {row['km']:.1f} km"
                    f" · {row['duration']} min{cash_detail}"
                ),
            )
            item.bind(
                on_release=lambda _x, trip_id=row["id"]:
                self.confirm_delete_trip(trip_id)
            )
            target.add_widget(item)

    def _fill_expense_list(self):
        target = self.root.get_screen("expenses").ids.expenses_list
        target.clear_widgets()

        rows = self.conn.execute(
            """
            SELECT created_at, category, description, amount
            FROM expenses
            ORDER BY id DESC
            LIMIT ?
            """,
            (MAX_HISTORY_ITEMS,),
        ).fetchall()

        if not rows:
            target.add_widget(
                TwoLineListItem(
                    text="Todavía no hay gastos",
                    secondary_text="Los gastos y mantenimientos aparecerán acá.",
                )
            )
            return

        for row in rows:
            target.add_widget(
                TwoLineListItem(
                    text=f"{row['category']} · {self.money(row['amount'])}",
                    secondary_text=(
                        f"{row['created_at']} · {row['description'] or ''}"
                    ),
                )
            )

    def _fill_fuel_list(self):
        target = self.root.get_screen("fuel").ids.fuel_list
        target.clear_widgets()

        rows = self.conn.execute(
            """
            SELECT id, created_at, amount, liters, odometer
            FROM fuel
            ORDER BY id DESC
            LIMIT ?
            """,
            (MAX_HISTORY_ITEMS,),
        ).fetchall()

        if not rows:
            target.add_widget(
                TwoLineListItem(
                    text="Todavía no hay cargas",
                    secondary_text="Registrá combustible para conservar su historial.",
                )
            )
            return

        for row in rows:
            item = TwoLineListItem(
                text=f"{self.money(row['amount'])} · {row['liters']:.2f} L",
                secondary_text=(
                    f"{row['created_at']} · {row['odometer']:.0f} km · TOCÁ PARA ELIMINAR"
                ),
            )
            item.bind(
                on_release=lambda _x, fuel_id=row["id"]: self.confirm_delete_fuel(fuel_id)
            )
            target.add_widget(item)

    def _fill_maintenance_list(self):
        try:
            target = self.root.get_screen("maintenance").ids.maintenance_list
        except Exception:
            return
        target.clear_widgets()
        rows = self.conn.execute(
            """
            SELECT id,created_at,category,description,odometer,amount,
                   next_due_date,next_due_odometer,status
            FROM maintenance_records
            ORDER BY id DESC LIMIT ?
            """,
            (MAX_HISTORY_ITEMS,),
        ).fetchall()
        if not rows:
            target.add_widget(
                TwoLineListItem(
                    text="Todavía no hay mantenimientos",
                    secondary_text="Registrá el primero para recibir el próximo aviso.",
                )
            )
            return
        for row in rows:
            due = []
            if row["next_due_odometer"]:
                due.append(f"próximo {float(row['next_due_odometer']):.0f} km")
            if row["next_due_date"]:
                due.append(str(row["next_due_date"]))
            amount = f" · {self.money(row['amount'])}" if row["amount"] else ""
            item = TwoLineListItem(
                text=f"{row['category']}{amount}",
                secondary_text=(
                    f"{row['created_at']} · {float(row['odometer'] or 0):.0f} km"
                    + (" · " + " · ".join(due) if due else "")
                ),
            )
            item.bind(
                on_release=lambda _item, record_id=int(row["id"]):
                self.show_maintenance_record(record_id)
            )
            target.add_widget(item)

    def show_maintenance_record(self, record_id: int):
        row = self.conn.execute(
            "SELECT * FROM maintenance_records WHERE id=?", (record_id,)
        ).fetchone()
        if row is None:
            return
        lines = [
            f"Fecha: {row['created_at']}",
            f"Odómetro: {float(row['odometer'] or 0):.0f} km",
            f"Costo: {self.money(row['amount'] or 0)}",
        ]
        if row["description"]:
            lines.append(f"Detalle: {row['description']}")
        if row["next_due_odometer"]:
            lines.append(f"Próximo kilometraje: {float(row['next_due_odometer']):.0f} km")
        if row["next_due_date"]:
            lines.append(f"Próxima fecha: {row['next_due_date']}")
        self.show_message(str(row["category"]), "\n".join(lines))

    def confirm_delete_latest_fuel(self):
        row = self.conn.execute("SELECT id FROM fuel ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            self.show_message("Combustible", "No hay cargas para eliminar.")
            return
        self.confirm_delete_fuel(int(row["id"]))

    def confirm_delete_fuel(self, fuel_id: int):
        dialog = MDDialog(
            title="Eliminar carga",
            text="¿Querés eliminar esta carga de combustible y su gasto asociado?",
            buttons=[
                MDFlatButton(text="CANCELAR", on_release=lambda _x: dialog.dismiss()),
                MDFlatButton(
                    text="ELIMINAR",
                    on_release=lambda _x: self.delete_fuel(fuel_id, dialog),
                ),
            ],
        )
        dialog.open()

    def delete_fuel(self, fuel_id: int, dialog):
        try:
            row = self.conn.execute(
                "SELECT * FROM fuel WHERE id=?", (fuel_id,)
            ).fetchone()
            if row is None:
                raise ValidationError("La carga ya no existe.")
            with self.transaction():
                # La 4.2 guardaba la carga también como gasto. Eliminamos el par.
                self.conn.execute(
                    """
                    DELETE FROM expenses
                    WHERE id=(
                        SELECT id FROM expenses
                        WHERE session_id=? AND created_at=?
                          AND lower(category)='combustible' AND amount=?
                        ORDER BY id DESC LIMIT 1
                    )
                    """,
                    (row["session_id"], row["created_at"], row["amount"]),
                )
                self.conn.execute("DELETE FROM fuel WHERE id=?", (fuel_id,))
            dialog.dismiss()
            self.refresh_all()
        except ValidationError as exc:
            self.show_message("No se pudo eliminar", str(exc))
        except Exception:
            LOGGER.exception("Unexpected error while deleting fuel id=%s", fuel_id)
            self.show_message("No se pudo eliminar", "La carga no fue eliminada.")

    def show_message(self, title: str, message: str):
        dialog = MDDialog(
            title=title,
            text=message,
            buttons=[
                MDFlatButton(
                    text="OK",
                    on_release=lambda _x: dialog.dismiss(),
                )
            ],
        )
        dialog.open()

    def input_dialog(self, title, fields, callback):
        box = MDBoxLayout(
            orientation="vertical",
            spacing=dp(8),
            adaptive_height=True,
        )
        widgets = {}

        for key, hint, numeric in fields:
            field = MDTextField(hint_text=hint)
            if key == "payment":
                field.text = PAYMENT_CASH
            elif key == "odometer":
                current_odometer = self._current_odometer()
                field.text = self._compact_number(current_odometer) if current_odometer > 0 else ""
            if numeric:
                field.input_filter = "float"
            widgets[key] = field
            box.add_widget(field)

        content = box
        if len(fields) > 4:
            scroll = ScrollView(
                do_scroll_x=False,
                size_hint_y=None,
                height=dp(420),
            )
            scroll.add_widget(box)
            content = scroll

        dialog = MDDialog(
            title=title,
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(
                    text="CANCELAR",
                    on_release=lambda _x: dialog.dismiss(),
                ),
                MDFlatButton(
                    text="GUARDAR",
                    on_release=lambda _x: callback(dialog, widgets),
                ),
            ],
        )
        dialog.open()

    def open_trip_dialog(self):
        if self._active_session() is None:
            self.show_message("Abrí una jornada", "Primero abrí la jornada para registrar viajes.")
            return
        self.prepare_new_trip()
        self.root.current = "new_trip"

    def prepare_new_trip(self):
        screen = self.root.get_screen("new_trip")
        screen.payment_method = PAYMENT_UBER
        screen.cash_received_value = 0
        screen.cash_received_text = self.money(0)
        screen.change_preview_text = "Vuelto: $0"
        screen.cash_bill_stack = []
        screen.ids.trip_amount.text = ""
        screen.ids.trip_uber_fee.text = ""

    def cancel_new_trip(self):
        self.prepare_new_trip()
        self.root.current = "dashboard"
        self.refresh_all()

    def select_trip_payment(self, method: str):
        if method not in PAYMENT_METHODS:
            LOGGER.error("Rejected unknown payment method: %r", method)
            return
        screen = self.root.get_screen("new_trip")
        screen.payment_method = method
        if method != PAYMENT_CASH:
            screen.cash_received_value = 0
            screen.cash_received_text = self.money(0)
            screen.cash_bill_stack = []

    def add_banknote(self, value: float):
        screen = self.root.get_screen("new_trip")
        if screen.payment_method != PAYMENT_CASH:
            return
        value = float(value)
        if value <= 0:
            return
        screen.cash_bill_stack = list(screen.cash_bill_stack) + [value]
        screen.cash_received_value = sum(screen.cash_bill_stack)
        screen.cash_received_text = self.money(screen.cash_received_value)
        self._update_cash_change_preview()

    def undo_last_banknote(self):
        screen = self.root.get_screen("new_trip")
        stack = list(screen.cash_bill_stack)
        if stack:
            stack.pop()
        screen.cash_bill_stack = stack
        screen.cash_received_value = sum(stack)
        screen.cash_received_text = self.money(screen.cash_received_value)
        self._update_cash_change_preview()

    def reset_cash_received(self):
        screen = self.root.get_screen("new_trip")
        screen.cash_bill_stack = []
        screen.cash_received_value = 0
        screen.cash_received_text = self.money(0)
        screen.change_preview_text = "Vuelto: $0"

    def _update_cash_change_preview(self):
        screen = self.root.get_screen("new_trip")
        try:
            amount = float((screen.ids.trip_amount.text or "0").replace(",", "."))
        except ValueError:
            amount = 0.0
        change = max(float(screen.cash_received_value) - amount, 0.0)
        screen.change_preview_text = f"Vuelto: {self.money(change)}"

    def fast_save_payment(self, method: str):
        self.select_trip_payment(method)
        self.save_trip_screen()

    def cash_exact_and_save(self):
        screen = self.root.get_screen("new_trip")
        try:
            amount = self._parse_non_negative_float(
                screen.ids.trip_amount.text, "Importe", allow_zero=False
            )
        except ValidationError as exc:
            self.show_message("Revisá los datos", str(exc))
            return
        screen.payment_method = PAYMENT_CASH
        screen.cash_bill_stack = [amount]
        screen.cash_received_value = amount
        screen.cash_received_text = self.money(amount)
        screen.change_preview_text = "Vuelto: $0"
        self.save_trip_screen()

    def save_trip_screen(self):
        screen = self.root.get_screen("new_trip")
        try:
            session_id = self._require_active_session()
            amount = self._parse_non_negative_float(
                screen.ids.trip_amount.text,
                "Importe",
                allow_zero=False,
            )
            uber_fee = self._parse_non_negative_float(
                screen.ids.trip_uber_fee.text or "0",
                "Comisión Uber",
            )
            # Fast Driver UX: no pedimos km ni duración en cada viaje.
            # Los km reales de trabajo salen del odómetro de apertura/cierre.
            km = 0.0
            duration = 0
            payment = self._normalize_payment(screen.payment_method)

            cash_received: Optional[float] = None
            change_given: Optional[float] = None

            if payment == PAYMENT_CASH:
                cash_received = float(screen.cash_received_value)
                if cash_received <= 0:
                    raise ValidationError(
                        "Seleccioná los billetes que te entregó el pasajero."
                    )
                if cash_received < amount:
                    raise ValidationError(
                        f"El efectivo recibido no alcanza. "
                        f"Faltan {self.money(amount - cash_received)}."
                    )
                change_given = cash_received - amount

            now = datetime.now().strftime(DATETIME_FORMAT)
            with self.transaction():
                self.conn.execute(
                    """
                    INSERT INTO trips(
                        created_at, amount, payment, km, duration,
                        cash_received, change_given, session_id, uber_fee
                    )
                    VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        now,
                        amount,
                        payment,
                        km,
                        duration,
                        cash_received,
                        change_given,
                        session_id,
                        uber_fee,
                    ),
                )

            LOGGER.info(
                "Trip saved from visual entry: amount=%s uber_fee=%s payment=%s "
                "cash_received=%s change=%s km=%s duration=%s",
                amount,
                uber_fee,
                payment,
                cash_received,
                change_given,
                km,
                duration,
            )

            self.prepare_new_trip()
            self.root.current = "dashboard"
            self.refresh_all()

            detail = f"Sumaste {self.money(amount)} a la jornada."
            if payment == PAYMENT_CASH:
                detail += f" Vuelto: {self.money(change_given or 0)}."
            self.show_message("¡Viaje sumado!", detail)

        except ValidationError as exc:
            self.show_message("Revisá los datos", str(exc))
        except Exception:
            LOGGER.exception("Unexpected error while saving visual trip.")
            self.show_message(
                "Error inesperado",
                "No se pudo guardar el viaje. Tus datos anteriores siguen intactos.",
            )

    def confirm_delete_trip(self, trip_id: int):
        dialog = MDDialog(
            title="Eliminar viaje",
            text="¿Querés eliminar este viaje?",
            buttons=[
                MDFlatButton(
                    text="CANCELAR",
                    on_release=lambda _x: dialog.dismiss(),
                ),
                MDFlatButton(
                    text="ELIMINAR",
                    on_release=lambda _x:
                    self.delete_trip(trip_id, dialog),
                ),
            ],
        )
        dialog.open()

    def delete_trip(self, trip_id: int, dialog):
        try:
            with self.transaction():
                self.conn.execute(
                    "DELETE FROM trips WHERE id=?",
                    (trip_id,),
                )
            dialog.dismiss()
            self.refresh_all()
            LOGGER.info("Trip deleted: id=%s", trip_id)
        except Exception:
            LOGGER.exception("Unexpected error while deleting trip id=%s", trip_id)
            self.show_message(
                "No se pudo eliminar",
                "El viaje no fue eliminado.",
            )

    def open_expense_dialog(self):
        if self._active_session() is None:
            self.show_message("Abrí una jornada", "Primero abrí la jornada para registrar gastos.")
            return
        fields = [
            ("category", "Categoría", False),
            ("description", "Descripción", False),
            ("amount", "Importe", True),
            ("payment", "Pago: Efectivo / Mercado Pago / Otro", False),
        ]
        self.input_dialog("Nuevo gasto", fields, self.save_expense)

    def save_expense(self, dialog, widgets):
        try:
            session_id = self._require_active_session()
            amount = self._parse_non_negative_float(
                widgets["amount"].text,
                "Importe",
                allow_zero=False,
            )
            category = (widgets["category"].text or "Otro").strip()
            description = (widgets["description"].text or "").strip()
            payment = self._normalize_payment(widgets["payment"].text)
            now = datetime.now().strftime(DATETIME_FORMAT)

            with self.transaction():
                self.conn.execute(
                    """
                    INSERT INTO expenses(
                        created_at, category, description, amount, payment, session_id
                    )
                    VALUES(?,?,?,?,?,?)
                    """,
                    (now, category, description, amount, payment, session_id),
                )

            dialog.dismiss()
            self.refresh_all()
            LOGGER.info("Expense saved: category=%s amount=%s", category, amount)

        except ValidationError as exc:
            self.show_message("Revisá los datos", str(exc))
        except Exception:
            LOGGER.exception("Unexpected error while saving expense.")
            self.show_message(
                "Error inesperado",
                "No se pudo guardar el gasto.",
            )

    def open_fuel_dialog(self):
        if self._active_session() is None:
            self.show_message("Abrí una jornada", "Primero abrí la jornada para registrar combustible.")
            return
        fields = [
            ("amount", "Importe", True),
            ("liters", "Litros", True),
            ("odometer", "Odómetro", True),
            ("payment", "Pago: Efectivo / Mercado Pago / Otro", False),
        ]
        self.input_dialog("Combustible", fields, self.save_fuel)

    def save_fuel(self, dialog, widgets):
        try:
            session_id = self._require_active_session()
            amount = self._parse_non_negative_float(
                widgets["amount"].text,
                "Importe",
                allow_zero=False,
            )
            liters = self._parse_non_negative_float(
                widgets["liters"].text,
                "Litros",
                allow_zero=False,
            )
            odometer = self._parse_non_negative_float(
                widgets["odometer"].text,
                "Odómetro",
            )
            payment = self._normalize_payment(widgets["payment"].text)
            now = datetime.now().strftime(DATETIME_FORMAT)

            with self.transaction():
                self.conn.execute(
                    """
                    INSERT INTO fuel(
                        created_at, amount, liters, odometer, payment, session_id
                    )
                    VALUES(?,?,?,?,?,?)
                    """,
                    (now, amount, liters, odometer, payment, session_id),
                )
                self.conn.execute(
                    """
                    INSERT INTO expenses(
                        created_at, category, description, amount, payment, session_id
                    )
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        now,
                        "Combustible",
                        f"Carga {liters:.2f} L",
                        amount,
                        payment,
                        session_id,
                    ),
                )

            dialog.dismiss()
            self.refresh_all()
            LOGGER.info(
                "Fuel saved: amount=%s liters=%s odometer=%s",
                amount,
                liters,
                odometer,
            )

        except ValidationError as exc:
            self.show_message("Revisá los datos", str(exc))
        except Exception:
            LOGGER.exception("Unexpected error while saving fuel.")
            self.show_message(
                "Error inesperado",
                "No se pudo guardar la carga de combustible.",
            )

    def set_tank_percent(self, percent: float):
        screen = self.root.get_screen("wellness_map")
        screen.ids.tank_percent.text = self._compact_number(float(percent))
        self.calculate_refuel()

    def calculate_refuel(self):
        screen = self.root.get_screen("wellness_map")
        try:
            current_percent = self._parse_non_negative_float(
                screen.ids.tank_percent.text,
                "Combustible actual",
            )
            if current_percent > 100:
                raise ValidationError("Combustible actual: usá un porcentaje entre 0 y 100.")
            capacity = self._setting_float("tank_capacity", DEFAULT_TANK_CAPACITY)
            price = self._setting_float("fuel_price", DEFAULT_FUEL_PRICE)
            liters = capacity * (100.0 - current_percent) / 100.0
            cost = liters * price
            screen.refuel_result_text = (
                f"Para llenar: {liters:.1f} L · aproximadamente {self.money(cost)}"
            )
        except ValidationError as exc:
            screen.refuel_result_text = str(exc)

    def open_maintenance_dialog(self):
        fields = [
            ("category", "Tipo: aceite, frenos, cubiertas...", False),
            ("description", "Detalle del trabajo", False),
            ("odometer", "Odómetro actual", True),
            ("amount", "Costo (0 si fue solo un control)", True),
            ("next_due_odometer", "Próximo control (km, opcional)", True),
            ("next_due_date", "Próxima fecha DD/MM/AAAA (opcional)", False),
            ("payment", "Pago: Efectivo / Mercado Pago / Otro", False),
        ]
        self.input_dialog("Registrar mantenimiento", fields, self.save_maintenance)

    def save_maintenance(self, dialog, widgets):
        try:
            category = (widgets["category"].text or "Mantenimiento general").strip()
            description = (widgets["description"].text or "").strip()
            odometer_raw = widgets["odometer"].text.strip()
            odometer = self._parse_non_negative_float(
                odometer_raw if odometer_raw else str(self._current_odometer()),
                "Odómetro",
            )
            amount = self._parse_non_negative_float(
                widgets["amount"].text or "0",
                "Costo",
            )
            due_km_raw = widgets["next_due_odometer"].text.strip()
            next_due_odometer = (
                self._parse_non_negative_float(due_km_raw, "Próximo control")
                if due_km_raw else None
            )
            next_due_date = widgets["next_due_date"].text.strip()
            if next_due_date:
                try:
                    datetime.strptime(next_due_date, DATE_FORMAT)
                except ValueError:
                    raise ValidationError("Próxima fecha: usá el formato DD/MM/AAAA.")
            payment = self._normalize_payment(widgets["payment"].text)
            active = self._active_session()
            session_id = int(active["id"]) if active is not None else None
            now = datetime.now().strftime(DATETIME_FORMAT)
            with self.transaction():
                expense_id = None
                if amount > 0:
                    cursor = self.conn.execute(
                        """
                        INSERT INTO expenses(
                            created_at,category,description,amount,payment,session_id
                        ) VALUES(?,?,?,?,?,?)
                        """,
                        (
                            now,
                            "Mantenimiento",
                            f"{category}: {description}".strip(": "),
                            amount,
                            payment,
                            session_id,
                        ),
                    )
                    expense_id = int(cursor.lastrowid)
                self.conn.execute(
                    """
                    INSERT INTO maintenance_records(
                        created_at,category,description,odometer,amount,
                        next_due_date,next_due_odometer,payment,session_id,
                        expense_id,status
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,'COMPLETED')
                    """,
                    (
                        now, category, description, odometer, amount,
                        next_due_date or None, next_due_odometer, payment,
                        session_id, expense_id,
                    ),
                )
            dialog.dismiss()
            self.refresh_all()
            self.show_message(
                "Mantenimiento guardado",
                "El control quedó en el historial"
                + (" y su costo se registró como gasto." if amount > 0 else "."),
            )
        except ValidationError as exc:
            self.show_message("Revisá los datos", str(exc))
        except Exception:
            LOGGER.exception("Unexpected error while saving maintenance")
            self.show_message("Error", "No se pudo guardar el mantenimiento.")

    def save_settings(self):
        screen = self.root.get_screen("settings")
        try:
            daily_goal = self._parse_non_negative_float(
                screen.ids.daily_goal.text,
                "Meta diaria",
                allow_zero=False,
            )
            weekly_goal = self._parse_non_negative_float(
                screen.ids.weekly_goal.text,
                "Meta semanal",
                allow_zero=False,
            )
            vehicle = (screen.ids.vehicle.text or DEFAULT_VEHICLE).strip()
            fuel_consumption = self._parse_non_negative_float(
                screen.ids.fuel_consumption.text, "Consumo", allow_zero=False
            )
            fuel_price = self._parse_non_negative_float(
                screen.ids.fuel_price.text, "Precio de nafta", allow_zero=False
            )
            tank_capacity = self._parse_non_negative_float(
                screen.ids.tank_capacity.text, "Capacidad del tanque", allow_zero=False
            )
            assistant_min_hourly = self._parse_non_negative_float(
                screen.ids.assistant_min_hourly.text, "Mínimo por hora", allow_zero=False
            )
            assistant_min_per_km = self._parse_non_negative_float(
                screen.ids.assistant_min_per_km.text, "Mínimo por km", allow_zero=False
            )
            assistant_max_pickup_km = self._parse_non_negative_float(
                screen.ids.assistant_max_pickup_km.text, "Pickup máximo", allow_zero=False
            )
            ai_server_url = (screen.ids.ai_server_url.text or "").strip().rstrip("/")
            ai_access_token = (screen.ids.ai_access_token.text or "").strip()
            if ai_server_url and not ai_server_url.startswith("https://"):
                raise ValidationError("La dirección del servidor de IA debe comenzar con https://")

            with self.transaction():
                self.conn.execute(
                    "INSERT OR REPLACE INTO settings(key,value) VALUES('daily_goal',?)",
                    (str(daily_goal),),
                )
                self.conn.execute(
                    "INSERT OR REPLACE INTO settings(key,value) VALUES('weekly_goal',?)",
                    (str(weekly_goal),),
                )
                self.conn.execute(
                    "INSERT OR REPLACE INTO settings(key,value) VALUES('vehicle',?)",
                    (vehicle,),
                )
                self.conn.execute(
                    "INSERT OR REPLACE INTO settings(key,value) VALUES('fuel_consumption',?)",
                    (str(fuel_consumption),),
                )
                self.conn.execute(
                    "INSERT OR REPLACE INTO settings(key,value) VALUES('fuel_price',?)",
                    (str(fuel_price),),
                )
                self.conn.execute(
                    "INSERT OR REPLACE INTO settings(key,value) VALUES('tank_capacity',?)",
                    (str(tank_capacity),),
                )
                self.conn.execute(
                    "INSERT OR REPLACE INTO settings(key,value) VALUES('assistant_min_hourly',?)",
                    (str(assistant_min_hourly),),
                )
                self.conn.execute(
                    "INSERT OR REPLACE INTO settings(key,value) VALUES('assistant_min_per_km',?)",
                    (str(assistant_min_per_km),),
                )
                self.conn.execute(
                    "INSERT OR REPLACE INTO settings(key,value) VALUES('assistant_max_pickup_km',?)",
                    (str(assistant_max_pickup_km),),
                )
                self.conn.execute(
                    "INSERT OR REPLACE INTO settings(key,value) VALUES('ai_server_url',?)",
                    (ai_server_url,),
                )
                self.conn.execute(
                    "INSERT OR REPLACE INTO settings(key,value) VALUES('ai_access_token',?)",
                    (ai_access_token,),
                )

            self._sync_android_assistant_settings()
            self.refresh_all()
            self.show_message("Configuración", "Cambios y valor de nafta actualizados correctamente.")
            LOGGER.info(
                "Settings saved: daily_goal=%s weekly_goal=%s vehicle=%s fuel_price=%s",
                daily_goal,
                weekly_goal,
                vehicle,
                fuel_price,
            )

        except ValidationError as exc:
            self.show_message("Revisá la configuración", str(exc))
        except Exception:
            LOGGER.exception("Unexpected error while saving settings.")
            self.show_message(
                "Error inesperado",
                "No se pudo guardar la configuración.",
            )

    def _share_excel_on_android(self, export_path: Path):
        from jnius import autoclass, cast

        if not export_path.is_file() or export_path.stat().st_size <= 0:
            raise FileNotFoundError(f"Excel export not found: {export_path}")

        ClipData = autoclass("android.content.ClipData")
        File = autoclass("java.io.File")
        FileProvider = autoclass("androidx.core.content.FileProvider")
        Intent = autoclass("android.content.Intent")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")

        current = PythonActivity.mActivity
        authority = f"{current.getPackageName()}.fileprovider"
        uri = FileProvider.getUriForFile(current, authority, File(str(export_path)))
        intent = Intent(Intent.ACTION_SEND)
        intent.setType(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        intent.putExtra(Intent.EXTRA_STREAM, cast("android.os.Parcelable", uri))
        intent.putExtra(Intent.EXTRA_SUBJECT, f"Driver Control {APP_VERSION}")
        intent.setClipData(ClipData.newRawUri("Excel de Driver Control", uri))
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        chooser = Intent.createChooser(intent, "Compartir Excel de Driver Control")
        chooser.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        current.startActivity(chooser)

    def export_database_to_xlsx(self):
        try:
            from excel_exporter import export_driver_control_xlsx

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = (
                Path(self.user_data_dir)
                / f"driver_control_export_{timestamp}.xlsx"
            )
            self.conn.commit()
            counts = export_driver_control_xlsx(
                self.conn,
                export_path,
                APP_VERSION,
            )

            if platform == "android":
                self._share_excel_on_android(export_path)
                detail = "Elegí dónde guardar o compartir el archivo."
            else:
                detail = f"Archivo guardado en:\n{export_path.resolve()}"

            self.show_message(
                "Excel creado",
                f"{counts['jornadas']} jornadas · {counts['viajes']} viajes · "
                f"{counts['gastos']} gastos · {counts['cargas']} cargas · "
                f"{counts.get('mantenimientos', 0)} mantenimientos\n{detail}",
            )
            LOGGER.info("Complete database exported to XLSX: %s", export_path)
        except Exception:
            LOGGER.exception("Error exporting data to XLSX.")
            self.show_message("Error", "No se pudo crear o compartir el archivo Excel.")


if __name__ == "__main__":
    DriverControlApp().run()
