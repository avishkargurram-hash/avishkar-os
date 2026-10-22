package app.tryvanta.laylanative

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import `in`.tryvanta.laylaphone.LaylaAccessibilityService
import `in`.tryvanta.laylaphone.LaylaNotificationListener
import `in`.tryvanta.laylaphone.PhoneAgentService
import `in`.tryvanta.laylawa.WaApi
import `in`.tryvanta.laylawa.WaListenerService
import org.json.JSONObject

/**
 * The bridge between the Almanac screens and Layla's two on-phone agents, which now live in this one app:
 *   - Layla Phone Agent (calls, SMS, contacts, app control, notifications) -- the old standalone setup checklist
 *   - Layla WhatsApp agent (auto-replies to people who are NOT in the owner's contacts)
 *
 * Nothing here decides anything. It only reports what the phone has granted, opens the right Android settings page,
 * starts/stops the agent service, and relays the WhatsApp kill switch to the server. Secrets (the WhatsApp device
 * token) stay in native code and never reach the web layer.
 */
@CapacitorPlugin(name = "LaylaNative")
class LaylaNativePlugin : Plugin() {

    private val ctx: Context get() = context

    private val runtimePermissions: List<String>
        get() = buildList {
            add(Manifest.permission.CALL_PHONE)
            add(Manifest.permission.READ_PHONE_STATE)
            add(Manifest.permission.SEND_SMS)
            add(Manifest.permission.READ_SMS)
            add(Manifest.permission.RECEIVE_SMS)
            add(Manifest.permission.READ_CONTACTS)
            add(Manifest.permission.READ_CALL_LOG)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) add(Manifest.permission.ANSWER_PHONE_CALLS)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) add(Manifest.permission.POST_NOTIFICATIONS)
        }

    /** True when Android lists this component under "Notification access" and the owner switched it on. */
    private fun listenerEnabled(cls: Class<*>): Boolean {
        val flat = Settings.Secure.getString(ctx.contentResolver, "enabled_notification_listeners") ?: return false
        val me = ComponentName(ctx, cls).flattenToString()
        return flat.split(":").any { it == me }
    }

    @PluginMethod
    fun status(call: PluginCall) {
        val missing = runtimePermissions.filter {
            ContextCompat.checkSelfPermission(ctx, it) != PackageManager.PERMISSION_GRANTED
        }
        val pm = ctx.getSystemService(Context.POWER_SERVICE) as PowerManager
        val phone = JSObject()
            .put("permissionsMissing", missing.size)
            .put("accessibility", LaylaAccessibilityService.isReady())
            .put("notificationReader", LaylaNotificationListener.isReady())
            .put("batteryUnrestricted", pm.isIgnoringBatteryOptimizations(ctx.packageName))
            .put("overlay", Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(ctx))
        val wa = JSObject()
            .put("listener", listenerEnabled(WaListenerService::class.java))
            .put("serverConfigured", waConfigured())
        call.resolve(JSObject().put("phone", phone).put("wa", wa).put("sdk", Build.VERSION.SDK_INT))
    }

    private fun waConfigured(): Boolean = `in`.tryvanta.laylawa.BuildConfig.WA_BASE.isNotBlank() &&
        `in`.tryvanta.laylawa.BuildConfig.WA_TOKEN.isNotBlank()

    @PluginMethod
    fun startPhone(call: PluginCall) {
        try {
            val i = Intent(ctx, PhoneAgentService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) ctx.startForegroundService(i) else ctx.startService(i)
            call.resolve(JSObject().put("started", true))
        } catch (e: Exception) {
            call.reject("Could not start the phone agent: " + (e.message ?: e.javaClass.simpleName))
        }
    }

    @PluginMethod
    fun stopPhone(call: PluginCall) {
        try {
            ctx.stopService(Intent(ctx, PhoneAgentService::class.java))
            call.resolve(JSObject().put("stopped", true))
        } catch (e: Exception) {
            call.reject("Could not stop the phone agent: " + (e.message ?: e.javaClass.simpleName))
        }
    }

    @PluginMethod
    fun askPermissions(call: PluginCall) {
        val act = activity ?: return call.reject("No active screen")
        ActivityCompat.requestPermissions(act, runtimePermissions.toTypedArray(), 4242)
        call.resolve()
    }

    /** target: notification | accessibility | battery | overlay | app. Falls back to App Info on odd ROMs. */
    @PluginMethod
    fun openSettings(call: PluginCall) {
        val pkg = Uri.parse("package:" + ctx.packageName)
        val intent = when (call.getString("target")) {
            "notification" -> Intent("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS")
            "accessibility" -> Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
            "battery" -> Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).setData(pkg)
            "overlay" -> Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, pkg)
            else -> Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).setData(pkg)
        }.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            ctx.startActivity(intent)
        } catch (_: Exception) {
            try {
                ctx.startActivity(
                    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).setData(pkg).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                )
            } catch (e: Exception) {
                return call.reject("Could not open settings: " + (e.message ?: ""))
            }
        }
        call.resolve()
    }

    // ---- WhatsApp auto-reply: status + kill switch (server is the source of truth) ---------------------------------
    @PluginMethod
    fun waStatus(call: PluginCall) = waCall(call) { WaApi.get("/status") }

    @PluginMethod
    fun waPower(call: PluginCall) {
        val on = call.getBoolean("on") ?: return call.reject("on must be true or false")
        waCall(call) { WaApi.post("/power", JSONObject().put("on", on)) }
    }

    private fun waCall(call: PluginCall, block: () -> JSONObject) {
        if (!waConfigured()) return call.reject("This build has no WhatsApp server settings (wa.properties missing)")
        Thread {
            try {
                call.resolve(JSObject(block().toString()))
            } catch (e: Exception) {
                call.reject("WhatsApp server: " + (e.message ?: e.javaClass.simpleName))
            }
        }.start()
    }
}
