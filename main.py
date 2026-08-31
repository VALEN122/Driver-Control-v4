import csv
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from kivy.lang import Builder
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import NumericProperty, StringProperty
from kivy.uix.screenmanager import Screen
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import TwoLineListItem
from kivymd.uix.textfield import MDTextField


# ============================================================
# Driver Control v4.1.0
# Mejoras aplicadas:
# - Valor actual de nafta dinámico y persistente con respaldo histórico.
# - Exportación completa de datos operativos a formato CSV.
# - Verificación preventiva de recursos gráficos (assets de billetes).
# - Prevención de micro-cortes y optimización en la gestión de jornadas.
# ============================================================

APP_NAME = "Driver Control"
APP_VERSION = "4.3.2"
DB_FILE = "driver_control.db"
DATE_FORMAT = "%d/%m/%Y"
DATETIME_FORMAT = "%d/%m/%Y %H:%M"

DEFAULT_DAILY_GOAL = 70000.0
DEFAULT_WEEKLY_GOAL = 400000.0
DEFAULT_VEHICLE = "Volkswagen Gol Trend 2015"
DEFAULT_FUEL_CONSUMPTION = 8.0  # L/100 km
DEFAULT_FUEL_PRICE = 2048.0  # $/L; editable en Configuración

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

ScreenManager:
    DashboardScreen:
    TripEntryScreen:
    TripsScreen:
    ExpensesScreen:
    FuelScreen:
    CashScreen:
    SettingsScreen:

