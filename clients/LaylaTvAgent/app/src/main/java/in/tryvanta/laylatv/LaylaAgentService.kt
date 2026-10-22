package `in`.tryvanta.laylatv

import android.app.*
import android.content.Context
import android.content.Intent
import android.graphics.ImageFormat
import android.hardware.camera2.*
import android.media.ImageReader
import android.os.*
import android.util.Log
import androidx.core.app.NotificationCompat
import org.eclipse.paho.client.mqttv3.*
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Single always-on foreground service: holds the MQTT control channel and
 * grabs ONE camera frame on demand. No visible preview — Camera2 captures
 * straight into an ImageReader, so there is no overlay/TextureView/headless-
 * activity trampoline to fight Google TV over. The "camera" FGS type is what
 * actually lets the capture run while the app is backgrounded on Android 11+.
 *
 * NOTE: the room frame is published back over MQTT (same pattern as the door
 * bridge), NOT HTTP-POSTed to /room_diag — that endpoint is owner-cookie
 * gated and an APK can't do Google OAuth. MQTT reuses the broker credential
 * the agent already holds. (If you prefer HTTP, add a bearer-token endpoint
 * on the brain; see notes.)
 */
class LaylaAgentService : Service() {

    companion object {
        const val TAG = "LaylaAgent"
        const val CH = "layla_agent"
        const val NOTIF_ID = 42
        // ---- fill these in ----
        const val BROKER = "ssl://layla.tryvanta.in:8883"
        const val USER = "tvagent"          // dedicated broker user, isolated from tvcam
        const val PASS = "dppgNDCXWpqwk9uQlCPr"
        const val CMD_TOPIC = "layla/tv/cmd/#"
        const val SNAP_RESULT = "tryvanta/camera/room/result"   // server subscribes here
        const val STATUS_TOPIC = "layla/tv/status"
    }

    private lateinit var camThread: HandlerThread
    private lateinit var camHandler: Handler
    private var client: MqttAsyncClient? = null
    private val capturing = AtomicBoolean(false)

    override fun onBind(i: Intent?) = null

    override fun onCreate() {
        super.onCreate()
        startForeground(NOTIF_ID, buildNotification())
        camThread = HandlerThread("cam").also { it.start() }
        camHandler = Handler(camThread.looper)
        connectMqtt()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // START_STICKY + BootReceiver + MQTT auto-reconnect = "always restarting"
        return START_STICKY
    }

    // ───────────────────────── MQTT ─────────────────────────
    private fun connectMqtt() {
        try {
            val c = MqttAsyncClient(BROKER, "layla-tvagent-" + stableId(), MemoryPersistence())
            client = c
            val opts = MqttConnectOptions().apply {
                userName = USER
                password = PASS.toCharArray()
                isAutomaticReconnect = true      // the real "always-on" mechanism
                isCleanSession = true
                connectionTimeout = 15
                keepAliveInterval = 30
                setWill(STATUS_TOPIC, "offline".toByteArray(), 1, true)
            }
            c.setCallback(object : MqttCallbackExtended {
                override fun connectComplete(reconnect: Boolean, uri: String?) {
                    c.subscribe(CMD_TOPIC, 1)
                    c.publish(STATUS_TOPIC, MqttMessage("online".toByteArray()).apply { isRetained = true; qos = 1 })
                    Log.i(TAG, "mqtt connected (reconnect=$reconnect)")
                }
                override fun connectionLost(cause: Throwable?) { Log.w(TAG, "mqtt lost: $cause") }
                override fun deliveryComplete(t: IMqttDeliveryToken?) {}
                override fun messageArrived(topic: String, msg: MqttMessage) = onCommand(topic, msg)
            })
            c.connect(opts)
        } catch (e: Exception) { Log.e(TAG, "mqtt connect failed", e); camHandler.postDelayed({ connectMqtt() }, 5000) }
    }

    private fun onCommand(topic: String, msg: MqttMessage) {
        val action = topic.substringAfterLast('/')
        val body = runCatching { JSONObject(String(msg.payload)) }.getOrDefault(JSONObject())
        when (action) {
            "snap" -> captureFrame(body.optString("reqid", "noreq"))
            // key/nav/media/launch commands are handed to the accessibility
            // service + TvController (see LaylaAccessibilityService / TvController)
            else -> TvController.dispatch(this, action, body)
        }
    }

    // ─────────────────────── Camera grab ───────────────────────
    // Opening a USB webcam cold and grabbing one still immediately gives a
    // black/underexposed frame -- auto-exposure/white-balance need several
    // streaming frames to converge (the browser looked fine only because its
    // live preview had already converged). So we run a REPEATING request to
    // the JPEG reader, keep the newest frame, and after an AE-settle window
    // publish the last (properly-exposed) one, then tear everything down.
    private fun captureFrame(reqid: String) {
        if (!capturing.compareAndSet(false, true)) return
        val mgr = getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val camId = pickCamera(mgr) ?: run {
            publishResult(reqid, "ERR:no camera enumerated by Camera2")
            capturing.set(false); return
        }
        val reader = ImageReader.newInstance(1920, 1080, ImageFormat.JPEG, 4)
        val latest = arrayOfNulls<ByteArray>(1)
        val frames = java.util.concurrent.atomic.AtomicInteger(0)
        var device: CameraDevice? = null
        var session: CameraCaptureSession? = null
        val finished = AtomicBoolean(false)

        fun cleanup() {
            runCatching { session?.stopRepeating() }
            runCatching { session?.close() }
            runCatching { device?.close() }
            runCatching { reader.close() }
            capturing.set(false)
        }
        fun finish() {
            if (!finished.compareAndSet(false, true)) return
            val bytes = latest[0]
            if (bytes != null)
                publishResult(reqid, android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP))
            else
                publishResult(reqid, "ERR:no frame delivered (frames=${frames.get()})")
            cleanup()
        }

