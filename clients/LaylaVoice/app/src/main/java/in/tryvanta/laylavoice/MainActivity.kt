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
import android.media.MediaPlayer
import android.os.Bundle
import android.text.InputType
import android.util.TypedValue
import android.view.Gravity
import android.view.MotionEvent
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import java.io.File
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
    private var player: MediaPlayer? = null
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

        hint = label("Hello $name. Try: \"Turn up the volume\"", 15f, dim)
        root.addView(hint, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT).apply { topMargin = dp(18) })
        setContentView(root)

        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.RECORD_AUDIO), 1)

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

    private fun showSettings() {
        val pad = dp(16)
        val col = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad, pad, 0) }
        fun field(h: String, v: String) = EditText(this).apply { hint = h; setText(v); setSingleLine() }.also { col.addView(it) }
        val n = field("Your name", prefs.getString("name", "") ?: "")
        val b = field("Brain URL", prefs.getString("base", "https://layla.tryvanta.in") ?: "")
        val t = field("Device token", prefs.getString("token", "")?.takeIf { it.isNotBlank() } ?: BuildConfig.DEFAULT_TOKEN)
        AlertDialog.Builder(this).setTitle("Settings").setView(col)
            .setPositiveButton("Save") { _, _ ->
                prefs.edit().putString("name", n.text.toString().trim()).putString("base", b.text.toString().trim())
                    .putString("token", t.text.toString().trim()).apply()
                if (prefs.getString("name", "").isNullOrBlank()) showWelcome() else showTalk()
            }.setNegativeButton("Cancel", null).show()
    }

    private fun handle(name: String) {
        val base = prefs.getString("base", "https://layla.tryvanta.in") ?: "https://layla.tryvanta.in"
        val token = prefs.getString("token", "")?.takeIf { it.isNotBlank() } ?: BuildConfig.DEFAULT_TOKEN
        val wav = rec.stop()
        if (wav == null) { status.text = "TOO SHORT\nHOLD AND SPEAK"; return }
        status.text = "THINKING..."
        thread {
            var said = ""
            var audio: ByteArray? = null
            val msg: String = try {
                val c = LaylaClient(base, token)
                said = c.stt(wav)
                if (said.isBlank()) "(no speech heard)" else {
                    val (answer, tone) = c.ask("(Speaker: $name) $said")
                    if (answer.isNotBlank()) {
                        try {
                            if (prefs.getBoolean("tv", false)) c.sayOnTv(answer, tone) else audio = c.tts(answer, tone)
                        } catch (_: Exception) { /* text still shows; voice is best-effort */ }
                    }
                    answer
                }
            } catch (e: Exception) { "Error: ${e.message}" }
            runOnUiThread {
                status.text = idle
                hint.text = if (said.isBlank()) msg else "You: $said\n\n$msg"
                hint.setTextColor(Color.WHITE)
                audio?.let { playVoice(it) }
            }
        }
    }

    private fun playVoice(mp3: ByteArray) {
        stopVoice()
        try {
            val f = File(cacheDir, "layla_reply.mp3").apply { writeBytes(mp3) }
            player = MediaPlayer().apply {
                setDataSource(f.absolutePath)
                setOnCompletionListener { orb.speaking = false }
                setOnErrorListener { _, _, _ -> orb.speaking = false; true }
                prepare(); start()
            }
            orb.speaking = true
        } catch (_: Exception) { orb.speaking = false }
    }

    private fun stopVoice() {
        try { player?.release() } catch (_: Exception) {}
        player = null
        if (::orb.isInitialized) orb.speaking = false
    }

    override fun onStop() { super.onStop(); stopVoice() }
}