<DashboardScreen>:
    name: "dashboard"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Driver Control"
            md_bg_color: app.bg_color

        ScrollView:
            MDBoxLayout:
                orientation: "vertical"
                padding: dp(16)
                spacing: dp(14)
                adaptive_height: True

                MDLabel:
                    text: "Resumen de hoy"
                    font_style: "H5"
                    bold: True
                    size_hint_y: None
                    height: dp(40)

                MDLabel:
                    text: root.current_datetime_text
                    theme_text_color: "Custom"
                    text_color: app.muted_color
                    size_hint_y: None
                    height: dp(28)

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [18,18,18,18]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(196)

                    MDLabel:
                        text: "JORNADA"
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        size_hint_y: None
                        height: dp(24)

                    MDLabel:
                        text: root.session_status_text
                        font_style: "H5"
                        bold: True
                        size_hint_y: None
                        height: dp(38)

                    MDLabel:
                        text: root.session_time_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        size_hint_y: None
                        height: dp(30)

                    MDRaisedButton:
                        text: root.session_action_text
                        size_hint_y: None
                        height: dp(48)
                        on_release: app.toggle_work_session()

                MDGridLayout:
                    cols: 2
                    adaptive_height: True
                    spacing: dp(10)

                    StatCard:
                        MDLabel:
                            text: "FACTURACIÓN"
                            theme_text_color: "Custom"
                            text_color: app.muted_color
                            font_style: "Caption"
                        MDLabel:
                            text: root.revenue_text
                            font_style: "H5"
                            bold: True

                    StatCard:
                        MDLabel:
                            text: "GANANCIA NETA"
                            theme_text_color: "Custom"
                            text_color: app.muted_color
                            font_style: "Caption"
                        MDLabel:
                            text: root.net_text
                            font_style: "H5"
                            bold: True

                    StatCard:
                        MDLabel:
                            text: "KILÓMETROS"
                            theme_text_color: "Custom"
                            text_color: app.muted_color
                            font_style: "Caption"
                        MDLabel:
                            text: root.km_text
                            font_style: "H5"
                            bold: True

                    StatCard:
                        MDLabel:
                            text: "VIAJES"
                            theme_text_color: "Custom"
                            text_color: app.muted_color
                            font_style: "Caption"
                        MDLabel:
                            text: root.trips_text
                            font_style: "H5"
                            bold: True

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(7)
                    radius: [16,16,16,16]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(150)

                    MDLabel:
                        text: "COMBUSTIBLE DE LA JORNADA"
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        font_style: "Caption"
                        size_hint_y: None
                        height: dp(24)
                    MDLabel:
                        text: root.fuel_used_text
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(34)
                    MDLabel:
                        text: root.fuel_reserve_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        size_hint_y: None
                        height: dp(34)

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [16,16,16,16]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(154)

                    MDLabel:
                        text: "Meta diaria"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(30)

                    MDLabel:
                        text: root.goal_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        size_hint_y: None
                        height: dp(26)

                    MDProgressBar:
                        value: root.goal_percent
                        max: 100
                        size_hint_y: None
                        height: dp(6)

                    MDLabel:
                        text: root.daily_remaining_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        size_hint_y: None
                        height: dp(26)

                MDCard:
                    orientation: "vertical"
                    padding: dp(16)
                    spacing: dp(8)
                    radius: [16,16,16,16]
                    md_bg_color: app.card_color
                    size_hint_y: None
                    height: dp(162)

                    MDLabel:
                        text: "Meta semanal"
                        font_style: "H6"
                        bold: True
                        size_hint_y: None
                        height: dp(30)

                    MDLabel:
                        text: root.weekly_goal_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        size_hint_y: None
                        height: dp(26)

                    MDProgressBar:
                        value: root.weekly_goal_percent
                        max: 100
                        size_hint_y: None
                        height: dp(6)

                    MDLabel:
                        text: root.weekly_remaining_text
                        theme_text_color: "Custom"
                        text_color: app.muted_color
                        size_hint_y: None
                        height: dp(26)

                MDRaisedButton:
                    text: "+ Nuevo viaje"
                    size_hint_y: None
                    height: dp(48)
                    on_release: app.open_trip_dialog()

                MDRaisedButton:
                    text: "+ Nuevo gasto"
                    size_hint_y: None
                    height: dp(48)
                    on_release: app.open_expense_dialog()

                MDRaisedButton:
                    text: "Caja de hoy"
                    size_hint_y: None
                    height: dp(48)
                    on_release: app.go("cash")

        MDBoxLayout:
            size_hint_y: None
            height: dp(60)
            spacing: dp(2)
            md_bg_color: app.card_color

            MDFlatButton:
                text: "Inicio"
                on_release: app.go("dashboard")

            MDFlatButton:
                text: "Viajes"
                on_release: app.go("trips")

            MDFlatButton:
                text: "Gastos"
                on_release: app.go("expenses")

            MDFlatButton:
                text: "Nafta"
                on_release: app.go("fuel")

            MDFlatButton:
                text: "Más"
                on_release: app.go("settings")


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
                    hint_text: "Ej: 7350"
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
                    text: "Uber, Mercado Pago y Otro se guardan al tocarlos."
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
            title: "Viajes"
            left_action_items: [["arrow-left", lambda x: app.go("dashboard")]]
            md_bg_color: app.bg_color

        MDRaisedButton:
            text: "+ Cargar viaje"
            size_hint_y: None
            height: dp(48)
            on_release: app.open_trip_dialog()

        ScrollView:
            MDList:
                id: trips_list
                adaptive_height: True


<ExpensesScreen>:
    name: "expenses"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Gastos"
            left_action_items: [["arrow-left", lambda x: app.go("dashboard")]]
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
            left_action_items: [["arrow-left", lambda x: app.go("dashboard")]]
            md_bg_color: app.bg_color

        MDRaisedButton:
            text: "+ Cargar combustible"
            size_hint_y: None
            height: dp(48)
            on_release: app.open_fuel_dialog()

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
            title: "Caja de hoy"
            left_action_items: [["arrow-left", lambda x: app.go("dashboard")]]
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
                    text: "Cobros por método"
                    font_style: "H5"
                    bold: True
                    size_hint_y: None
                    height: dp(44)

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
                    height: dp(190)

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
                        text: "Facturación total del día"
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
                    text: "Este resumen refleja cobros registrados en viajes. No incluye un fondo inicial de caja ni retiros manuales."
                    theme_text_color: "Custom"
                    text_color: app.muted_color
                    size_hint_y: None
                    text_size: self.width, None
                    height: self.texture_size[1] + dp(20)


