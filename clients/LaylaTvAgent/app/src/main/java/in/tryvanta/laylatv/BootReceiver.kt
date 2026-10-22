package `in`.tryvanta.laylatv

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build

/** Brings the agent back after boot, app update, or an onDestroy self-restart,
 *  and schedules the watchdog. Combined with START_STICKY + MQTT auto-reconnect
 *  this is the "always restarting" guarantee. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent?) {
        val svc = Intent(ctx, LaylaAgentService::class.java)
        if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(svc) else ctx.startService(svc)
        ServiceWatchdogWorker.schedule(ctx)
    }
}
