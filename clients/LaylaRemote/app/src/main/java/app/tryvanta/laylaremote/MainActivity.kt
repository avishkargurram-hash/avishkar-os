package app.tryvanta.laylaremote

import android.app.Activity
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import kotlin.math.abs

/**
 * Layla Remote: two joysticks drive the Layla GR robot over MQTT.
 *   left stick  - up/down  = forward/backward
 *   right stick - left/right = turn left/right
 * Stick distance sets the speed. Release = stop. The robot firmware also stops by
 * itself ~1s after the last command, so a dropped link can never run it away.
 */
class MainActivity : Activity(), MqttLink.Listener {

    private val ui = Handler(Looper.getMainLooper())
    private lateinit var link: MqttLink

    private lateinit var linkTv: TextView
    private lateinit var robotTv: TextView
    private lateinit var onBtn: TextView
    private lateinit var fbBtn: TextView
    private lateinit var lrBtn: TextView

    // stick positions, written by the touch thread, read by the ticker (both UI thread)
    private var fy = 0f
    private var rx = 0f

    private var userOn = true
    private var connected = false
    private var invFB = true     // the robot's motors are wired so firmware "backward" drives it FORWARD
    private var invLR = false

    private var lastAction: String? = null
    private var lastSentAt = 0L

    private var robotOnline = false
    private var obstacle = "?"
    private var motor = "?"
    private var distance = ""

    private val ticker = object : Runnable {
        override fun run() {
            tick()
            ui.postDelayed(this, TICK_MS)
        }
    }

    companion object {
        private const val TICK_MS = 150L
        private const val RESEND_MS = 600L
        private const val BURST_MS = 900
        private const val DEAD = 0.25f
        private const val MIN_SPEED = 140
        private const val PREFS = "remote"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val p = getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        invFB = p.getBoolean("invFB", true)
        invLR = p.getBoolean("invLR", false)
        link = MqttLink(this)
        buildUi()
        refreshToggles()
        refreshTelemetry()
    }

    override fun onStart() {
        super.onStart()
        hideSystemUi()
        if (userOn) link.connect()
        ui.post(ticker)
    }

    override fun onStop() {
        ui.removeCallbacks(ticker)
        link.stop()
        link.disconnect()
        fy = 0f; rx = 0f; lastAction = null
        super.onStop()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemUi()
    }

    // ---------------------------------------------------------------- driving

    private fun tick() {
        val mf = abs(fy)
        val mt = abs(rx)
        var action: String? = null
        var mag = 0f
        if (connected && (mf > DEAD || mt > DEAD)) {
            if (mf >= mt) {
                val fwd = fy > 0
                action = if (fwd != invFB) "forward" else "backward"
                mag = mf
            } else {
                val right = rx > 0
                action = if (right != invLR) "right" else "left"
                mag = mt
            }
        }
        val now = SystemClock.uptimeMillis()
        if (action != null) {
            val speed = (MIN_SPEED + ((mag - DEAD) / (1f - DEAD)) * (255 - MIN_SPEED)).toInt().coerceIn(MIN_SPEED, 255)
            if (action != lastAction || now - lastSentAt >= RESEND_MS) {
                link.drive(action, speed, BURST_MS)
                lastAction = action
                lastSentAt = now
            }
        } else if (lastAction != null) {
            lastAction = null
            lastSentAt = now
            link.stop()
            ui.postDelayed({ link.stop() }, 120)   // belt and braces: one lost packet must not leave it running
        }
    }

    // ---------------------------------------------------------------- MQTT callbacks (Paho threads)

    override fun onLink(connected: Boolean, detail: String) {
        runOnUiThread {
            this.connected = connected
            linkTv.text = if (connected) "LINK  connected" else "LINK  $detail"
            linkTv.setTextColor(Color.parseColor(if (connected) "#6BE3A5" else "#FFB4B4"))
            if (!connected) {
                robotOnline = false
                refreshTelemetry()
            }
            onBtn.text = if (userOn) "ON" else "OFF"
        }
    }

    override fun onTopic(suffix: String, payload: String) {
        runOnUiThread {
            when (suffix) {
                "status" -> robotOnline = payload == "online"
                "obstacle/state" -> obstacle = payload
                "distance/state" -> distance = payload
                "motor/state" -> motor = Regex("\"action\"\\s*:\\s*\"(\\w+)\"").find(payload)?.groupValues?.get(1) ?: payload
            }
            refreshTelemetry()
        }
    }

