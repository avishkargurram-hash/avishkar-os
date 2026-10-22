package in.tryvanta.layla;

import android.Manifest;
import android.os.Bundle;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import android.content.pm.PackageManager;
import com.getcapacitor.BridgeActivity;

/**
 * Layla's mobile shell: a Capacitor BridgeActivity pointed at the live
 * https://layla.tryvanta.in/app web frontend (see capacitor.config.json's
 * server.url) -- reuses 100% of the already-proven avatar/voice/wake-word
 * web experience instead of a native rewrite.
 *
 * Mic/camera permission requested up front at launch, matching the way the
 * web frontend expects the browser's getUserMedia prompt to just work.
 * Capacitor's own WebChromeClient forwards the WebView's getUserMedia
 * PermissionRequest and auto-grants it once the equivalent Android runtime
 * permission is already held -- this activity's only job is to make sure
 * that's true before the page ever asks.
 */
public class MainActivity extends BridgeActivity {
  private static final int PERMISSION_REQUEST_CODE = 1001;
  private static final String[] REQUIRED_PERMISSIONS = {
      Manifest.permission.RECORD_AUDIO,
      Manifest.permission.CAMERA,
  };

  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    requestMissingPermissions();
  }

  private void requestMissingPermissions() {
    java.util.ArrayList<String> missing = new java.util.ArrayList<>();
    for (String p : REQUIRED_PERMISSIONS) {
      if (ContextCompat.checkSelfPermission(this, p) != PackageManager.PERMISSION_GRANTED) {
        missing.add(p);
      }
    }
    if (!missing.isEmpty()) {
      ActivityCompat.requestPermissions(this, missing.toArray(new String[0]), PERMISSION_REQUEST_CODE);
    }
  }
}
