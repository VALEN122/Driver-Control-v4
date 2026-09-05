[app]
title = Driver Control
package.name = drivercontrol
package.domain = org.drivercontrol
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,xml,java,md
version = 5.1.0
requirements = python3,kivy==2.3.0,kivymd==1.2.0,hostpython3,android,pyjnius
android.gradle_dependencies = com.google.mlkit:text-recognition:16.0.1
android.permissions = FOREGROUND_SERVICE,FOREGROUND_SERVICE_MEDIA_PROJECTION,POST_NOTIFICATIONS,SYSTEM_ALERT_WINDOW
orientation = portrait
fullscreen = 0
android.api = 33
android.minapi = 26
android.ndk = 25b
android.ndk_api = 26
android.archs = arm64-v8a
android.accept_sdk_license = True
p4a.branch = v2024.01.21

# Driver Control 4.5 - integración Android del asistente sobre Uber
android.add_src = android_src
android.add_resources = android_res
android.extra_manifest_application_arguments = android_manifest/application_services.xml

[buildozer]
log_level = 2
warn_on_root = 1
