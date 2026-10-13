package `in`.tryvanta.laylaphone

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken
import org.eclipse.paho.client.mqttv3.MqttCallbackExtended
import org.eclipse.paho.client.mqttv3.MqttClient
import org.eclipse.paho.client.mqttv3.MqttConnectOptions
import org.eclipse.paho.client.mqttv3.MqttMessage
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicLong

/**
 * Layla Phone Agent -- the Android-side companion for Phone Access.
 *
 * Connects OUTBOUND to the same secured broker the ESP32 home box, PC agent
 * and robot all use; no inbound port ever opens on this device.
 *
 * Topics (device_id = "phone-001"):
 *   cmd    tryvanta/phone/phone-001/cmd/<action>
 *   result tryvanta/phone/phone-001/result  {"cmd","status","detail","data"}
 *   status tryvanta/phone/phone-001/status  online|offline (retained, LWT)
 *
 * Payloads are JSON objects. A bare string is still accepted and mapped to
 * the action's primary argument, so the three Tier-1 commands keep working
 * byte-for-byte as the original server-side adapter sends them.
 *
 * The scope is no longer Tier 1. Calls, SMS and WhatsApp are implemented.
 * Those three run as soon as they arrive, because the owner asking Layla out
 * loud is the approval; the tap-to-confirm gate (CONFIRM_REQUIRED below) is
 * still here and still the only way they fire when the server marks a request
 * "confirm" -- which it does when the request grew out of text read off this
 * phone, and an outsider could have written that text.
 */
class PhoneAgentService : Service() {

    companion object {
        const val DEVICE_ID = "phone-001"
        const val HOST = "ssl://layla.tryvanta.in:8883"
        const val USER = "tvphone"
        const val PASS = "TVPHONE_MQTT_9300_G9QavA"
        const val BASE = "tryvanta/phone/$DEVICE_ID"

        const val CHANNEL_ID = "layla_phone_agent"
        const val CHANNEL_CONFIRM = "layla_phone_confirm"
        const val STATUS_NOTIF_ID = 1

        const val ACTION_APPROVE = "in.tryvanta.laylaphone.APPROVE"
        const val ACTION_DENY = "in.tryvanta.laylaphone.DENY"

        /**
         * The actions a human must physically approve on the phone. These are
         * exactly the ones that reach another person and cannot be taken back
         * once they land. Everything else -- reading, launching, answering or
         * ending a call already in progress -- runs directly, because making
         * the owner tap twice to hang up would just teach him to bypass the
         * gate entirely.
         */
        val CONFIRM_REQUIRED = setOf("call", "sms", "whatsapp")

        private const val APPROVAL_TIMEOUT_MS = 120_000L
    }

    private var client: MqttClient? = null
    private val work = Executors.newFixedThreadPool(2)
    private val main = Handler(Looper.getMainLooper())
    private val pending = ConcurrentHashMap<String, PendingAction>()
    private val seq = AtomicLong(0)

    private class PendingAction(
        val id: String,
        val cmd: String,
        val summary: String,
        val notifId: Int,
        val run: () -> String,
        val timeout: Runnable,
    )

    // -- lifecycle ---------------------------------------------------------

    override fun onCreate() {
        super.onCreate()
        createChannels()
        startForeground(STATUS_NOTIF_ID, buildStatusNotification("Connecting…"))
        connect()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_APPROVE -> resolve(intent.getStringExtra(ConfirmActivity.EXTRA_ID), true)
            ACTION_DENY -> resolve(intent.getStringExtra(ConfirmActivity.EXTRA_ID), false)
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        try {
            client?.publish(
                "$BASE/status",
                MqttMessage("offline".toByteArray()).apply { qos = 1; isRetained = true },
            )
            client?.disconnect()
        } catch (_: Exception) {
            // best-effort -- the broker's own LWT covers a hard kill
        }
        work.shutdownNow()
        super.onDestroy()
    }

    // -- notifications -----------------------------------------------------

