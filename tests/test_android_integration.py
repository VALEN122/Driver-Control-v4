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

    def test_excel_share_uses_native_android_bridge(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        bridge = (
            ROOT
            / "android_src/org/drivercontrol/drivercontrol/DriverFileShare.java"
        ).read_text(encoding="utf-8")

        self.assertIn("DriverFileShare.shareFile", source)
        self.assertIn("activity.getCacheDir()", bridge)
        self.assertIn("FileProvider.getUriForFile", bridge)
        self.assertIn("FLAG_GRANT_READ_URI_PERMISSION", bridge)
        self.assertIn("runOnUiThread", bridge)

    def test_file_provider_exposes_controlled_export_paths(self):
        manifest = (
            ROOT / "android_manifest/application_services.xml"
        ).read_text(encoding="utf-8")
        paths = (
            ROOT / "android_res/xml/driver_control_file_paths.xml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'android:authorities="org.drivercontrol.drivercontrol.fileprovider"',
            manifest,
        )
        self.assertIn("<cache-path", paths)
        self.assertIn('path="driver_control_exports/"', paths)

    def test_file_provider_dependency_is_packaged(self):
        spec = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
        self.assertIn("androidx.core:core:1.9.0", spec)

    def test_new_financial_home_is_packaged_and_versioned(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        spec = (ROOT / "buildozer.spec").read_text(encoding="utf-8")

        self.assertIn('APP_VERSION = "6.1.2"', source)
        self.assertIn('text: "DINERO REAL QUE TE QUEDÓ · "', source)
        self.assertIn(
            'dashboard.session_action_text = "FINALIZAR Y VER MI GANANCIA"',
            source,
        )
        self.assertIn("def create_database_backup", source)
        self.assertIn("version = 6.1.2", spec)


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
        self.assertIn("android.presplash_color = #041F3E", spec)
        self.assertGreater(icon.stat().st_size, 100_000)
        self.assertGreater(splash.stat().st_size, 100_000)


if __name__ == "__main__":
    unittest.main()
