package `in`.tryvanta.laylavoice

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.MediaPlayer
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.Future
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/**
 * Foreground Service that keeps Bluetooth Earpods connected in Hands-Free Communication mode
 * and continuously listens for Avishkar's voice + "Layla" trigger word, even when the phone is locked.
 */
class LaylaPodsService : Service() {

    private lateinit var btRouter: BluetoothAudioRouter
    private var recorder: ContinuousPodsRecorder? = null
    private val channelId = "layla_pods_channel"
    private val notificationId = 1001

    @Volatile private var isSpeaking = false
    @Volatile private var activePlayer: MediaPlayer? = null
    @Volatile private var playLatch: CountDownLatch? = null

    companion object {
        private const val TAG = "LaylaPodsService"
        const val ACTION_START = "in.tryvanta.laylavoice.ACTION_START_PODS"
        const val ACTION_STOP = "in.tryvanta.laylavoice.ACTION_STOP_PODS"

        @Volatile var isRunning = false
            private set

        var listener: PodsEventListener? = null

        fun start(context: Context) {
            val intent = Intent(context, LaylaPodsService::class.java).apply { action = ACTION_START }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            val intent = Intent(context, LaylaPodsService::class.java).apply { action = ACTION_STOP }
            context.startService(intent)
        }
    }

