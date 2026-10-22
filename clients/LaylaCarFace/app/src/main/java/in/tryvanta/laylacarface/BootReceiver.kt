package `in`.tryvanta.laylacarface

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Launches Layla's face the moment the head unit finishes booting, so she is
 *  always on without anyone tapping the app. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED,
            Intent.ACTION_LOCKED_BOOT_COMPLETED,
            "android.intent.action.QUICKBOOT_POWERON" -> {
                val launch = Intent(context, MainActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                try {
                    context.startActivity(launch)
                } catch (_: Exception) {
                    // some head units restrict background activity starts; the
                    // HOME intent-filter then brings the app up on first unlock.
                }
            }
        }
    }
}
