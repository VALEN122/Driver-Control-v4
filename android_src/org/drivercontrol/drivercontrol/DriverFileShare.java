package org.drivercontrol.drivercontrol;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.util.Log;

import androidx.core.content.FileProvider;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;

/**
 * Puente nativo para compartir exportaciones sin exponer rutas privadas.
 *
 * <p>Los archivos se copian primero a una carpeta controlada de cache y luego
 * se publican como un content:// URI temporal mediante FileProvider. Esto evita
 * incompatibilidades de PyJNIus con las sobrecargas de Intent/Parcelable y
 * funciona con Drive, Archivos, correo y mensajeria.</p>
 */
public final class DriverFileShare {
    private static final String TAG = "DriverControlShare";
    private static final String EXPORT_DIRECTORY = "driver_control_exports";

    private DriverFileShare() {
    }

    public static String shareFile(
            final Activity activity,
            final String sourcePath,
            final String mimeType,
            final String chooserTitle,
            final String subject
    ) {
        try {
            if (activity == null) {
                return "actividad Android no disponible";
            }

            File source = new File(sourcePath);
            if (!source.isFile() || source.length() <= 0) {
                return "archivo inexistente o vacio";
            }

            File exportDirectory = new File(activity.getCacheDir(), EXPORT_DIRECTORY);
            if (!exportDirectory.exists() && !exportDirectory.mkdirs()) {
                return "no se pudo preparar la carpeta temporal";
            }

            clearOldExports(exportDirectory, source.getName());
            File sharedFile = new File(exportDirectory, source.getName());
            copyFile(source, sharedFile);

            final Uri contentUri = FileProvider.getUriForFile(
                    activity,
                    activity.getPackageName() + ".fileprovider",
                    sharedFile
            );

            final Intent sendIntent = new Intent(Intent.ACTION_SEND);
            sendIntent.setType(mimeType);
            sendIntent.putExtra(Intent.EXTRA_STREAM, contentUri);
            sendIntent.putExtra(Intent.EXTRA_SUBJECT, subject);
            sendIntent.setClipData(ClipData.newRawUri(subject, contentUri));
            sendIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);

            final Intent chooser = Intent.createChooser(sendIntent, chooserTitle);
            chooser.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            activity.runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    try {
                        activity.startActivity(chooser);
                    } catch (RuntimeException error) {
                        Log.e(TAG, "No se pudo abrir el selector para compartir", error);
                    }
                }
            });
            return "";
        } catch (Exception error) {
            Log.e(TAG, "No se pudo compartir el archivo", error);
            String message = error.getMessage();
            return error.getClass().getSimpleName()
                    + (message == null || message.trim().isEmpty() ? "" : ": " + message);
        }
    }

    private static void copyFile(File source, File destination) throws IOException {
        byte[] buffer = new byte[64 * 1024];
        try (
                FileInputStream input = new FileInputStream(source);
                FileOutputStream output = new FileOutputStream(destination, false)
        ) {
            int read;
            while ((read = input.read(buffer)) != -1) {
                output.write(buffer, 0, read);
            }
            output.flush();
        }
    }

    private static void clearOldExports(File directory, String keepName) {
        File[] files = directory.listFiles();
        if (files == null) {
            return;
        }
        for (File file : files) {
            if (!file.getName().equals(keepName) && file.isFile()) {
                // Una falla al limpiar cache no debe bloquear una nueva exportacion.
                if (!file.delete()) {
                    Log.w(TAG, "No se pudo limpiar exportacion anterior: " + file.getName());
                }
            }
        }
    }
}
