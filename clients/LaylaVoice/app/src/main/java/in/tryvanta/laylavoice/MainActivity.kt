package `in`.tryvanta.laylavoice

import android.Manifest
import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.Future
import java.util.concurrent.TimeUnit
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import kotlin.concurrent.thread

/**
 * Tryvanta Layla voice app. First launch asks who is talking, so Layla knows which family member it is.
 * Hold the orb, speak, release: mic -> /stt -> /ask; the reply shows here and is spoken on the TV by the brain.
 * Long-press "Layla" to change name / server / token.
 */
class MainActivity : AppCompatActivity() {
    private val rec = Recorder()
    private val rose = Color.parseColor("#FF5C93")
    private val dim = Color.parseColor("#B9BBC9")
    private lateinit var prefs: SharedPreferences
    private lateinit var status: TextView
    private lateinit var hint: TextView
    private lateinit var orb: OrbView
    @Volatile private var player: MediaPlayer? = null
    @Volatile private var speakGen = 0
    @Volatile private var playLatch: CountDownLatch? = null
    private val idle = "TAP & HOLD\nTO TALK TO LAYLA"

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun label(s: String, sp: Float, color: Int, tf: Typeface = Typeface.DEFAULT) =
        TextView(this).apply {
            text = s; setTextSize(TypedValue.COMPLEX_UNIT_SP, sp); setTextColor(color); typeface = tf; gravity = Gravity.CENTER
        }