    private fun createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Layla Phone Agent", NotificationManager.IMPORTANCE_LOW)
                .apply { description = "Keeps Layla connected to this phone" },
        )
        nm.createNotificationChannel(
            NotificationChannel(
                CHANNEL_CONFIRM,
                "Layla approval requests",
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = "Asks you before Layla calls or messages anyone"
                enableVibration(true)
            },
        )
    }

    private fun buildStatusNotification(status: String): Notification =
        NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Layla Phone Agent")
            .setContentText(status)
            .setSmallIcon(android.R.drawable.ic_secure)
            .setOngoing(true)
            .build()

    private fun updateStatusNotification(status: String) {
        getSystemService(NotificationManager::class.java)
            .notify(STATUS_NOTIF_ID, buildStatusNotification(status))
    }

    private fun showOwnerNotification(message: String) {
        val n = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Layla")
            .setContentText(message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        getSystemService(NotificationManager::class.java)
            .notify(System.currentTimeMillis().toInt(), n)
    }

    // -- MQTT ---------------------------------------------------------------

    private fun connect() {
        Thread {
            try {
                val c = MqttClient(
                    HOST,
                    "layla-phoneagent-$DEVICE_ID-${System.currentTimeMillis()}",
                    null,
                )
                val opts = MqttConnectOptions().apply {
                    userName = USER
                    password = PASS.toCharArray()
                    isAutomaticReconnect = true
                    connectionTimeout = 15
                    keepAliveInterval = 30
                    isCleanSession = true
                    setWill("$BASE/status", "offline".toByteArray(), 1, true)
                }
                c.setCallback(object : MqttCallbackExtended {
                    override fun connectComplete(reconnect: Boolean, serverURI: String?) {
                        c.subscribe("$BASE/cmd/+", 1)
                        c.publish(
                            "$BASE/status",
                            MqttMessage("online".toByteArray()).apply { qos = 1; isRetained = true },
                        )
                        updateStatusNotification("Connected")
                    }

                    override fun connectionLost(cause: Throwable?) {
                        updateStatusNotification("Reconnecting…")
                    }

                    override fun messageArrived(topic: String?, message: MqttMessage?) {
                        val action = topic?.substringAfterLast("/") ?: return
                        val raw = String(message?.payload ?: ByteArray(0))
                        // Off the MQTT callback thread: a slow action (WhatsApp
                        // takes seconds to render) would otherwise stall the
                        // keepalive and drop the connection mid-command.
                        work.execute { dispatch(action, raw) }
                    }

                    override fun deliveryComplete(token: IMqttDeliveryToken?) {}
                })
                c.connect(opts)
                client = c
            } catch (e: Exception) {
                updateStatusNotification("Connection failed: ${e.message}")
            }
        }.start()
    }

    private fun publishResult(cmd: String, status: String, detail: String, data: Any? = null) {
        val payload = JSONObject()
            .put("cmd", cmd)
            .put("status", status)
            .put("detail", detail)
        if (data != null) payload.put("data", data)
        try {
            client?.publish(
                "$BASE/result",
                MqttMessage(payload.toString().toByteArray()).apply { qos = 1 },
            )
        } catch (_: Exception) {
            // best-effort; if the publish itself fails there's nothing left to do
        }
    }

    // -- command dispatch ----------------------------------------------------

    /** Accepts a JSON object payload, or a bare string for the legacy commands. */
    private fun parseArgs(action: String, raw: String): JSONObject {
        val trimmed = raw.trim()
        if (trimmed.startsWith("{")) {
            try {
                return JSONObject(trimmed)
            } catch (_: Exception) {
                // fall through and treat it as a plain string
            }
        }
        val key = when (action) {
            "notify" -> "message"
            "open_url" -> "url"
            "open_app" -> "app"
            "contacts" -> "query"
            "call" -> "to"
            "screen_text", "device", "answer_call", "end_call" -> return JSONObject()
            "ui_tap", "ui_type" -> "text"
            "ui_global" -> "action"
            "ui_scroll" -> "direction"
            else -> "value"
        }
        return JSONObject().put(key, trimmed)
    }

    private fun dispatch(action: String, raw: String) {
        val args = try {
            parseArgs(action, raw)
        } catch (e: Exception) {
            publishResult(action, "error", "bad payload: ${e.message}")
            return
        }

        try {
            if (action in CONFIRM_REQUIRED) {
                stageForApproval(action, args)
            } else {
                val (status, detail, data) = runFree(action, args)
                publishResult(action, status, detail, data)
            }
        } catch (e: Exception) {
            publishResult(action, "error", e.message ?: "unknown error")
        }
    }

    /** Actions that run immediately. Returns (status, detail, data?). */
    private fun runFree(action: String, a: JSONObject): Triple<String, String, Any?> {
        fun str(k: String) = a.optString(k).trim()
        fun need(k: String): String =
            str(k).ifEmpty { throw IllegalArgumentException("$action needs '$k'") }

        val acc = { LaylaAccessibilityService.get() }
        val noAcc = "App control is off — open Layla Phone Agent and turn on the " +
            "Accessibility service, then try again"

        return when (action) {
            "notify" -> {
                showOwnerNotification(need("message"))
                ok("notification shown")
            }

            "open_url" -> {
                val url = need("url")
                if (!url.startsWith("http://") && !url.startsWith("https://")) {
                    throw IllegalArgumentException("only http(s) URLs are allowed")
                }
                startActivity(
                    Intent(Intent.ACTION_VIEW, Uri.parse(url))
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
                ok("opened $url")
            }

            "open_app" -> fromAction(PhoneActions.openApp(this, need("app")))
            "list_apps" -> {
                val list = PhoneActions.listApps(this, a.optString("filter").ifBlank { null })
                Triple("success", "${list.length()} apps", list)
            }

            "contacts" -> {
                val hits = PhoneActions.searchContacts(this, need("query"))
                if (hits.length() == 0) {
                    Triple("success", "no contact matches '${str("query")}'", JSONArray())
                } else {
                    Triple("success", "${hits.length()} match(es)", hits)
                }
            }

            "read_sms" -> {
                val msgs = PhoneActions.readSms(this, a.optInt("limit", 10))
                Triple("success", "${msgs.length()} message(s)", msgs)
            }

            "call_log" -> {
                val log = PhoneActions.callLog(this, a.optInt("limit", 10))
                Triple("success", "${log.length()} call(s)", log)
            }

            "notifications" -> {
                if (!LaylaNotificationListener.isReady()) {
                    throw IllegalStateException(
                        "Notification access is off — turn it on in Layla Phone Agent",
                    )
                }
                val items = LaylaNotificationListener.snapshot(
                    a.optInt("limit", 15),
                    a.optString("app").ifBlank { null },
                )
                Triple("success", "${items.length()} notification(s)", items)
            }

            "device" -> Triple("success", "device status", PhoneActions.deviceStatus(this))

            "answer_call" -> fromAction(PhoneActions.answerCall(this))
            "end_call" -> fromAction(PhoneActions.endCall(this))

            "screen_text" -> {
                val a2 = acc() ?: throw IllegalStateException(noAcc)
                val lines = JSONArray().apply { a2.screenText().forEach { put(it) } }
                Triple("success", a2.currentPackage() ?: "screen", lines)
            }

            "ui_tap" -> {
                val a2 = acc() ?: throw IllegalStateException(noAcc)
                val label = need("text")
                if (a2.tapText(label)) ok("tapped '$label'")
                else Triple("error", "nothing on screen matches '$label'", null)
            }

            "ui_type" -> {
                val a2 = acc() ?: throw IllegalStateException(noAcc)
                if (a2.typeText(need("text"))) ok("typed")
                else Triple("error", "no text field is focused on screen", null)
            }

            "ui_global" -> {
                val a2 = acc() ?: throw IllegalStateException(noAcc)
                val g = need("action")
                if (a2.globalAction(g)) ok(g)
                else Triple("error", "unknown screen action '$g'", null)
            }

            "ui_scroll" -> {
                val a2 = acc() ?: throw IllegalStateException(noAcc)
                val d = a.optString("direction").ifBlank { "down" }
                if (a2.scroll(d)) ok("scrolled $d")
                else Triple("error", "nothing scrollable on screen", null)
            }

            else -> Triple("error", "unknown command '$action'", null)
        }
    }

    private fun ok(detail: String) = Triple("success", detail, null as Any?)

    /** Maps the "OK:…" / "ERR:…" convention PhoneActions uses onto a result. */
    private fun fromAction(r: String): Triple<String, String, Any?> =
        if (r.startsWith("OK:")) Triple("success", r.removePrefix("OK:"), null)
        else Triple("error", r.removePrefix("ERR:"), null)

    // -- the approval gate -----------------------------------------------------

    private fun stageForApproval(action: String, a: JSONObject) {
        val to = a.optString("to").trim().ifEmpty { a.optString("number").trim() }
        if (to.isEmpty()) {
            publishResult(action, "error", "$action needs a 'to' (a contact name or number)")
            return
        }
        val message = a.optString("message").trim()
        if (action != "call" && message.isEmpty()) {
            publishResult(action, "error", "$action needs a 'message'")
            return
        }

        val who = PhoneActions.resolveRecipient(this, to)
        if (who == null) {
            publishResult(
                action, "error",
                "no contact or usable number matches '$to' — give me the number directly",
            )
            return
        }

        val title = when (action) {
            "call" -> "Call ${who.display()}?"
            "sms" -> "Send an SMS to ${who.display()}?"
            else -> "Send a WhatsApp to ${who.display()}?"
        }
        val body = if (action == "call") "" else "\"$message\""

        val id = "${action}-${seq.incrementAndGet()}-${System.currentTimeMillis()}"
        val notifId = 1000 + (seq.get().toInt() % 8000)

        val execute: () -> String = when (action) {
            "call" -> ({ PhoneActions.placeCall(this, who.number) })
            "sms" -> ({ PhoneActions.sendSms(this, who.number, message) })
            else -> ({
                LaylaAccessibilityService.get()
                    ?.sendWhatsApp(who.number, message)
                    ?: "ERR:App control is off — turn on the Accessibility service in " +
                    "Layla Phone Agent, WhatsApp can't be driven without it"
            })
        }

        // The owner asking for it IS the approval, so act at once. Layla sets
        // "confirm" only when the request traces back to text she read off the
        // phone (an SMS, a notification, the screen) — an outsider could have
        // written that, so it still takes a deliberate tap.
        if (!a.optBoolean("confirm", false)) {
            work.execute {
                val r = try {
                    execute()
                } catch (e: Exception) {
                    "ERR:${e.message}"
                }
                val (status, detail, _) = fromAction(r)
                publishResult(action, status, detail)
            }
            return
        }

        val timeout = Runnable {
            pending.remove(id)?.let {
                cancelNotification(it.notifId)
                publishResult(action, "error", "you didn't respond — I cancelled the request")
            }
        }

        pending[id] = PendingAction(id, action, title, notifId, execute, timeout)
        main.postDelayed(timeout, APPROVAL_TIMEOUT_MS)

        askOwner(id, notifId, title, body)
    }

    /**
     * Raises the request two ways on purpose. The dialog is the nicer
     * surface, but Android blocks background activity starts in several
     * real situations (another app foregrounded, OEM pop-up restrictions on
     * Funtouch); the heads-up notification with Allow/Deny buttons always
     * lands. Whichever the owner sees first resolves the same request id.
     */
    private fun askOwner(id: String, notifId: Int, title: String, body: String) {
        val confirmIntent = Intent(this, ConfirmActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            putExtra(ConfirmActivity.EXTRA_ID, id)
            putExtra(ConfirmActivity.EXTRA_TITLE, title)
            putExtra(ConfirmActivity.EXTRA_BODY, body)
        }

        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        val fullScreen = PendingIntent.getActivity(this, notifId, confirmIntent, flags)
        val allow = PendingIntent.getService(
            this, notifId + 1,
            Intent(this, PhoneAgentService::class.java)
                .setAction(ACTION_APPROVE)
                .putExtra(ConfirmActivity.EXTRA_ID, id),
            flags,
        )
        val deny = PendingIntent.getService(
            this, notifId + 2,
            Intent(this, PhoneAgentService::class.java)
                .setAction(ACTION_DENY)
                .putExtra(ConfirmActivity.EXTRA_ID, id),
            flags,
        )

        val n = NotificationCompat.Builder(this, CHANNEL_CONFIRM)
            .setContentTitle(title)
            .setContentText(body.ifBlank { "Tap Allow to let Layla go ahead." })
            .setStyle(NotificationCompat.BigTextStyle().bigText(body.ifBlank { "Tap Allow to let Layla go ahead." }))
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setAutoCancel(false)
            .setOngoing(true)
            .setFullScreenIntent(fullScreen, true)
            .addAction(0, "Allow", allow)
            .addAction(0, "Deny", deny)
            .build()
        getSystemService(NotificationManager::class.java).notify(notifId, n)

        try {
            startActivity(confirmIntent)
        } catch (_: Exception) {
            // Blocked by background-activity-start rules; the notification above
            // is the real guarantee, so this failing is not an error.
        }
    }

    private fun resolve(id: String?, approved: Boolean) {
        val p = id?.let { pending.remove(it) } ?: return
        main.removeCallbacks(p.timeout)
        cancelNotification(p.notifId)

        if (!approved) {
            publishResult(p.cmd, "denied", "you said no — I didn't do it")
            return
        }

        work.execute {
            val r = try {
                p.run()
            } catch (e: Exception) {
                "ERR:${e.message}"
            }
            val (status, detail, _) = fromAction(r)
            publishResult(p.cmd, status, detail)
        }
    }

    private fun cancelNotification(id: Int) {
        try {
            getSystemService(NotificationManager::class.java).cancel(id)
        } catch (_: Exception) {
        }
    }
}
