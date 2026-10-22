package `in`.tryvanta.laylaphone

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.BatteryManager
import android.os.Build
import android.provider.CallLog
import android.provider.ContactsContract
import android.provider.MediaStore
import android.provider.Settings
import android.provider.Telephony
import android.telecom.TelecomManager
import android.telephony.SmsManager
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject

/**
 * The Tier-2 device actions: telephony, messaging, contacts and apps.
 *
 * Every function here is a plain mechanism that assumes the decision has
 * already been made. The approval gate lives in PhoneAgentService -- keeping
 * "can this happen" and "how does it happen" in separate files is what makes
 * the gate auditable at a glance instead of scattered through the actions.
 */
object PhoneActions {

    data class Recipient(val name: String?, val number: String) {
        fun display(): String = if (name.isNullOrBlank()) number else "$name ($number)"
    }

    fun has(ctx: Context, perm: String): Boolean =
        ContextCompat.checkSelfPermission(ctx, perm) == PackageManager.PERMISSION_GRANTED

    // -- contacts ---------------------------------------------------------

    /**
     * Turns whatever Layla passed ("Mom", "+919876543210", "98765 43210")
     * into a real number plus the contact name it belongs to, so the
     * confirm popup can show the owner a human-readable "who" rather than
     * a bare string he has to parse himself.
     */
    fun resolveRecipient(ctx: Context, raw: String): Recipient? {
        val trimmed = raw.trim()
        if (trimmed.isEmpty()) return null

        val digitsOnly = trimmed.count { it.isDigit() }
        val looksNumeric = digitsOnly >= 5 &&
            trimmed.all { it.isDigit() || it in " -()+." }

        if (looksNumeric) {
            val number = trimmed.filter { it.isDigit() || it == '+' }
            return Recipient(lookupNameFor(ctx, number), number)
        }

        val match = searchContactsRaw(ctx, trimmed).firstOrNull() ?: return null
        return Recipient(match.first, match.second)
    }

    private fun lookupNameFor(ctx: Context, number: String): String? {
        if (!has(ctx, Manifest.permission.READ_CONTACTS)) return null
        return try {
            val uri = Uri.withAppendedPath(
                ContactsContract.PhoneLookup.CONTENT_FILTER_URI,
                Uri.encode(number),
            )
            ctx.contentResolver.query(
                uri,
                arrayOf(ContactsContract.PhoneLookup.DISPLAY_NAME),
                null, null, null,
            )?.use { c -> if (c.moveToFirst()) c.getString(0) else null }
        } catch (_: Exception) {
            null
        }
    }

    private fun searchContactsRaw(ctx: Context, query: String): List<Pair<String, String>> {
        if (!has(ctx, Manifest.permission.READ_CONTACTS)) return emptyList()
        val uri = Uri.withAppendedPath(
            ContactsContract.CommonDataKinds.Phone.CONTENT_FILTER_URI,
            Uri.encode(query),
        )
        val out = LinkedHashMap<String, String>()
        try {
            ctx.contentResolver.query(
                uri,
                arrayOf(
                    ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
                    ContactsContract.CommonDataKinds.Phone.NUMBER,
                ),
                null, null, null,
            )?.use { c ->
                while (c.moveToNext() && out.size < 25) {
                    val name = c.getString(0) ?: continue
                    val num = c.getString(1)?.replace(" ", "") ?: continue
                    out.putIfAbsent("$name|$num", "")
                    out["$name|$num"] = num
                }
            }
        } catch (_: Exception) {
            return emptyList()
        }
        return out.keys.map { k -> k.substringBefore('|') to k.substringAfter('|') }
    }

    fun searchContacts(ctx: Context, query: String): JSONArray {
        val arr = JSONArray()
        searchContactsRaw(ctx, query).forEach { (name, num) ->
            arr.put(JSONObject().put("name", name).put("number", num))
        }
        return arr
    }

    // -- calls ------------------------------------------------------------