<SettingsScreen>:
    name: "settings"
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.bg_color

        MDTopAppBar:
            title: "Configuración"
            left_action_items: [["arrow-left", lambda x: app.go("dashboard")]]
            md_bg_color: app.bg_color

        ScrollView:
            MDBoxLayout:
                orientation: "vertical"
                padding: dp(16)
                spacing: dp(12)
                adaptive_height: True

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

                MDRaisedButton:
                    text: "Guardar configuración"
                    on_release: app.save_settings()

                MDRaisedButton:
                    text: "Exportar datos a CSV"
                    md_bg_color: app.accent_color
                    on_release: app.export_database_to_csv()

                Widget:
                    size_hint_y: None
                    height: dp(40)
"""


class DashboardScreen(Screen):
    current_datetime_text = StringProperty("")
    session_status_text = StringProperty("Jornada cerrada")
    session_time_text = StringProperty("Abrí una jornada para empezar")
    session_action_text = StringProperty("ABRIR JORNADA")
    fuel_used_text = StringProperty("Consumido: 0,00 L · $0")
    fuel_reserve_text = StringProperty("A reponer: $0")
    revenue_text = StringProperty("$0")
    net_text = StringProperty("$0")
    km_text = StringProperty("0 km")
    trips_text = StringProperty("0")
    goal_text = StringProperty("$0 / $0")
    goal_percent = NumericProperty(0)
    daily_remaining_text = StringProperty("Faltan $0")
    weekly_goal_text = StringProperty("$0 / $0")
    weekly_goal_percent = NumericProperty(0)
    weekly_remaining_text = StringProperty("Faltan $0")


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


class SettingsScreen(Screen):
    pass


class ValidationError(ValueError):
    """Expected user input error. Safe to display to the user."""


class DriverControlApp(MDApp):
    bg_color = (0.965, 0.98, 0.99, 1)
    card_color = (1, 1, 1, 1)
    muted_color = (0.34, 0.40, 0.46, 1)
    accent_color = (0.00, 0.62, 0.86, 1)

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
        return Builder.load_string(KV)

    def on_start(self):
        try:
            self._clock_event = Clock.schedule_interval(self._tick_clock, 1)
            self._tick_clock(0)
            self.refresh_all()
            LOGGER.info("Application started successfully. Version=%s", APP_VERSION)
        except Exception:
            LOGGER.exception("Fatal error during application startup.")
            raise

    def on_stop(self):
        event = getattr(self, "_clock_event", None)
        if event is not None:
            event.cancel()
        if getattr(self, "conn", None) is not None:
            try:
                self.conn.commit()
                self.conn.close()
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

            self._ensure_column("trips", "cash_received", "REAL")
            self._ensure_column("trips", "change_given", "REAL")
            self._ensure_column("trips", "session_id", "INTEGER")
            self._ensure_column("expenses", "session_id", "INTEGER")
            self._ensure_column("expenses", "payment", "TEXT")
            self._ensure_column("fuel", "session_id", "INTEGER")
            self._ensure_column("fuel", "payment", "TEXT")

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

    def money(self, value: float) -> str:
        return f"${float(value):,.0f}".replace(",", ".")

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
        dashboard.current_datetime_text = now.strftime("%A %d/%m/%Y · %H:%M:%S").capitalize()
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
                        opened_at, opening_odometer, opening_cash, status
                    ) VALUES(?,?,?,'OPEN')
                    """,
                    (now, odometer, opening_cash),
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
        fields = [
            ("odometer", "Odómetro final", True),
            ("cash", "Efectivo contado al cierre", True),
        ]
        self.input_dialog("Cerrar jornada", fields, self.save_close_session)

    def _session_metrics(self, session_id: int, closing_odometer=None):
        session = self.conn.execute(
            "SELECT * FROM work_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if session is None:
            raise ValidationError("No se encontró la jornada.")

        trip = self.conn.execute(
            """
            SELECT COALESCE(SUM(amount),0) revenue,
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
                   COALESCE(SUM(CASE WHEN payment=? AND lower(category)!='combustible' THEN amount ELSE 0 END),0) cash_paid
            FROM expenses WHERE session_id=?
            """,
            (PAYMENT_CASH, session_id),
        ).fetchone()
        loaded = self.conn.execute(
            "SELECT COALESCE(SUM(amount),0) amount, COALESCE(SUM(liters),0) liters FROM fuel WHERE session_id=?",
            (session_id,),
        ).fetchone()

        end_odo = closing_odometer
        if end_odo is None:
            end_odo = session["closing_odometer"]
        if end_odo is not None:
            worked_km = max(float(end_odo) - float(session["opening_odometer"]), 0.0)
        else:
            worked_km = float(trip["trip_km"] or 0.0)

        consumption = self._setting_float("fuel_consumption", DEFAULT_FUEL_CONSUMPTION)
        fuel_price = self._setting_float("fuel_price", DEFAULT_FUEL_PRICE)
        fuel_liters = worked_km * consumption / 100.0
        fuel_cost = fuel_liters * fuel_price
        operating_expenses = float(exp["operating"] or 0.0)
        revenue = float(trip["revenue"] or 0.0)
        net = revenue - operating_expenses - fuel_cost
        cash_expected = (
            float(session["opening_cash"] or 0.0)
            + float(trip["cash_sales"] or 0.0)
            - float(exp["cash_paid"] or 0.0)
        )
        return {
            "revenue": revenue,
            "trips": int(trip["trips"] or 0),
            "worked_km": worked_km,
            "operating_expenses": operating_expenses,
            "fuel_liters": fuel_liters,
            "fuel_cost": fuel_cost,
            "fuel_loaded_amount": float(loaded["amount"] or 0.0),
            "fuel_loaded_liters": float(loaded["liters"] or 0.0),
            "net": net,
            "cash_expected": cash_expected,
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
                    """
                    UPDATE work_sessions
                    SET closed_at=?, closing_odometer=?, closing_cash=?,
                        cash_expected=?, cash_difference=?, status='CLOSED'
                    WHERE id=?
                    """,
                    (
                        now, closing_odometer, closing_cash,
                        metrics["cash_expected"], difference, session["id"],
                    ),
                )
            dialog.dismiss()
            self.refresh_all()
            sign = "+" if difference >= 0 else "-"
            self.show_message(
                "Jornada cerrada",
                "\n".join([
                    f"Facturación: {self.money(metrics['revenue'])}",
                    f"Km trabajados: {metrics['worked_km']:.1f} km",
                    f"Nafta consumida: {metrics['fuel_liters']:.2f} L",
                    f"A reponer en nafta: {self.money(metrics['fuel_cost'])}",
                    f"Nafta cargada: {metrics['fuel_loaded_liters']:.2f} L · {self.money(metrics['fuel_loaded_amount'])}",
                    f"Otros gastos: {self.money(metrics['operating_expenses'])}",
                    f"Ganancia neta: {self.money(metrics['net'])}",
                    f"Caja esperada: {self.money(metrics['cash_expected'])}",
                    f"Caja contada: {self.money(closing_cash)}",
                    f"Diferencia de caja: {sign}{self.money(abs(difference))}",
                ]),
            )
        except ValidationError as exc:
            self.show_message("No se puede cerrar", str(exc))
        except Exception:
            LOGGER.exception("Could not close work session")
            self.show_message("Error", "No se pudo cerrar la jornada.")

    def refresh_all(self):
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
            metrics = self._session_metrics(int(session["id"]))
            dashboard.session_status_text = "Jornada abierta"
            dashboard.session_action_text = "CERRAR JORNADA"
            dashboard.fuel_used_text = (
                f"Consumido: {metrics['fuel_liters']:.2f} L · {self.money(metrics['fuel_cost'])}"
            )
            dashboard.fuel_reserve_text = f"A reponer: {self.money(metrics['fuel_cost'])}"
        else:
            dashboard.session_status_text = "Jornada cerrada"
            dashboard.session_time_text = "Abrí una jornada para empezar"
            dashboard.session_action_text = "ABRIR JORNADA"
            dashboard.fuel_used_text = "Consumido: 0,00 L · $0"
            dashboard.fuel_reserve_text = "A reponer: $0"

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

        total_day = sum(totals.values())
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

    def fill_lists(self):
        self._fill_trip_list()
        self._fill_expense_list()
        self._fill_fuel_list()

    def _fill_trip_list(self):
        target = self.root.get_screen("trips").ids.trips_list
        target.clear_widgets()

        rows = self.conn.execute(
            """
            SELECT id, created_at, amount, payment, km, duration,
                   cash_received, change_given
            FROM trips
            ORDER BY id DESC
            LIMIT ?
            """,
            (MAX_HISTORY_ITEMS,),
        ).fetchall()

        for row in rows:
            cash_detail = ""
            if row["payment"] == PAYMENT_CASH and row["cash_received"] is not None:
                cash_detail = (
                    f" · Recibido {self.money(row['cash_received'])}"
                    f" · Vuelto {self.money(row['change_given'] or 0)}"
                )

            item = TwoLineListItem(
                text=f"{self.money(row['amount'])} · {row['payment']}",
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

        for row in rows:
            item = TwoLineListItem(
                text=f"{self.money(row['amount'])} · {row['liters']:.2f} L",
                secondary_text=(
                    f"{row['created_at']} · {row['odometer']:.0f} km · Tocá para eliminar"
                ),
            )
            item.bind(
                on_release=lambda _x, fuel_id=row["id"]: self.confirm_delete_fuel(fuel_id)
            )
            target.add_widget(item)

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
            if numeric:
                field.input_filter = "float"
            widgets[key] = field
            box.add_widget(field)

        dialog = MDDialog(
            title=title,
            type="custom",
            content_cls=box,
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
                        cash_received, change_given, session_id
                    )
                    VALUES(?,?,?,?,?,?,?,?)
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
                    ),
                )

            LOGGER.info(
                "Trip saved from visual entry: amount=%s payment=%s "
                "cash_received=%s change=%s km=%s duration=%s",
                amount,
                payment,
                cash_received,
                change_given,
                km,
                duration,
            )

            self.prepare_new_trip()
            self.root.current = "dashboard"
            self.refresh_all()

            if payment == PAYMENT_CASH:
                self.show_message(
                    "Cobro en efectivo",
                    f"Vuelto a entregar: {self.money(change_given or 0)}",
                )

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

    def export_database_to_csv(self):
        try:
            export_path = Path(self.user_data_dir) / "driver_control_export.csv"
            cursor = self.conn.cursor()
            cursor.execute("SELECT id, created_at, amount, payment, km, duration FROM trips ORDER BY id DESC")
            trips = cursor.fetchall()

            with open(export_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "Fecha", "Monto", "Pago", "Km", "Duración (min)"])
                for row in trips:
                    writer.writerow(list(row))

            self.show_message("Exportación exitosa", f"Los datos se guardaron en:\n{export_path.resolve()}")
            LOGGER.info("Database trips exported to CSV successfully.")
        except Exception:
            LOGGER.exception("Error exporting data to CSV.")
            self.show_message("Error", "No se pudo exportar el archivo CSV.")


if __name__ == "__main__":
    DriverControlApp().run()