    private fun page(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = Gravity.CENTER_HORIZONTAL
        background = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
            intArrayOf(Color.parseColor("#0A0B12"), Color.parseColor("#151829"), Color.parseColor("#090A10")))
        setPadding(dp(24), 0, dp(24), dp(24))
    }

    private fun header(root: LinearLayout): TextView {
        root.addView(LogoView(this), LinearLayout.LayoutParams(dp(46), dp(52)).apply { topMargin = dp(48) })
        root.addView(label("Tryvanta", 38f, Color.WHITE, Typeface.create("sans-serif-light", Typeface.NORMAL)),
            LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { topMargin = dp(10) })
        val sub = label("Layla", 21f, dim, Typeface.create(Typeface.SERIF, Typeface.ITALIC))
        root.addView(sub, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { topMargin = dp(4) })
        return sub
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = Color.parseColor("#0A0B12")
        window.navigationBarColor = Color.parseColor("#090A10")
        prefs = getSharedPreferences("layla", MODE_PRIVATE)
        if (prefs.getString("name", "").isNullOrBlank()) showWelcome() else showTalk()
    }

    private fun showWelcome() {
        val root = page()
        header(root)
        root.addView(label("Welcome. Who is talking to Layla?", 16f, dim),
            LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { topMargin = dp(56) })
        val name = EditText(this).apply {
            hint = "Your name"
            setHintTextColor(Color.parseColor("#6F7185"))
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 22f)
            gravity = Gravity.CENTER
            setSingleLine()
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS
            backgroundTintList = ColorStateList.valueOf(rose)
        }
        root.addView(name, LinearLayout.LayoutParams(dp(260), WRAP_CONTENT).apply { topMargin = dp(18) })
        val go = Button(this).apply {
            text = "Continue"
            setTextColor(Color.WHITE)
            isAllCaps = false
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
            background = GradientDrawable().apply { cornerRadius = dp(28).toFloat(); setColor(Color.parseColor("#D93F78")) }
            setOnClickListener {
                val n = name.text.toString().trim()
                if (n.isEmpty()) { name.error = "Type your name"; return@setOnClickListener }
                prefs.edit().putString("name", n).apply()
                showTalk()
            }
        }
        root.addView(go, LinearLayout.LayoutParams(dp(220), dp(54)).apply { topMargin = dp(28) })
        setContentView(root)
    }

    @SuppressLint("ClickableViewAccessibility")
    private fun showTalk() {
        val name = prefs.getString("name", "") ?: ""
        val root = page()
        header(root).setOnLongClickListener { showSettings(); true }

        val side = (resources.displayMetrics.widthPixels * .86f).toInt()
        orb = OrbView(this)
        status = label(idle, 12f, Color.WHITE).apply { letterSpacing = .06f }
        val holder = FrameLayout(this)
        holder.addView(orb, FrameLayout.LayoutParams(side, side))
        holder.addView(status, FrameLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT, Gravity.CENTER_HORIZONTAL)
            .apply { topMargin = (side * .64f).toInt() })
        root.addView(holder, LinearLayout.LayoutParams(side, side).apply { topMargin = dp(18) })

        val tv = TextView(this).apply {
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f); gravity = Gravity.CENTER; setPadding(dp(18), dp(8), dp(18), dp(8))
        }
        fun paintTv() {
            val on = prefs.getBoolean("tv", false)
            tv.text = if (on) "TV: ON  •  Layla talks on the TV screen" else "TV: OFF  •  voice on this phone"
            tv.setTextColor(if (on) Color.WHITE else dim)
            tv.background = GradientDrawable().apply {
                cornerRadius = dp(20).toFloat()
                if (on) setColor(Color.parseColor("#D93F78")) else { setColor(Color.TRANSPARENT); setStroke(dp(1), Color.parseColor("#4A4D63")) }
            }
        }
        paintTv()
        tv.setOnClickListener { prefs.edit().putBoolean("tv", !prefs.getBoolean("tv", false)).apply(); paintTv() }
        root.addView(tv, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { topMargin = dp(8) })

        val pods = TextView(this).apply {
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f); gravity = Gravity.CENTER; setPadding(dp(18), dp(8), dp(18), dp(8))
        }
        fun paintPods() {
            val on = LaylaPodsService.isRunning
            val isEnrolled = VoiceMatcher.isEnrolled(this)
            val wakeFree = prefs.getBoolean("voiceprint_wakeword_free", true)
            pods.text = when {
                on && isEnrolled && wakeFree -> "PODS: ACTIVE 🎧  •  Voiceprint (No Wake-Word)"
                on -> "PODS: ACTIVE 🎧  •  Always Listening ('Layla')"
                else -> "PODS: OFF  •  Tap to connect Ear Pods"
            }
            pods.setTextColor(if (on) Color.WHITE else dim)
            pods.background = GradientDrawable().apply {
                cornerRadius = dp(20).toFloat()
                if (on) setColor(Color.parseColor("#4C2A6F")) else { setColor(Color.TRANSPARENT); setStroke(dp(1), Color.parseColor("#4A4D63")) }
            }
        }
        paintPods()
        pods.setOnClickListener {
            togglePods { paintPods() }
        }
        root.addView(pods, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply { topMargin = dp(8) })

        hint = label("Hello $name. Try: \"Turn up the volume\"", 15f, dim)
        root.addView(hint, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { topMargin = dp(18) })
        setContentView(root)

        val neededPerms = mutableListOf<String>()
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
            neededPerms.add(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED)
            neededPerms.add(Manifest.permission.BLUETOOTH_CONNECT)
        if (neededPerms.isNotEmpty())
            ActivityCompat.requestPermissions(this, neededPerms.toTypedArray(), 1)

        orb.setOnTouchListener { v, e ->
            when (e.action) {
                MotionEvent.ACTION_DOWN -> {
                    v.parent.requestDisallowInterceptTouchEvent(true)
                    stopVoice()
                    rec.start()
                    orb.holding = true
                    status.text = "HOLDING...\nLAYLA IS LISTENING"
                    true
                }
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    orb.holding = false
                    v.performClick()
                    handle(name)
                    true
                }
                else -> false
            }
        }
    }

    private fun togglePods(onChanged: () -> Unit) {
        val perms = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            perms.add(Manifest.permission.BLUETOOTH_CONNECT)
        }
        val needed = perms.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (needed.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, needed.toTypedArray(), 102)
            return
        }

        if (LaylaPodsService.isRunning) {
            LaylaPodsService.stop(this)
            status.text = idle
        } else {
            LaylaPodsService.start(this)
            val isEnrolled = VoiceMatcher.isEnrolled(this)
            val wakeFree = prefs.getBoolean("voiceprint_wakeword_free", true)
            status.text = if (isEnrolled && wakeFree) {
                "PODS CONNECTED 🎧\nALWAYS LISTENING FOR AVISHKAR"
            } else {
                "PODS CONNECTED 🎧\nALWAYS LISTENING FOR 'LAYLA'"
            }
        }
        onChanged()
    }

    private fun showSettings() {
        val pad = dp(16)
        val scroll = ScrollView(this)
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad, pad, pad) }
        scroll.addView(col)

        fun field(h: String, v: String) = EditText(this).apply { hint = h; setText(v); setSingleLine() }.also { col.addView(it) }
        val n = field("Your name", prefs.getString("name", "") ?: "")
        val b = field("Brain URL", prefs.getString("base", "https://layla.tryvanta.in") ?: "")
        val t = field("Device token", prefs.getString("token", "")?.takeIf { it.isNotBlank() } ?: BuildConfig.DEFAULT_TOKEN)

        // Voiceprint Biometric Section
        val bioHeader = TextView(this).apply {
            text = "🎙️ Voiceprint Biometrics (Ear Pods)"
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setTextColor(rose)
            setTypeface(null, Typeface.BOLD)
            setPadding(0, dp(14), 0, dp(4))
        }
        col.addView(bioHeader)

        val bioStatus = TextView(this).apply {
            text = VoiceMatcher.getEnrolledDetails(this@MainActivity)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
            setTextColor(if (VoiceMatcher.isEnrolled(this@MainActivity)) Color.parseColor("#00E676") else dim)
            setPadding(0, 0, 0, dp(8))
        }
        col.addView(bioStatus)

        val enrollBtn = Button(this).apply {
            text = if (VoiceMatcher.isEnrolled(this@MainActivity)) "🔄 RE-CALIBRATE MY VOICE BIOMETRIC" else "🎙️ ENROLL MY VOICE BIOMETRIC"
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            background = GradientDrawable().apply {
                cornerRadius = dp(20).toFloat()
                setColor(Color.parseColor("#6A1B9A"))
            }
        }
        col.addView(enrollBtn, LinearLayout.LayoutParams(MATCH_PARENT, dp(44)).apply { bottomMargin = dp(8) })

        val wakeFreeCb = CheckBox(this).apply {
            text = "Wake-Word-Free Mode (No 'Layla' needed)"
            setTextColor(Color.WHITE)
            isChecked = prefs.getBoolean("voiceprint_wakeword_free", true)
        }
        col.addView(wakeFreeCb)

        val pMin = field("Voice Pitch Min Hz (default 85)", prefs.getFloat("voice_pitch_min", 85f).toInt().toString())
        val pMax = field("Voice Pitch Max Hz (default 185)", prefs.getFloat("voice_pitch_max", 185f).toInt().toString())

        val dialog = AlertDialog.Builder(this).setTitle("Settings").setView(scroll)
            .setPositiveButton("Save") { _, _ ->
                val minHz = pMin.text.toString().toFloatOrNull() ?: 85f
                val maxHz = pMax.text.toString().toFloatOrNull() ?: 185f
                prefs.edit().putString("name", n.text.toString().trim())
                    .putString("base", b.text.toString().trim())
                    .putString("token", t.text.toString().trim())
                    .putBoolean("voiceprint_wakeword_free", wakeFreeCb.isChecked)
                    .putFloat("voice_pitch_min", minHz)
                    .putFloat("voice_pitch_max", maxHz)
                    .apply()
                if (prefs.getString("name", "").isNullOrBlank()) showWelcome() else showTalk()
            }.setNegativeButton("Cancel", null).create()

        enrollBtn.setOnClickListener {
            dialog.dismiss()
            showVoiceEnrollmentDialog()
        }

        dialog.show()
    }

    @SuppressLint("MissingPermission")
    private fun showVoiceEnrollmentDialog() {
        val pad = dp(16)
        val view = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
        }

        val promptTitle = TextView(this).apply {
            text = "Voiceprint Biometric Enrollment"
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            setTextColor(Color.WHITE)
            setTypeface(null, Typeface.BOLD)
            gravity = Gravity.CENTER
        }
        view.addView(promptTitle)

        val instructions = TextView(this).apply {
            text = "Connect your Boult Ear Pods. Tap 'Start Recording' and read the prompt naturally for 5 seconds."
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setTextColor(dim)
            gravity = Gravity.CENTER
            setPadding(0, dp(8), 0, dp(12))
        }
        view.addView(instructions)

        val promptCard = TextView(this).apply {
            text = "\"Hey Layla, this is Avishkar. I am calibrating my biometric voice signature for hands-free ear pods mode.\""
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setTextColor(Color.parseColor("#FFD54F"))
            setTypeface(null, Typeface.ITALIC)
            gravity = Gravity.CENTER
            setPadding(dp(12), dp(12), dp(12), dp(12))
            background = GradientDrawable().apply {
                cornerRadius = dp(10).toFloat()
                setColor(Color.parseColor("#252836"))
                setStroke(dp(1), Color.parseColor("#4A4D63"))
            }
        }
        view.addView(promptCard)

        val countdownLabel = TextView(this).apply {
            text = "Ready to record"
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            setTextColor(rose)
            gravity = Gravity.CENTER
            setPadding(0, dp(14), 0, dp(10))
        }
        view.addView(countdownLabel)

        val enrollBtn = Button(this).apply {
            text = "🎙️ START 5-SECOND RECORDING"
            setTextColor(Color.WHITE)
            background = GradientDrawable().apply {
                cornerRadius = dp(24).toFloat()
                setColor(Color.parseColor("#8E24AA"))
            }
        }
        view.addView(enrollBtn, LinearLayout.LayoutParams(MATCH_PARENT, dp(48)))

        val dialog = AlertDialog.Builder(this)
            .setView(view)
            .setNegativeButton("Close", null)
            .create()

        dialog.show()

        enrollBtn.setOnClickListener {
            enrollBtn.isEnabled = false
            countdownLabel.text = "Recording via Pods mic... Speak now!"
            countdownLabel.setTextColor(Color.parseColor("#00E676"))

            thread {
                val sampleRate = VoiceMatcher.SAMPLE_RATE
                val minBuf = AudioRecord.getMinBufferSize(sampleRate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
                val audioRecord = AudioRecord(
                    MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                    sampleRate,
                    AudioFormat.CHANNEL_IN_MONO,
                    AudioFormat.ENCODING_PCM_16BIT,
                    maxOf(minBuf, 8192)
                )

                val durationSeconds = 5
                val totalBytes = sampleRate * 2 * durationSeconds
                val pcmBuffer = ByteArray(totalBytes)

                try {
                    audioRecord.startRecording()
                    var bytesRead = 0
                    val startMs = System.currentTimeMillis()

                    while (bytesRead < totalBytes && System.currentTimeMillis() - startMs < (durationSeconds + 1) * 1000) {
                        val n = audioRecord.read(pcmBuffer, bytesRead, totalBytes - bytesRead)
                        if (n > 0) bytesRead += n
                        val remainingSec = maxOf(1, durationSeconds - ((System.currentTimeMillis() - startMs) / 1000).toInt())
                        runOnUiThread {
                            countdownLabel.text = "Recording... $remainingSec seconds remaining"
                        }
                    }

                    audioRecord.stop()
                    audioRecord.release()

                    runOnUiThread { countdownLabel.text = "Analyzing biometric spectral harmonics..." }

                    val vm = VoiceMatcher(this@MainActivity)
                    val speakerName = prefs.getString("name", "Avishkar") ?: "Avishkar"
                    val result = vm.enroll(pcmBuffer, speakerName)

                    runOnUiThread {
                        enrollBtn.isEnabled = true
                        if (result.success) {
                            countdownLabel.setTextColor(Color.parseColor("#00E676"))
                            countdownLabel.text = "✅ Voiceprint Enrolled!\nMean: ${result.meanF0.toInt()} Hz (${result.minF0.toInt()}-${result.maxF0.toInt()} Hz)\nWake-Word-Free Mode: ACTIVE"
                            enrollBtn.text = "🔄 RE-CALIBRATE VOICEPRINT"
                            prefs.edit().putBoolean("voiceprint_wakeword_free", true).apply()
                            showTalk()
                        } else {
                            countdownLabel.setTextColor(Color.RED)
                            countdownLabel.text = "❌ ${result.errorMessage ?: "Failed to extract voiceprint"}"
                            enrollBtn.text = "RETRY RECORDING"
                        }
                    }
                } catch (e: Exception) {
                    try { audioRecord.release() } catch (_: Exception) {}
                    runOnUiThread {
                        enrollBtn.isEnabled = true
                        countdownLabel.setTextColor(Color.RED)
                        countdownLabel.text = "Error: ${e.message}"
                    }
                }
            }
        }
    }

    private fun handle(name: String) {
        val base = prefs.getString("base", "https://layla.tryvanta.in") ?: "https://layla.tryvanta.in"
        val token = prefs.getString("token", "")?.takeIf { it.isNotBlank() } ?: BuildConfig.DEFAULT_TOKEN
        val wav = rec.stop()
        if (wav == null) { status.text = "TOO SHORT\nHOLD AND SPEAK"; return }
        status.text = "THINKING..."
        orb.speaking = true
        val gen = ++speakGen
        thread {
            val c = LaylaClient(base, token)
            try {
                val said = c.stt(wav)
                if (said.isBlank()) { runOnUiThread { orb.speaking = false; status.text = idle; hint.text = "(no speech heard)" }; return@thread }
                runOnUiThread { hint.text = "You: $said"; hint.setTextColor(Color.WHITE) }
                val (answer, tone) = c.ask("(Speaker: $name) $said")
                if (gen != speakGen) return@thread
                runOnUiThread { status.text = idle; hint.text = "You: $said\n\n$answer" }   // text first, like the web page
                if (answer.isBlank()) { runOnUiThread { orb.speaking = false }; return@thread }
                if (prefs.getBoolean("tv", false)) {
                    try { c.sayOnTv(answer, tone) } catch (_: Exception) {}
                    runOnUiThread { orb.speaking = false }
                } else speakChunks(c, answer, tone, gen)
            } catch (e: Exception) {
                runOnUiThread { orb.speaking = false; status.text = idle; hint.text = "Error: ${e.message}" }
            }
        }
    }

    /** Chunked TTS like the web page: fetch chunk 0 and 1 together, start playing the moment chunk 0 is ready,
     *  and keep fetching i+2 while chunk i plays. */
    private fun speakChunks(c: LaylaClient, text: String, tone: String, gen: Int) {
        val chunks = Speech.split(text)
        val pool = Executors.newFixedThreadPool(2)
        try {
            val fut = arrayOfNulls<Future<ByteArray?>>(chunks.size)
            fun fetch(i: Int) {
                if (i < chunks.size && fut[i] == null)
                    fut[i] = pool.submit<ByteArray?> { try { c.tts(chunks[i], tone) } catch (_: Exception) { null } }
            }
            fetch(0); fetch(1)
            for (i in chunks.indices) {
                val mp3 = fut[i]!!.get()
                if (gen != speakGen) return
                fetch(i + 2)
                if (mp3 != null) playBlocking(mp3, i, gen)
                if (gen != speakGen) return
            }
        } finally {
            pool.shutdownNow()
            if (gen == speakGen) runOnUiThread { orb.speaking = false }
        }
    }

    private fun playBlocking(mp3: ByteArray, i: Int, gen: Int) {
        val done = CountDownLatch(1)
        playLatch = done
        try {
            val f = File(cacheDir, "layla_chunk_${i % 2}.mp3").apply { writeBytes(mp3) }
            val mp = MediaPlayer().apply {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
            }
            player = mp
            mp.setDataSource(f.absolutePath)
            mp.setOnCompletionListener { done.countDown() }
            mp.setOnErrorListener { _, _, _ -> done.countDown(); true }
            mp.prepare()
            if (gen != speakGen) { mp.release(); return }
            mp.start()
            done.await(60, TimeUnit.SECONDS)
            try { mp.release() } catch (_: Exception) {}
        } catch (_: Exception) { }
    }

    private fun stopVoice() {
        speakGen++
        playLatch?.countDown()
        try { player?.release() } catch (_: Exception) {}
        player = null
        if (::orb.isInitialized) orb.speaking = false
    }

    override fun onResume() {
        super.onResume()
        LaylaPodsService.listener = object : LaylaPodsService.PodsEventListener {
            override fun onListeningStateChanged(listening: Boolean, speaking: Boolean) {
                runOnUiThread {
                    if (speaking) {
                        orb.holding = true
                        status.text = "HEARING AVISHKAR...\nLAYLA LISTENING"
                    } else if (listening) {
                        orb.holding = false
                        if (LaylaPodsService.isRunning) {
                            val isEnrolled = VoiceMatcher.isEnrolled(this@MainActivity)
                            val wakeFree = prefs.getBoolean("voiceprint_wakeword_free", true)
                            status.text = if (isEnrolled && wakeFree) "PODS CONNECTED 🎧\nALWAYS LISTENING FOR AVISHKAR" else "PODS CONNECTED 🎧\nALWAYS LISTENING FOR 'LAYLA'"
                        }
                    }
                }
            }

            override fun onUtteranceHeard(said: String) {
                runOnUiThread {
                    hint.text = "You: $said"
                    hint.setTextColor(Color.WHITE)
                    status.text = "THINKING..."
                    orb.speaking = true
                }
            }

            override fun onReplyReady(said: String, answer: String) {
                runOnUiThread {
                    hint.text = "You: $said\n\n$answer"
                    orb.speaking = false
                    if (LaylaPodsService.isRunning) {
                        val isEnrolled = VoiceMatcher.isEnrolled(this@MainActivity)
                        val wakeFree = prefs.getBoolean("voiceprint_wakeword_free", true)
                        status.text = if (isEnrolled && wakeFree) "PODS CONNECTED 🎧\nALWAYS LISTENING FOR AVISHKAR" else "PODS CONNECTED 🎧\nALWAYS LISTENING FOR 'LAYLA'"
                    } else {
                        status.text = idle
                    }
                }
            }

            override fun onError(error: String) {
                runOnUiThread {
                    orb.speaking = false
                    hint.text = "Error: $error"
                    val isEnrolled = VoiceMatcher.isEnrolled(this@MainActivity)
                    val wakeFree = prefs.getBoolean("voiceprint_wakeword_free", true)
                    val podsText = if (isEnrolled && wakeFree) "PODS CONNECTED 🎧\nALWAYS LISTENING FOR AVISHKAR" else "PODS CONNECTED 🎧\nALWAYS LISTENING FOR 'LAYLA'"
                    status.text = if (LaylaPodsService.isRunning) podsText else idle
                }
            }
        }
    }

    override fun onStop() { super.onStop(); stopVoice() }

    override fun onDestroy() {
        super.onDestroy()
        LaylaPodsService.listener = null
    }
}
