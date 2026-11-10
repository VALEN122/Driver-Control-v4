import sqlite3
import unittest
from test_finance_model import _load_main_without_kivy

class Completion630Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _load_main_without_kivy()

    def setUp(self):
        self.app = object.__new__(self.main.DriverControlApp)
        self.app.conn = sqlite3.connect(':memory:')
        self.app.conn.row_factory = sqlite3.Row
        self.app._create_or_migrate_db()
        for key, value in {'fuel_consumption':8, 'fuel_price':1000,
                'assistant_min_hourly':15000, 'assistant_min_per_km':300,
                'assistant_max_pickup_km':3, 'maintenance_per_km':100}.items():
            self.app.conn.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key,str(value)))
        self.addCleanup(self.app.conn.close)

    def test_below_hourly_minimum_cannot_be_green(self):
        result = self.app._assistant_result(6000, 5, 1, 55, 9, 'Buena')
        self.assertEqual('DUDOSO', result['recommendation'])

    def test_both_minimums_missed_is_red(self):
        result = self.app._assistant_result(2000, 5, 1, 55, 9, 'Normal')
        self.assertEqual('NO CONVIENE', result['recommendation'])

    def test_maintenance_reserve_is_separate_from_fuel_and_used_for_verdict(self):
        result = self.app._assistant_result(6000, 2, 1, 18, 9, 'Normal')
        self.assertEqual(800, result['fuel_cost'])
        self.assertEqual(5200, result['net_est'])
        self.assertEqual(1000, result['maintenance_cost'])
        self.assertEqual(4200, result['operating_profit'])
        self.assertEqual(12600, result['hourly_est'])
        self.assertEqual('DUDOSO', result['recommendation'])

    def test_nonfinite_and_negative_inputs_rejected(self):
        for args in [(float('nan'),1,1,10,5), (5000,-1,1,10,5), (5000,1,1,0,5)]:
            with self.subTest(args=args), self.assertRaises(self.main.ValidationError):
                self.app._assistant_result(*args, 'Normal')

    def test_session_goal_does_not_count_other_sessions_or_offer_assessments(self):
        self.app.conn.execute("INSERT OR REPLACE INTO settings VALUES ('daily_goal','50000')")
        for sid in (1,2):
            self.app.conn.execute("INSERT INTO work_sessions(id,opened_at,opening_odometer,current_odometer,opening_cash) VALUES (?, '2026-11-09 23:00:00',1000,1010,0)",(sid,))
            self.app.conn.execute("INSERT INTO trips(created_at,amount,payment,session_id) VALUES ('2026-11-10 01:00:00',20000,'Efectivo',?)",(sid,))
        progress = self.app._session_goal_progress(1)
        self.assertEqual(20000, progress['income'])
        self.assertEqual(30000, progress['remaining'])
        self.assertEqual(40, progress['percent'])

    def test_invalid_saved_setting_falls_back_to_default(self):
        for value in ('NaN','inf','-100'):
            self.app.conn.execute("INSERT OR REPLACE INTO settings VALUES ('maintenance_per_km',?)",(value,))
            self.assertEqual(0,self.app._setting_float('maintenance_per_km',0))

    def test_pause_reason_does_not_claim_profitable_offer_is_recommended(self):
        self.app._sync_android_wellness_state(0,True)
        result=self.app._assistant_result(10000,2,1,18,9,'Normal')
        self.assertIn('pausa',self.app._decisive_trip_reason(result).lower())