    fun placeCall(ctx: Context, number: String): String {
        if (!has(ctx, Manifest.permission.CALL_PHONE)) {
            return "ERR:the Call permission isn't granted — open Layla Phone Agent and tap Grant permissions"
        }
        return try {
            val intent = Intent(Intent.ACTION_CALL, Uri.parse("tel:" + Uri.encode(number)))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(intent)
            "OK:calling $number"
        } catch (e: Exception) {
            "ERR:could not start the call (${e.message})"
        }
    }

    fun answerCall(ctx: Context): String {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            return "ERR:answering calls needs Android 8 or newer"
        }
        if (!has(ctx, Manifest.permission.ANSWER_PHONE_CALLS)) {
            return "ERR:the Answer-calls permission isn't granted"
        }
        return try {
            val tm = ctx.getSystemService(Context.TELECOM_SERVICE) as TelecomManager
            tm.acceptRingingCall()
            "OK:answered"
        } catch (e: Exception) {
            "ERR:could not answer (${e.message})"
        }
    }

    fun endCall(ctx: Context): String {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
            return "ERR:hanging up needs Android 9 or newer"
        }
        if (!has(ctx, Manifest.permission.ANSWER_PHONE_CALLS)) {
            return "ERR:the Answer-calls permission isn't granted"
        }
        return try {
            val tm = ctx.getSystemService(Context.TELECOM_SERVICE) as TelecomManager
            @Suppress("DEPRECATION")
            if (tm.endCall()) "OK:call ended" else "ERR:there was no call to end"
        } catch (e: Exception) {
            "ERR:could not end the call (${e.message})"
        }
    }

    fun callLog(ctx: Context, limit: Int): JSONArray {
        val arr = JSONArray()
        if (!has(ctx, Manifest.permission.READ_CALL_LOG)) return arr
        try {
            ctx.contentResolver.query(
                CallLog.Calls.CONTENT_URI,
                arrayOf(
                    CallLog.Calls.NUMBER,
                    CallLog.Calls.CACHED_NAME,
                    CallLog.Calls.TYPE,
                    CallLog.Calls.DATE,
                    CallLog.Calls.DURATION,
                ),
                null, null,
                "${CallLog.Calls.DATE} DESC",
            )?.use { c ->
                var n = 0
                while (c.moveToNext() && n < limit.coerceIn(1, 50)) {
                    val kind = when (c.getInt(2)) {
                        CallLog.Calls.INCOMING_TYPE -> "incoming"
                        CallLog.Calls.OUTGOING_TYPE -> "outgoing"
                        CallLog.Calls.MISSED_TYPE -> "missed"
                        CallLog.Calls.REJECTED_TYPE -> "rejected"
                        else -> "other"
                    }
                    arr.put(
                        JSONObject()
                            .put("number", c.getString(0) ?: "")
                            .put("name", c.getString(1) ?: "")
                            .put("type", kind)
                            .put("at", c.getLong(3))
                            .put("seconds", c.getLong(4)),
                    )
                    n++
                }
            }
        } catch (_: Exception) {
            // a locked-down OEM call-log provider: report nothing rather than crash
        }
        return arr
    }

    // -- SMS ---------------------------------------------------------------

    fun sendSms(ctx: Context, number: String, message: String): String {
        if (!has(ctx, Manifest.permission.SEND_SMS)) {
            return "ERR:the Send-SMS permission isn't granted"
        }
        return try {
            val sm = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                ctx.getSystemService(SmsManager::class.java)
            } else {
                @Suppress("DEPRECATION")
                SmsManager.getDefault()
            }
            val parts = sm.divideMessage(message)
            if (parts.size > 1) {
                sm.sendMultipartTextMessage(number, null, parts, null, null)
            } else {
                sm.sendTextMessage(number, null, message, null, null)
            }
            "OK:sent to $number"
        } catch (e: Exception) {
            "ERR:could not send the SMS (${e.message})"
        }
    }

    fun readSms(ctx: Context, limit: Int): JSONArray {
        val arr = JSONArray()
        if (!has(ctx, Manifest.permission.READ_SMS)) return arr
        try {
            ctx.contentResolver.query(
                Telephony.Sms.Inbox.CONTENT_URI,
                arrayOf(Telephony.Sms.ADDRESS, Telephony.Sms.BODY, Telephony.Sms.DATE),
                null, null,
                "${Telephony.Sms.DATE} DESC",
            )?.use { c ->
                var n = 0
                while (c.moveToNext() && n < limit.coerceIn(1, 50)) {
                    val from = c.getString(0) ?: ""
                    arr.put(
                        JSONObject()
                            .put("from", from)
                            .put("name", lookupNameFor(ctx, from) ?: "")
                            .put("text", (c.getString(1) ?: "").take(500))
                            .put("at", c.getLong(2)),
                    )
                    n++
                }
            }
        } catch (_: Exception) {
            // same reasoning as callLog
        }
        return arr
    }

    // -- apps ---------------------------------------------------------------

    private val SYSTEM_INTENTS = mapOf(
        "camera" to { -> Intent(MediaStore.ACTION_IMAGE_CAPTURE) },
        "dialer" to { -> Intent(Intent.ACTION_DIAL) },
        "settings" to { -> Intent(Settings.ACTION_SETTINGS) },
    )

    /**
     * Launches an app by its visible name. Unlike the Tier-1 agent's
     * hardcoded four-entry map, this resolves against everything actually
     * installed, so "spotify" or "paytm" work without an app update.
     */
    fun openApp(ctx: Context, name: String): String {
        val key = name.trim().lowercase()
        SYSTEM_INTENTS[key]?.let { make ->
            return try {
                ctx.startActivity(make().addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                "OK:opened $key"
            } catch (e: Exception) {
                "ERR:could not open $key (${e.message})"
            }
        }

        val pkg = resolvePackage(ctx, key)
            ?: return "ERR:no installed app matches '$name'"
        val launch = ctx.packageManager.getLaunchIntentForPackage(pkg)
            ?: return "ERR:'$name' is installed but has no launcher screen"
        return try {
            ctx.startActivity(launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            "OK:opened $name"
        } catch (e: Exception) {
            "ERR:could not open $name (${e.message})"
        }
    }

    private fun resolvePackage(ctx: Context, key: String): String? {
        val pm = ctx.packageManager
        val apps = pm.getInstalledApplications(0)
        // Exact label match wins over a substring one, so "phone" can never
        // resolve to "Phone Cleaner" while the real dialer sits right there.
        apps.firstOrNull { pm.getApplicationLabel(it).toString().equals(key, true) }?.let { return it.packageName }
        apps.firstOrNull { it.packageName.equals(key, true) }?.let { return it.packageName }
        apps.firstOrNull { pm.getApplicationLabel(it).toString().contains(key, true) }?.let { return it.packageName }
        return apps.firstOrNull { it.packageName.contains(key, true) }?.packageName
    }

    fun listApps(ctx: Context, filter: String?): JSONArray {
        val pm = ctx.packageManager
        val arr = JSONArray()
        pm.getInstalledApplications(0)
            .asSequence()
            .filter { pm.getLaunchIntentForPackage(it.packageName) != null }
            .map { pm.getApplicationLabel(it).toString() to it.packageName }
            .filter { (label, pkg) ->
                filter.isNullOrBlank() ||
                    label.contains(filter, true) || pkg.contains(filter, true)
            }
            .sortedBy { it.first.lowercase() }
            .take(200)
            .forEach { (label, pkg) ->
                arr.put(JSONObject().put("name", label).put("package", pkg))
            }
        return arr
    }

    // -- device --------------------------------------------------------------

    fun deviceStatus(ctx: Context): JSONObject {
        val bm = ctx.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

        val net = try {
            val caps = cm.getNetworkCapabilities(cm.activeNetwork)
            when {
                caps == null -> "offline"
                caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
                caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "mobile data"
                else -> "connected"
            }
        } catch (_: Exception) {
            "unknown"
        }

        return JSONObject()
            .put("battery_percent", bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY))
            .put("charging", bm.isCharging)
            .put("network", net)
            .put("model", "${Build.MANUFACTURER} ${Build.MODEL}")
            .put("android", Build.VERSION.RELEASE)
            .put("accessibility_enabled", LaylaAccessibilityService.isReady())
            .put("notification_access", LaylaNotificationListener.isReady())
    }
}
