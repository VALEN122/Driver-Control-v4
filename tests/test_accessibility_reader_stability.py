import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AccessibilityReaderStabilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
        cls.manifest = (
            ROOT / "android_manifest/application_services.xml"
        ).read_text(encoding="utf-8")
        cls.reader = (
            ROOT
            / "android_src/org/drivercontrol/drivercontrol/UberOfferAccessibilityService.java"
        ).read_text(encoding="utf-8")
        cls.overlay = (
            ROOT
            / "android_src/org/drivercontrol/drivercontrol/DriverOverlayService.java"
        ).read_text(encoding="utf-8")
        cls.main = (ROOT / "main.py").read_text(encoding="utf-8")
        cls.workflow = (
            ROOT / ".github/workflows/android.yml"
        ).read_text(encoding="utf-8") + (ROOT / "scripts/android/build_ci.sh").read_text(encoding="utf-8")

    def test_android_14_foreground_service_contract_is_complete(self):
        self.assertIn("FOREGROUND_SERVICE_SPECIAL_USE", self.spec)
        self.assertIn('android:foregroundServiceType="specialUse"', self.manifest)
        self.assertIn("android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE", self.manifest)
        self.assertIn("FOREGROUND_SERVICE_TYPE_SPECIAL_USE", self.overlay)

    def test_overlay_start_failure_does_not_crash_reader_process(self):
        self.assertIn('putString("overlay_start_error", reason)', self.overlay)
        self.assertIn("return START_NOT_STICKY;", self.overlay)
        self.assertIn('Log.e(TAG, "Could not enter foreground mode:', self.overlay)

    def test_mlkit_startup_is_guarded_and_retriable(self):
        self.assertIn("ensureCoordinator()", self.reader)
        self.assertIn("COORDINATOR_RETRY_MS", self.reader)
        self.assertIn('persistServiceState("DEGRADED"', self.reader)
        self.assertIn("catch (Throwable error)", self.reader)

    def test_reader_status_does_not_depend_on_overlay_permission(self):
        status_write = self.reader.index('putString("last_reader_status", message)')
        overlay_gate = self.reader.index("if (!Settings.canDrawOverlays(this)) return;")
        self.assertLess(status_write, overlay_gate)

    def test_sideloaded_apk_has_restricted_settings_guidance(self):
        self.assertIn("Permitir ajustes restringidos", self.main)
        self.assertIn("Settings.ACTION_APPLICATION_DETAILS_SETTINGS", self.main)
        self.assertIn('MDFlatButton(text="PREPARAR APK"', self.main)
        self.assertIn('MDFlatButton(text="YA PREPARÉ"', self.main)

    def test_manual_decision_engine_remains_available(self):
        self.assertIn("def _assistant_result(", self.main)
        self.assertIn("def analyze_trip_offer(", self.main)

    def test_test_apk_uses_the_existing_update_signature(self):
        self.assertIn("DRIVER_CONTROL_DEBUG_KEYSTORE_B64", self.workflow)
        # The final Gradle build runs on the host, after the Docker build.
        # Its signing configuration and the certificate check must use the
        # same restored keystore; a Docker volume alone cannot guarantee that.
        self.assertIn(
            'export DRIVER_CONTROL_SIGNING_KEYSTORE="$HOME/.android/debug.keystore"',
            self.workflow,
        )
        self.assertIn('storeFile file(System.getenv("DRIVER_CONTROL_SIGNING_KEYSTORE"))', self.workflow)
        self.assertIn('debug { signingConfig signingConfigs.debug }', self.workflow)
        self.assertIn('keytool -exportcert -keystore "$DRIVER_CONTROL_SIGNING_KEYSTORE"', self.workflow)
        self.assertIn('if ! grep -F "certificate SHA-256 digest: $EXPECTED_CERT"', self.workflow)
        self.assertIn('No se publicara esta compilacion.', self.workflow)
        self.assertIn("versionName='$VERSION'", self.workflow)


if __name__ == "__main__":
    unittest.main()