    private fun refreshTelemetry() {
        if (!robotOnline) {
            robotTv.text = "ROBOT  offline"
            robotTv.setTextColor(Color.parseColor("#FFB4B4"))
            return
        }
        val parts = mutableListOf("ROBOT  online", motor.lowercase())
        if (distance.isNotEmpty()) parts.add("$distance cm")
        if (obstacle != "?") parts.add("path " + if (obstacle == "blocked") "BLOCKED" else "clear")
        robotTv.text = parts.joinToString("  ·  ")
        robotTv.setTextColor(Color.parseColor("#6BE3A5"))
    }

    // ---------------------------------------------------------------- UI

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun redButton(label: String, onClick: () -> Unit): TextView {
        val t = TextView(this)
        t.text = label
        t.setTextColor(Color.WHITE)
        t.textSize = 17f
        t.typeface = Typeface.DEFAULT_BOLD
        t.gravity = Gravity.CENTER
        t.setPadding(dp(6), dp(4), dp(6), dp(4))
        t.background = GradientDrawable().apply {
            cornerRadius = dp(14).toFloat()
            setColor(Color.parseColor("#D42B3C"))
        }
        t.setOnClickListener { onClick() }
        t.layoutParams = LinearLayout.LayoutParams(dp(78), dp(54)).apply { topMargin = dp(10) }
        return t
    }

    private fun refreshToggles() {
        fun style(v: TextView, active: Boolean) {
            (v.background as GradientDrawable).apply {
                setColor(Color.parseColor(if (active) "#FF4A5C" else "#7B1822"))
                setStroke(if (active) dp(2) else 0, Color.WHITE)
            }
        }
        fbBtn.text = if (invFB) "⇅ F/B\nflipped" else "⇅ F/B"
        lrBtn.text = if (invLR) "⇄ L/R\nflipped" else "⇄ L/R"
        fbBtn.textSize = 12f
        lrBtn.textSize = 12f
        style(fbBtn, invFB)
        style(lrBtn, invLR)
    }

    private fun buildUi() {
        val root = FrameLayout(this)
        root.background = GradientDrawable(
            GradientDrawable.Orientation.TOP_BOTTOM,
            intArrayOf(Color.parseColor("#0C2A6B"), Color.parseColor("#050F2E"))
        )

        val row = LinearLayout(this)
        row.orientation = LinearLayout.HORIZONTAL
        row.gravity = Gravity.CENTER_VERTICAL
        row.setPadding(dp(16), dp(16), dp(16), dp(16))
        root.addView(row, FrameLayout.LayoutParams(-1, -1))

        // left stick: forward / backward
        val left = JoystickView(this)
        left.onMove = JoystickView.OnMove { _, y -> fy = y }
        row.addView(FrameLayout(this).apply { addView(left, FrameLayout.LayoutParams(-1, -1, Gravity.CENTER)) },
            LinearLayout.LayoutParams(0, -1, 1f))

        // centre: status + buttons
        val centre = LinearLayout(this)
        centre.orientation = LinearLayout.VERTICAL
        centre.gravity = Gravity.CENTER_HORIZONTAL
        val title = TextView(this).apply {
            text = "LAYLA GR"
            setTextColor(Color.WHITE); textSize = 15f; typeface = Typeface.DEFAULT_BOLD; letterSpacing = 0.2f
            gravity = Gravity.CENTER
        }
        linkTv = TextView(this).apply { textSize = 11f; gravity = Gravity.CENTER; text = "LINK  connecting..." }
        robotTv = TextView(this).apply { textSize = 11f; gravity = Gravity.CENTER; text = "ROBOT  offline" }
        centre.addView(title)
        centre.addView(linkTv)
        centre.addView(robotTv)

        onBtn = redButton("ON") {
            userOn = !userOn
            if (userOn) link.connect() else { link.stop(); link.disconnect() }
            onBtn.text = if (userOn) "ON" else "OFF"
        }
        val stopBtn = redButton("■ STOP") {
            fy = 0f; rx = 0f
            link.stop()
        }
        fbBtn = redButton("") {
            invFB = !invFB
            getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean("invFB", invFB).apply()
            refreshToggles()
        }
        lrBtn = redButton("") {
            invLR = !invLR
            getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean("invLR", invLR).apply()
            refreshToggles()
        }
        centre.addView(onBtn)
        centre.addView(stopBtn)
        centre.addView(fbBtn)
        centre.addView(lrBtn)
        row.addView(centre, LinearLayout.LayoutParams(dp(150), -2))

        // right stick: turn left / right
        val right = JoystickView(this)
        right.onMove = JoystickView.OnMove { x, _ -> rx = x }
        row.addView(FrameLayout(this).apply { addView(right, FrameLayout.LayoutParams(-1, -1, Gravity.CENTER)) },
            LinearLayout.LayoutParams(0, -1, 1f))

        setContentView(root)
    }

    @Suppress("DEPRECATION")
    private fun hideSystemUi() {
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                or View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            )
    }
}
