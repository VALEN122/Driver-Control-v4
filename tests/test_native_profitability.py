"""Execute the production Java engine and compare independent financial fixtures."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import test_completion_630

ROOT = Path(__file__).resolve().parents[1]

class NativeProfitabilityTest(test_completion_630.Completion630Test):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.build = Path(cls.temp.name)
        (cls.build/'Context.java').write_text('''package android.content;
public abstract class Context {
 public static final int MODE_PRIVATE=0;
 public abstract SharedPreferences getSharedPreferences(String n,int m);
}''')
        (cls.build/'SharedPreferences.java').write_text('''package android.content;
public interface SharedPreferences {
 float getFloat(String n,float d); int getInt(String n,int d); boolean getBoolean(String n,boolean d);
}''')
        (cls.build/'Harness.java').write_text('''
import org.drivercontrol.drivercontrol.TripProfitabilityAnalyzer;
public class Harness {
 public static void main(String[] a) {
  try {
   var r=TripProfitabilityAnalyzer.analyze(Double.parseDouble(a[0]),2,1,18,9,
          8,1000,15000,300,3,Double.parseDouble(a[1]),Integer.parseInt(a[2]),Boolean.parseBoolean(a[3]));
   System.out.print("["+r.fuelCost+","+r.maintenanceCost+","+r.netProfit+","+
       r.operatingProfit+","+r.perHour+","+r.perKm+",\\\""+r.verdict+"\\\"]");
  } catch (IllegalArgumentException e) {System.out.print("null");}
 }
}''')
        subprocess.run(['java','-m','jdk.compiler/com.sun.tools.javac.Main','-d',str(cls.build),
            str(cls.build/'Context.java'),str(cls.build/'SharedPreferences.java'),
            str(ROOT/'android_src/org/drivercontrol/drivercontrol/TripProfitabilityAnalyzer.java'),
            str(cls.build/'Harness.java')],check=True,capture_output=True,text=True)

    def native(self,fare,reserve=100,risk=0,paused=False):
        r=subprocess.run(['java','-cp',str(self.build),'Harness',str(fare),str(reserve),str(risk),str(paused).lower()],
                         check=True,capture_output=True,text=True)
        return json.loads(r.stdout)

    def test_native_financial_fixture(self):
        self.assertEqual([800,1000,5200,4200,12600,420,'REVIEW'],self.native(6000))

    def test_native_and_manual_agree_on_red_yellow_green(self):
        for fare,want in ((2000,'NO CONVIENE'),(6000,'DUDOSO'),(10000,'CONVIENE')):
            with self.subTest(fare=fare):
                native=self.native(fare)
                manual=self.app._assistant_result(fare,2,1,18,9,'Normal')
                self.assertEqual(want,manual['recommendation'])
                self.assertEqual(want,{'ACCEPT':'CONVIENE','REVIEW':'DUDOSO','DISCARD':'NO CONVIENE'}[native[-1]])
                self.assertEqual(native[4],manual['hourly_est'])
                self.assertEqual(native[5],manual['per_km_est'])

    def test_invalid_values_and_reserve_cannot_produce_green(self):
        self.assertIsNone(self.native('NaN'))
        self.assertIsNone(self.native(10000,-1))
        self.assertEqual('DISCARD',self.native(6000,1000)[-1])

    def test_pause_and_fatigue_override_profitable_offer(self):
        for risk,paused,want in ((0,True,'DISCARD'),(1,False,'REVIEW'),(2,False,'DISCARD')):
            with self.subTest(risk=risk,paused=paused):
                self.assertEqual(want,self.native(10000,100,risk,paused)[-1])
                self.app._sync_android_wellness_state(risk,paused)
                result=self.app._assistant_result(10000,2,1,18,9,'Normal')
                self.assertEqual({'DISCARD':'NO CONVIENE','REVIEW':'DUDOSO'}[want],result['recommendation'])