        reader.setOnImageAvailableListener({ r ->
            val img = r.acquireLatestImage() ?: return@setOnImageAvailableListener
            try {
                val buf = img.planes[0].buffer
                latest[0] = ByteArray(buf.remaining()).also { buf.get(it) }
                frames.incrementAndGet()
            } finally { img.close() }
        }, camHandler)

        try {
            mgr.openCamera(camId, object : CameraDevice.StateCallback() {
                override fun onOpened(dev: CameraDevice) {
                    device = dev
                    val req = dev.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply {
                        addTarget(reader.surface)
                        set(CaptureRequest.JPEG_ORIENTATION, 0)
                        set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO)
                        set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON)
                        set(CaptureRequest.CONTROL_AWB_MODE, CaptureRequest.CONTROL_AWB_MODE_AUTO)
                        // nudge brighter for a dim evening room, if supported
                        runCatching { set(CaptureRequest.CONTROL_AE_EXPOSURE_COMPENSATION, 2) }
                    }
                    dev.createCaptureSession(listOf(reader.surface), object : CameraCaptureSession.StateCallback() {
                        override fun onConfigured(s: CameraCaptureSession) {
                            session = s
                            runCatching { s.setRepeatingRequest(req.build(), null, camHandler) }
                            // let AE/AWB converge over ~1.8s of streaming, then
                            // keep the newest frame.
                            camHandler.postDelayed({ finish() }, 1800)
                        }
                        override fun onConfigureFailed(s: CameraCaptureSession) {
                            publishResult(reqid, "ERR:session config failed"); cleanup()
                        }
                    }, camHandler)
                }
                // Was silently swallowing the failure: no publishResult here
                // meant the server waited out its whole timeout with no idea
                // why. This is the path Android takes when it REVOKES camera
                // access from a foreground service that was started while the
                // app was in the background (Android 14 while-in-use rule) --
                // found 2026-10-06, after an ADB restart put the service in
                // exactly that state and room scans went quiet.
                override fun onDisconnected(dev: CameraDevice) {
                    device = dev
                    if (!finished.get()) publishResult(reqid,
                        "ERR:camera disconnected/revoked (frames=${frames.get()}) -- " +
                        "service may have been started from background without camera rights")
                    cleanup()
                }
                override fun onError(dev: CameraDevice, err: Int) {
                    device = dev; if (!finished.get()) publishResult(reqid, "ERR:camera error $err"); cleanup()
                }
            }, camHandler)
        } catch (e: Exception) { publishResult(reqid, "ERR:${e.message}"); cleanup() }
    }

    /** Prefer an EXTERNAL (USB) camera; fall back to the first available id. */
    private fun pickCamera(mgr: CameraManager): String? {
        return try {
            val ids = mgr.cameraIdList
            ids.firstOrNull {
                mgr.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING) ==
                    CameraCharacteristics.LENS_FACING_EXTERNAL
            } ?: ids.firstOrNull()
        } catch (e: Exception) { Log.e(TAG, "enumerate failed", e); null }
    }

    /** Stable per-install MQTT client id (two clients with the same id fight
     *  over the broker session; Build.SERIAL is "unknown" without permission). */
    private fun stableId(): String {
        val p = getSharedPreferences("layla", Context.MODE_PRIVATE)
        return p.getString("cid", null) ?: UUID.randomUUID().toString().take(12)
            .also { p.edit().putString("cid", it).apply() }
    }

    private fun publishResult(reqid: String, payload: String) {
        runCatching {
            client?.publish("$SNAP_RESULT/$reqid", MqttMessage(payload.toByteArray()).apply { qos = 1 })
        }.onFailure { Log.e(TAG, "publish failed", it) }
    }

    // ─────────────────────── FGS notification ───────────────────────
    private fun buildNotification(): Notification {
        (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .createNotificationChannel(NotificationChannel(CH, "Layla Agent", NotificationManager.IMPORTANCE_MIN))
        return NotificationCompat.Builder(this, CH)
            .setContentTitle("Layla is active")
            .setSmallIcon(R.drawable.ic_launcher)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .build()
    }

    override fun onDestroy() {
        runCatching { client?.disconnectForcibly() }
        LaylaTts.shutdown()   // so a recycled service re-inits the engine cleanly
        camThread.quitSafely()
        // ask the system to bring us back
        sendBroadcast(Intent(this, BootReceiver::class.java).setAction("RESTART"))
        super.onDestroy()
    }
}