    interface PodsEventListener {
        fun onListeningStateChanged(listening: Boolean, speaking: Boolean)
        fun onUtteranceHeard(said: String)
        fun onReplyReady(said: String, answer: String)
        fun onError(error: String)
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        btRouter = BluetoothAudioRouter(this)
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                startForegroundPods()
            }
        }
        return START_STICKY
    }

    private fun startForegroundPods() {
        val isEnrolled = VoiceMatcher.isEnrolled(this)
        val wakeWordFree = getSharedPreferences("layla", MODE_PRIVATE).getBoolean("voiceprint_wakeword_free", true)
        val initialText = if (isEnrolled && wakeWordFree) {
            "Listening for Avishkar's voice via ear pods..."
        } else {
            "Listening for 'Layla' via ear pods..."
        }
        val notification = buildNotification(initialText)
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(notificationId, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE)
            } else {
                startForeground(notificationId, notification)
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error starting foreground service: ${e.message}", e)
            startForeground(notificationId, notification)
        }

        isRunning = true
        btRouter.setPodsCommunication(true)

        recorder = ContinuousPodsRecorder(
            this,
            onUtteranceCaptured = { wavB64 -> handleUtterance(wavB64) },
            onListeningStateChanged = { listening, speaking ->
                listener?.onListeningStateChanged(listening, speaking)
            }
        )
        recorder?.start()
        Log.i(TAG, "Layla Pods Service started and listening")
    }

    private fun handleUtterance(wavB64: String) {
        if (isSpeaking) return
        thread {
            val prefs = getSharedPreferences("layla", MODE_PRIVATE)
            val base = prefs.getString("base", "https://layla.tryvanta.in") ?: "https://layla.tryvanta.in"
            val token = prefs.getString("token", "")?.takeIf { it.isNotBlank() } ?: BuildConfig.DEFAULT_TOKEN
            val name = prefs.getString("name", "Avishkar") ?: "Avishkar"
            val isEnrolled = VoiceMatcher.isEnrolled(this)
            val wakeWordFree = prefs.getBoolean("voiceprint_wakeword_free", true)
            val defaultStatus = if (isEnrolled && wakeWordFree) "Listening for Avishkar via pods..." else "Listening for 'Layla' via ear pods..."
            val client = LaylaClient(base, token)

            try {
                updateNotification("Transcribing audio...")
                val said = client.stt(wavB64)
                if (said.isBlank()) {
                    updateNotification(defaultStatus)
                    return@thread
                }

                val lower = said.lowercase()
                val hasTrigger = lower.contains("layla") || lower.contains("leila") || lower.contains("laila")

                if (isEnrolled && wakeWordFree) {
                    Log.i(TAG, "Biometric match confirmed! Wake-word-free mode active. Routing intent: '$said'")
                } else if (!hasTrigger) {
                    Log.d(TAG, "Spoken text did not contain trigger word 'layla' ('$said'). Ignoring.")
                    updateNotification(defaultStatus)
                    return@thread
                }

                Log.i(TAG, "Trigger matched! Avishkar said: $said")
                listener?.onUtteranceHeard(said)
                updateNotification("Thinking: \"$said\"...")

                recorder?.pause()
                isSpeaking = true

                val (answer, tone) = client.ask("(Speaker: $name) $said")
                listener?.onReplyReady(said, answer)

                if (answer.isNotBlank()) {
                    if (prefs.getBoolean("tv", false)) {
                        try { client.sayOnTv(answer, tone) } catch (_: Exception) {}
                    } else {
                        updateNotification("Layla answering in pods...")
                        speakChunks(client, answer, tone)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error handling pods utterance: ${e.message}", e)
                listener?.onError(e.message ?: "Voice processing error")
            } finally {
                isSpeaking = false
                recorder?.resume()
                updateNotification("Listening for 'Layla' via ear pods...")
            }
        }
    }

    private fun speakChunks(client: LaylaClient, text: String, tone: String) {
        val chunks = Speech.split(text)
        val pool = Executors.newFixedThreadPool(2)
        try {
            val fut = arrayOfNulls<Future<ByteArray?>>(chunks.size)
            fun fetch(i: Int) {
                if (i < chunks.size && fut[i] == null)
                    fut[i] = pool.submit<ByteArray?> { try { client.tts(chunks[i], tone) } catch (_: Exception) { null } }
            }
            fetch(0); fetch(1)
            for (i in chunks.indices) {
                val mp3 = fut[i]!!.get()
                if (!isRunning) return
                fetch(i + 2)
                if (mp3 != null) playBlockingToPods(mp3, i)
            }
        } finally {
            pool.shutdownNow()
        }
    }

    private fun playBlockingToPods(mp3: ByteArray, index: Int) {
        val done = CountDownLatch(1)
        playLatch = done
        try {
            val f = File(cacheDir, "layla_pods_chunk_${index % 2}.mp3").apply { writeBytes(mp3) }
            val mp = MediaPlayer()
            activePlayer = mp

            val attrs = AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()
            mp.setAudioAttributes(attrs)

            mp.setDataSource(f.absolutePath)
            mp.setOnCompletionListener { done.countDown() }
            mp.setOnErrorListener { _, _, _ -> done.countDown(); true }
            mp.prepare()
            mp.start()
            done.await(60, TimeUnit.SECONDS)
            try { mp.release() } catch (_: Exception) {}
        } catch (e: Exception) {
            Log.e(TAG, "Error playing chunk to pods: ${e.message}")
        } finally {
            activePlayer = null
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "Layla Pods Mode",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Hands-free continuous ear pods communication with Layla"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(contentText: String): Notification {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0)
        )

        val stopIntent = Intent(this, LaylaPodsService::class.java).apply { action = ACTION_STOP }
        val stopPendingIntent = PendingIntent.getService(
            this, 1, stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0)
        )

        return NotificationCompat.Builder(this, channelId)
            .setContentTitle("Layla Pods Active 🎧")
            .setContentText(contentText)
            .setSmallIcon(R.drawable.ic_launcher_agent)
            .setContentIntent(pendingIntent)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Disconnect", stopPendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        manager.notify(notificationId, buildNotification(text))
    }

    override fun onDestroy() {
        super.onDestroy()
        isRunning = false
        playLatch?.countDown()
        try { activePlayer?.release() } catch (_: Exception) {}
        activePlayer = null

        recorder?.stop()
        recorder = null

        btRouter.setPodsCommunication(false)
        stopForeground(true)
        Log.i(TAG, "Layla Pods Service destroyed and Bluetooth audio restored")
    }
}
