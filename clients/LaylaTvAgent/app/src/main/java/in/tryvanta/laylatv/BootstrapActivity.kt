package `in`.tryvanta.laylatv

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.os.Build
import android.os.Bundle
import android.util.Log

/**
 * No-UI launcher. Does two things, then finishes:
 *  1. STEP-0 FEASIBILITY LOG — enumerates Camera2 so you can see, in logcat,
 *     whether the USB webcam is even visible to the native camera stack on THIS
 *     TV. This is the single most important unknown; check it before trusting
 *     the capture path.  `adb logcat -s LaylaCamProbe`
 *  2. starts the always-on foreground service.
 */
class BootstrapActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        probeCameras()
        val svc = Intent(this, LaylaAgentService::class.java)
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(svc) else startService(svc)
        finish()
    }

    private fun probeCameras() {
        val mgr = getSystemService(Context.CAMERA_SERVICE) as CameraManager
        try {
            val ids = mgr.cameraIdList
            Log.i("LaylaCamProbe", "Camera2 sees ${ids.size} camera(s): ${ids.joinToString()}")
            for (id in ids) {
                val c = mgr.getCameraCharacteristics(id)
                val facing = when (c.get(CameraCharacteristics.LENS_FACING)) {
                    CameraCharacteristics.LENS_FACING_EXTERNAL -> "EXTERNAL(USB)"
                    CameraCharacteristics.LENS_FACING_FRONT -> "FRONT"
                    CameraCharacteristics.LENS_FACING_BACK -> "BACK"
                    else -> "?"
                }
                Log.i("LaylaCamProbe", "  id=$id facing=$facing")
            }
            if (ids.isEmpty())
                Log.w("LaylaCamProbe", "NO cameras via Camera2 -> USB webcam not exposed to the native stack. " +
                        "Use the USB-Host + UVC path (libuvc / saki4510t UVCCamera) instead of Camera2.")
        } catch (e: Exception) {
            Log.e("LaylaCamProbe", "enumeration threw", e)
        }
    }
}
