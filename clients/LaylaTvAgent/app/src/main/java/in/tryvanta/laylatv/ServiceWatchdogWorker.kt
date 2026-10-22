package `in`.tryvanta.laylatv

import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.work.*
import java.util.concurrent.TimeUnit

/**
 * The "MqttWorker" belt-and-braces. The MQTT client itself lives in the always-
 * on foreground service (isAutomaticReconnect=true); this periodic worker is
 * the watchdog that re-launches that service if Google TV ever killed it
 * outright. WorkManager's floor is 15 min, so this is a safety net, not the
 * primary keep-alive (START_STICKY + the FGS are).
 */
class ServiceWatchdogWorker(c: Context, p: WorkerParameters) : Worker(c, p) {
    override fun doWork(): Result {
        val svc = Intent(applicationContext, LaylaAgentService::class.java)
        if (Build.VERSION.SDK_INT >= 26) applicationContext.startForegroundService(svc)
        else applicationContext.startService(svc)
        return Result.success()
    }
    companion object {
        fun schedule(ctx: Context) {
            val req = PeriodicWorkRequestBuilder<ServiceWatchdogWorker>(15, TimeUnit.MINUTES)
                .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
                .build()
            WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
                "layla-watchdog", ExistingPeriodicWorkPolicy.KEEP, req)
        }
    }
}
