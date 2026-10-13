package `in`.tryvanta.laylaphone

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

/**
 * Setup and status screen. The agent itself has no ongoing UI -- everything
 * real happens in PhoneAgentService's background MQTT loop -- but the Tier-2
 * capabilities need a pile of grants that a manifest declaration alone can
 * never give: runtime permissions, two separate Settings-only toggles
 * (Accessibility and Notification access), a battery-optimisation exemption,
 * and on Funtouch/ColorOS an autostart entry buried in the OEM's own menus.
 *
 * This screen is the single checklist for all of it, so a failure is always
 * visible here rather than showing up later as Layla mysteriously doing
 * nothing.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var container: LinearLayout

    private val runtimePermissions: Array<String>
        get() = buildList {
            add(Manifest.permission.CALL_PHONE)
            add(Manifest.permission.READ_PHONE_STATE)
            add(Manifest.permission.SEND_SMS)
            add(Manifest.permission.READ_SMS)
            add(Manifest.permission.RECEIVE_SMS)
            add(Manifest.permission.READ_CONTACTS)
            add(Manifest.permission.READ_CALL_LOG)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                add(Manifest.permission.ANSWER_PHONE_CALLS)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }.toTypedArray()

    private val permLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { render() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 56, 48, 56)
        }
        setContentView(ScrollView(this).apply { addView(container) })
        startAgent()
    }

    override fun onResume() {
        super.onResume()
        render()
    }

    // -- the checklist -------------------------------------------------------

    private fun render() {
        container.removeAllViews()

        heading("Layla Phone Agent")
        note("Work down the list. Every red item is something Layla can't do yet.")

        val missing = runtimePermissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        row(
            ok = missing.isEmpty(),
            label = "Calls, SMS and contacts",
            detail = if (missing.isEmpty()) "Granted" else "${missing.size} permission(s) still needed",
            button = "Grant permissions",
        ) { permLauncher.launch(runtimePermissions) }

        row(
            ok = LaylaAccessibilityService.isReady(),
            label = "App control (WhatsApp, tapping, typing)",
            detail = if (LaylaAccessibilityService.isReady()) {
                "On"
            } else {
                "Off — WhatsApp sending and app control will not work. " +
                    "Find \"Layla app control\" in the list and turn it on. " +
                    "If the toggle is greyed out, see the note at the bottom."
            },
            button = "Open Accessibility settings",
        ) { safeOpen(Settings.ACTION_ACCESSIBILITY_SETTINGS) }

        row(
            ok = LaylaNotificationListener.isReady(),
            label = "Reading your notifications",
            detail = if (LaylaNotificationListener.isReady()) {
                "On"
            } else {
                "Off — Layla can't tell you who messaged you"
            },
            button = "Open Notification access",
        ) { safeOpen("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS") }

        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        val unrestricted = pm.isIgnoringBatteryOptimizations(packageName)
        row(
            ok = unrestricted,
            label = "Battery: run without restrictions",
            detail = if (unrestricted) {
                "Exempt"
            } else {
                "Restricted — the phone will kill the connection in the background"
            },
            button = "Allow background running",
        ) { requestBatteryExemption() }

        val overlay = Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(this)
        row(
            ok = overlay,
            label = "Show the approval popup over other apps",
            detail = if (overlay) {
                "Allowed"
            } else {
                "Not allowed — approvals will still arrive as a notification, " +
                    "but the full popup won't appear over other apps"
            },
            button = "Allow display over apps",
        ) { requestOverlay() }

        divider()
        heading("On this Vivo phone specifically")
        note(
            "1. Settings → Battery → Background power consumption management → " +
                "Layla Phone Agent → Allow background high power consumption.\n\n" +
                "2. Settings → Apps → Autostart (or \"Auto-start manage\") → turn Layla Phone Agent ON. " +
                "Without this the agent will not come back after a reboot.\n\n" +
                "3. If the Accessibility toggle is greyed out: Settings → Apps → Layla Phone Agent → " +
                "the ⋮ menu in the top corner → \"Allow restricted settings\". Android blocks " +
                "sideloaded apps from accessibility until you do this once.\n\n" +
                "4. Recent apps → swipe down on the Layla card to lock it, so clearing " +
                "recents doesn't kill the agent.",
        )

        divider()
        row(
            ok = true,
            label = "Agent service",
            detail = "Check the notification shade for the live connection status.",
            button = "Restart agent",
        ) { startAgent() }

        note(
            "\nLayla will always ask you here before placing a call or sending an SMS " +
                "or WhatsApp message. Reading contacts, opening apps and checking your " +
                "notifications happen without asking.",
        )
    }

    // -- small UI helpers -----------------------------------------------------

    private fun heading(text: String) {
        container.addView(
            TextView(this).apply {
                this.text = text
                textSize = 21f
                setTextColor(Color.parseColor("#111827"))
                setPadding(0, 8, 0, 12)
            },
        )
    }

    private fun note(text: String) {
        container.addView(
            TextView(this).apply {
                this.text = text
                textSize = 14f
                setTextColor(Color.parseColor("#4B5563"))
                setPadding(0, 0, 0, 16)
            },
        )
    }

    private fun divider() {
        container.addView(
            TextView(this).apply {
                text = ""
                height = 48
            },
        )
    }

    private fun row(
        ok: Boolean,
        label: String,
        detail: String,
        button: String,
        onClick: () -> Unit,
    ) {
        container.addView(
            TextView(this).apply {
                text = (if (ok) "✓  " else "✗  ") + label
                textSize = 16f
                setTextColor(if (ok) Color.parseColor("#15803D") else Color.parseColor("#B91C1C"))
                setPadding(0, 20, 0, 4)
            },
        )
        container.addView(
            TextView(this).apply {
                text = detail
                textSize = 13f
                setTextColor(Color.parseColor("#6B7280"))
            },
        )
        if (!ok || button == "Restart agent") {
            container.addView(
                Button(this).apply {
                    text = button
                    setOnClickListener { onClick() }
                },
            )
        }
    }

    // -- actions ----------------------------------------------------------------

    private fun startAgent() {
        val intent = Intent(this, PhoneAgentService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
    }

    private fun requestBatteryExemption() {
        try {
            startActivity(
                Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
                    .setData(Uri.parse("package:$packageName")),
            )
        } catch (_: Exception) {
            safeOpen(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
        }
    }

    private fun requestOverlay() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return
        try {
            startActivity(
                Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName"),
                ),
            )
        } catch (_: Exception) {
            safeOpen(Settings.ACTION_MANAGE_OVERLAY_PERMISSION)
        }
    }

    /** OEM ROMs sometimes remove a settings screen entirely; fall back to App Info. */
    private fun safeOpen(action: String) {
        try {
            startActivity(Intent(action))
        } catch (_: Exception) {
            try {
                startActivity(
                    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                        .setData(Uri.parse("package:$packageName")),
                )
            } catch (_: Exception) {
            }
        }
    }
}
