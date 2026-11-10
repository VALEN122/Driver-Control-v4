"""Apply the reviewed Android components once, preserving unrelated attributes."""
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

ANDROID = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ANDROID)


def complete_manifest(path, components):
    tree = ET.parse(path)
    app = tree.getroot().find("application")
    if app is None:
        raise ValueError("No application in generated manifest")
    # SDL2 still handles the legacy Android back event.
    app.set(f"{{{ANDROID}}}enableOnBackInvokedCallback", "false")
    additions = ET.fromstring(f'<root xmlns:android="{ANDROID}">' + Path(components).read_text() + '</root>')
    for element in additions:
        name = element.get(f"{{{ANDROID}}}name")
        for old in list(app):
            if old.tag == element.tag and old.get(f"{{{ANDROID}}}name") == name:
                app.remove(old)
        app.append(element)
    tree.write(path, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    complete_manifest(sys.argv[1], "android_manifest/application_services.xml")
