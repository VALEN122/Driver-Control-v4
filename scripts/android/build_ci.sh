#!/usr/bin/env bash
set -euo pipefail

export DRIVER_CONTROL_SIGNING_KEYSTORE="$HOME/.android/debug.keystore"
CERT_FILE=$(mktemp)
keytool -exportcert -keystore "$DRIVER_CONTROL_SIGNING_KEYSTORE" \
  -storepass android -alias androiddebugkey -file "$CERT_FILE" >/dev/null
EXPECTED_CERT=$(sha256sum "$CERT_FILE" | awk '{print $1}')
rm -f "$CERT_FILE"
printf 'Firma de actualizacion esperada: %s\n' "$EXPECTED_CERT"

cp buildozer.spec buildozer.spec.ci-backup
trap 'mv -f buildozer.spec.ci-backup buildozer.spec' EXIT
VERSION=$(python3 - <<'PY'
import ast
import configparser
from pathlib import Path
tree = ast.parse(Path('main.py').read_text())
version = next(ast.literal_eval(node.value) for node in tree.body
               if isinstance(node, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'APP_VERSION' for t in node.targets))
config = configparser.ConfigParser(interpolation=None)
config.read('buildozer.spec')
assert config['app']['version'] == version, 'Version mismatch'
config.remove_option('app', 'android.extra_manifest_application_arguments')
# This option must live in [app], never after the [buildozer] section.
config['app']['p4a.source_dir'] = '/home/user/p4a-api36'
with open('buildozer.spec', 'w') as stream:
    config.write(stream)
print(version)
PY
)

docker run --rm \
  -v "$PWD":/home/user/hostcwd \
  -v "$PWD/_toolchain/python-for-android":/home/user/p4a-api36 \
  "$BUILDOZER_IMAGE" android debug
sudo chown -R "$(id -u):$(id -g)" .buildozer bin
MANIFEST_PATH=$(find .buildozer/android/platform -path '*/dists/drivercontrol/src/main/AndroidManifest.xml' -print -quit)
test -n "$MANIFEST_PATH"
DIST_DIR=$(dirname "$(dirname "$(dirname "$MANIFEST_PATH")")")
python3 scripts/android/complete_manifest.py "$MANIFEST_PATH"
JAVA_DST="$DIST_DIR/src/main/java/org/drivercontrol/drivercontrol"
mkdir -p "$JAVA_DST"
cp android_src/org/drivercontrol/drivercontrol/*.java "$JAVA_DST/"
# The Docker SDK path is not available to the final Gradle build on the runner.
# Point Gradle at the runner SDK and install the exact packages it requests.
BUILD_TOOLS_VERSION=$(python3 - "$DIST_DIR/build.gradle" <<'PY'
import re
import sys
from pathlib import Path
match = re.search(r"buildToolsVersion\s+['\"]([^'\"]+)['\"]", Path(sys.argv[1]).read_text())
if not match:
    raise SystemExit('No se pudo determinar la version de Android Build Tools')
print(match.group(1))
PY
)
SDKMANAGER="$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"
"$SDKMANAGER" 'platforms;android-36' "build-tools;$BUILD_TOOLS_VERSION"
printf 'sdk.dir=%s\n' "$ANDROID_HOME" > "$DIST_DIR/local.properties"
python3 - "$DIST_DIR/build.gradle" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
source = path.read_text()
marker = '// Driver Control: use the existing update certificate explicitly.'
if marker not in source:
    source += '''
// Driver Control: use the existing update certificate explicitly.
android {
    signingConfigs {
        debug {
            storeFile file(System.getenv("DRIVER_CONTROL_SIGNING_KEYSTORE"))
            storePassword "android"
            keyAlias "androiddebugkey"
            keyPassword "android"
        }
    }
    buildTypes {
        debug { signingConfig signingConfigs.debug }
    }
}
'''
    path.write_text(source)
PY
(cd "$DIST_DIR" && ./gradlew clean assembleDebug)
BUILT_APK=$(find "$DIST_DIR/build/outputs/apk/debug" -name '*.apk' -print -quit)
test -n "$BUILT_APK"
APK="bin/driver-control-${VERSION}-beta.apk"
cp "$BUILT_APK" "$APK"
unzip -t "$APK" >/dev/null
AAPT=$(find "$ANDROID_HOME/build-tools" -type f -name aapt -print | sort -V | tail -1)
APKSIGNER=$(find "$ANDROID_HOME/build-tools" -type f -name apksigner -print | sort -V | tail -1)
"$AAPT" dump badging "$APK" | tee "bin/${VERSION}-badging.txt"
grep -F "package: name='org.drivercontrol.drivercontrol'" "bin/${VERSION}-badging.txt"
grep -F "targetSdkVersion:'36'" "bin/${VERSION}-badging.txt"
grep -F "versionName='$VERSION'" "bin/${VERSION}-badging.txt"
"$APKSIGNER" verify --verbose --print-certs "$APK" | tee "bin/${VERSION}-signature.txt"
if ! grep -F "certificate SHA-256 digest: $EXPECTED_CERT" "bin/${VERSION}-signature.txt"; then
  echo '::error::El APK no coincide con la firma guardada. No se publicara esta compilacion.'
  exit 1
fi
APKANALYZER=$(command -v apkanalyzer || true)
if [ -z "$APKANALYZER" ]; then
  APKANALYZER=$(find "$ANDROID_HOME/cmdline-tools" -type f -name apkanalyzer -print | sort -V | tail -1)
fi
test -n "$APKANALYZER" && test -x "$APKANALYZER"
"$APKANALYZER" manifest print "$APK" > "bin/${VERSION}-manifest.txt"
test -s "bin/${VERSION}-manifest.txt"
grep -F 'org.drivercontrol.drivercontrol.fileprovider' "bin/${VERSION}-manifest.txt"
grep -F 'org.drivercontrol.drivercontrol.DriverOverlayService' "bin/${VERSION}-manifest.txt"
grep -F 'org.drivercontrol.drivercontrol.UberOfferAccessibilityService' "bin/${VERSION}-manifest.txt"
sha256sum "$APK" | tee "bin/${VERSION}-sha256.txt"
