package org.drivercontrol.drivercontrol;

import android.app.Activity;
import android.graphics.Insets;
import android.os.Build;
import android.util.Log;
import android.view.View;
import android.view.WindowInsets;
import androidx.core.view.WindowCompat;

/** Keep Kivy controls outside system bars when Android enforces edge-to-edge. */
public final class DriverWindowInsets {
    private DriverWindowInsets() {}

    public static void install(Activity activity) {
        if (activity == null || Build.VERSION.SDK_INT < 35) return;
        activity.runOnUiThread(() -> {
            try {
                View content = activity.findViewById(android.R.id.content);
                if (content == null) return;
                WindowCompat.setDecorFitsSystemWindows(activity.getWindow(), false);
                content.setOnApplyWindowInsetsListener((view, windowInsets) -> {
                    Insets bars = windowInsets.getInsets(
                            WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                    view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                    return windowInsets;
                });
                content.requestApplyInsets();
            } catch (RuntimeException error) {
                Log.e("DriverControlInsets", "Could not apply system bar insets", error);
            }
        });
    }
}
