package `in`.tryvanta.laylaphone

import android.content.Intent
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * The approval screen: nothing that reaches the outside world (a call, an
 * SMS, a WhatsApp message) happens until the owner physically taps Allow
 * here. This is the real tap-to-confirm gate the Tier-1 agent was explicitly
 * waiting for before any of these permissions could be justified.
 *
 * Deliberately dumb: it renders a description and reports one of two
 * outcomes back to PhoneAgentService. It never performs the action itself,
 * so there is exactly one place in the app where a sensitive action can be
 * triggered, and it is behind this screen's answer.
 */
class ConfirmActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_ID = "req_id"
        const val EXTRA_TITLE = "req_title"
        const val EXTRA_BODY = "req_body"
    }

    private var answered = false
    private var reqId: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        showOverLockScreen()

        reqId = intent.getStringExtra(EXTRA_ID)
        val title = intent.getStringExtra(EXTRA_TITLE) ?: "Layla wants to do something"
        val body = intent.getStringExtra(EXTRA_BODY).orEmpty()

        setContentView(buildUi(title, body))
        setFinishOnTouchOutside(false)
    }

    private fun buildUi(title: String, body: String): LinearLayout {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(56, 56, 56, 40)
        }
        root.addView(
            TextView(this).apply {
                text = "Layla is asking"
                textSize = 13f
                setTextColor(Color.parseColor("#6B7280"))
            },
        )
        root.addView(
            TextView(this).apply {
                text = title
                textSize = 20f
                setPadding(0, 16, 0, 0)
                setTextColor(Color.parseColor("#111827"))
            },
        )
        if (body.isNotBlank()) {
            root.addView(
                TextView(this).apply {
                    text = body
                    textSize = 16f
                    setPadding(0, 20, 0, 0)
                    setTextColor(Color.parseColor("#374151"))
                },
            )
        }

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
            setPadding(0, 40, 0, 0)
        }
        row.addView(
            Button(this).apply {
                text = "Deny"
                setOnClickListener { answer(false) }
            },
        )
        row.addView(
            Button(this).apply {
                text = "Allow"
                setOnClickListener { answer(true) }
            },
        )
        root.addView(row)
        return root
    }

    private fun showOverLockScreen() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                    WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON,
            )
        }
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    private fun answer(approved: Boolean) {
        if (answered) return
        answered = true
        val id = reqId
        if (id != null) {
            startService(
                Intent(this, PhoneAgentService::class.java).apply {
                    action = if (approved) PhoneAgentService.ACTION_APPROVE else PhoneAgentService.ACTION_DENY
                    putExtra(EXTRA_ID, id)
                },
            )
        }
        finish()
    }

    /** Backing out of the screen is a refusal, never a silent approval. */
    override fun onDestroy() {
        if (!answered) answer(false)
        super.onDestroy()
    }
}
