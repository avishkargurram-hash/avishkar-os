package `in`.tryvanta.laylawa

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.core.app.NotificationManagerCompat

class MainActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var log: TextView
    private val ui = Handler(Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val pad = (16 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
        }
        status = TextView(this).apply { textSize = 16f }
        root.addView(status)
        root.addView(button("1. Allow notification access") {
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        })
        root.addView(button("2. Exempt from battery optimisation") {
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        })
        root.addView(button("3. Test connection to Layla server") { testConnection() })
        log = TextView(this).apply { textSize = 12f; typeface = android.graphics.Typeface.MONOSPACE }
        root.addView(ScrollView(this).apply { addView(log) },
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)
    }

    private fun button(label: String, onClick: () -> Unit) = Button(this).apply {
        text = label
        setOnClickListener { onClick() }
    }

    override fun onResume() {
        super.onResume()
        refresh()
    }

    private fun refresh(serverLine: String? = null) {
        val access = NotificationManagerCompat.getEnabledListenerPackages(this).contains(packageName)
        val battery = (getSystemService(POWER_SERVICE) as PowerManager).isIgnoringBatteryOptimizations(packageName)
        status.text = buildString {
            append("Notification access: ").append(if (access) "ON" else "OFF - tap 1").append('\n')
            append("Battery exemption: ").append(if (battery) "ON" else "OFF - tap 2").append('\n')
            append("Server: ").append(serverLine ?: "not tested - tap 3")
        }
        log.text = WaLog.read(this)
    }

    private fun testConnection() {
        refresh("testing...")
        Thread {
            val line = try {
                val r = WaApi.get("/ping")
                if (r.optBoolean("enabled")) "reachable, auto-reply is ON" else "reachable, auto-reply is OFF (send /wa on in Telegram)"
            } catch (e: Throwable) {
                "FAILED: ${e.message}"
            }
            ui.post { refresh(line) }
        }.start()
    }
}
