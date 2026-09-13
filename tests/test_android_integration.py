import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AndroidIntegrationSourceTest(unittest.TestCase):
    def test_change_bubble_can_be_dragged_and_keeps_its_position(self):
        source = (
            ROOT
            / "android_src/org/drivercontrol/drivercontrol/DriverOverlayService.java"
        ).read_text(encoding="utf-8")

        self.assertIn("MotionEvent.ACTION_MOVE", source)
        self.assertIn("windowManager.updateViewLayout(view, params)", source)
        self.assertIn('putInt("bubble_x"', source)
        self.assertIn('putInt("bubble_y"', source)
        self.assertIn("view.performClick()", source)

    def test_excel_share_grants_android_uri_access(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertIn('cast("android.os.Parcelable", uri)', source)
        self.assertIn("intent.setClipData", source)
        self.assertIn("FLAG_GRANT_READ_URI_PERMISSION", source)

    def test_file_provider_dependency_is_packaged(self):
        spec = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
        self.assertIn("androidx.core:core:1.9.0", spec)

    def test_new_financial_home_is_packaged_and_versioned(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        spec = (ROOT / "buildozer.spec").read_text(encoding="utf-8")

        self.assertIn('APP_VERSION = "6.1.1"', source)
        self.assertIn('text: "DINERO REAL QUE TE QUEDÓ · "', source)
        self.assertIn(
            'dashboard.session_action_text = "FINALIZAR Y VER MI GANANCIA"',
            source,
        )
        self.assertIn("def create_database_backup", source)
        self.assertIn("version = 6.1.1", spec)


    def test_driver_control_brand_replaces_default_kivy_startup(self):
        spec = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
        icon = ROOT / "assets/branding/driver_control_icon.png"
        splash = ROOT / "assets/branding/driver_control_splash.png"

        self.assertIn(
            "icon.filename = %(source.dir)s/assets/branding/driver_control_icon.png",
            spec,
        )
        self.assertIn(
            "presplash.filename = %(source.dir)s/assets/branding/driver_control_splash.png",
            spec,
        )
        self.assertGreater(icon.stat().st_size, 100_000)
        self.assertGreater(splash.stat().st_size, 100_000)


if __name__ == "__main__":
    unittest.main()
