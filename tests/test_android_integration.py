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
        self.assertIn("androidx.core:core:1.13.1", spec)


if __name__ == "__main__":
    unittest.main()
