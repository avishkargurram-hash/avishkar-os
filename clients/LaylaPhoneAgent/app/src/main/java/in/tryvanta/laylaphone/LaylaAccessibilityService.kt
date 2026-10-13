package `in`.tryvanta.laylaphone

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import java.net.URLEncoder

/**
 * Layla's app-control layer.
 *
 * Android exposes no API that lets one app tap or type inside another --
 * an AccessibilityService is the only mechanism, which is precisely why the
 * original Tier-1 agent could launch WhatsApp but never send anything in it.
 *
 * Everything here is read-or-drive-the-UI only. The decision about *whether*
 * an action is allowed to happen at all lives in PhoneAgentService's
 * approval gate, never here -- this class is the hands, not the judgement.
 */
class LaylaAccessibilityService : AccessibilityService() {

    companion object {
        @Volatile
        private var instance: LaylaAccessibilityService? = null

        /** Null whenever the owner hasn't enabled the service in Settings. */
        fun get(): LaylaAccessibilityService? = instance

        fun isReady(): Boolean = instance != null

        private const val MAX_NODES = 400
        private const val MAX_DEPTH = 40
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Intentionally empty: this service is driven on demand by Layla's
        // commands rather than reacting to the event stream. Subscribing to
        // events at all is only what keeps the service bound and alive.
    }

    override fun onInterrupt() {}

    // -- generic screen reading ------------------------------------------

    /** Visible text on the current screen, deduplicated, in traversal order. */
    fun screenText(): List<String> {
        val root = rootInActiveWindow ?: return emptyList()
        val seen = LinkedHashSet<String>()
        walk(root) { n ->
            val t = (n.text ?: n.contentDescription)?.toString()?.trim()
            if (!t.isNullOrEmpty() && t.length <= 300) seen.add(t)
            seen.size < MAX_NODES
        }
        return seen.toList()
    }

    fun currentPackage(): String? = rootInActiveWindow?.packageName?.toString()

    // -- generic UI driving ----------------------------------------------

    /** Clicks the first node whose text or description matches [label]. */
    fun tapText(label: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val needle = label.trim().lowercase()
        var target: AccessibilityNodeInfo? = null
        walk(root) { n ->
            val hay = listOfNotNull(n.text?.toString(), n.contentDescription?.toString())
                .joinToString(" ").lowercase()
            if (hay.isNotEmpty() && hay.contains(needle)) {
                target = n
                false
            } else {
                true
            }
        }
        return target?.let { clickable(it)?.performAction(AccessibilityNodeInfo.ACTION_CLICK) } ?: false
    }

    /** Types into the currently focused editable field. */
    fun typeText(text: String): Boolean {
        val root = rootInActiveWindow ?: return false
        var field = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
        if (field == null || !field.isEditable) {
            walk(root) { n ->
                if (n.isEditable) {
                    field = n
                    false
                } else {
                    true
                }
            }
        }
        val f = field ?: return false
        f.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return f.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    fun globalAction(name: String): Boolean {
        val action = when (name.trim().lowercase()) {
            "back" -> GLOBAL_ACTION_BACK
            "home" -> GLOBAL_ACTION_HOME
            "recents", "recent", "overview" -> GLOBAL_ACTION_RECENTS
            "notifications", "shade" -> GLOBAL_ACTION_NOTIFICATIONS
            "quick_settings", "settings_panel" -> GLOBAL_ACTION_QUICK_SETTINGS
            "lock", "lock_screen" -> GLOBAL_ACTION_LOCK_SCREEN
            else -> return false
        }
        return performGlobalAction(action)
    }

    fun scroll(direction: String): Boolean {
        val root = rootInActiveWindow ?: return false
        val action = if (direction.trim().lowercase() == "up") {
            AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
        } else {
            AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
        }
        var scroller: AccessibilityNodeInfo? = null
        walk(root) { n ->
            if (n.isScrollable) {
                scroller = n
                false
            } else {
                true
            }
        }
        return scroller?.performAction(action) ?: false
    }

    // -- WhatsApp ---------------------------------------------------------

    /**
     * Sends a WhatsApp message to [number] (digits, with country code).
     *
     * Deep-links straight into the chat with the text pre-filled, then taps
     * WhatsApp's own send button. Deliberately NOT a blind
     * open-search-type-send sequence through the UI: the deep link puts the
     * message in the right chat atomically, so a slow render or a mistyped
     * search can never land the text in somebody else's conversation.
     */
    fun sendWhatsApp(number: String, message: String): String {
        val digits = number.filter { it.isDigit() }
        if (digits.isEmpty()) return "ERR:no usable phone number"

        val url = "https://api.whatsapp.com/send?phone=$digits&text=" +
            URLEncoder.encode(message, "UTF-8")
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
            setPackage("com.whatsapp")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        try {
            startActivity(intent)
        } catch (e: Exception) {
            return "ERR:could not open WhatsApp (${e.message})"
        }

        // Wait for the chat to actually render its send button before tapping.
        val deadline = System.currentTimeMillis() + 12_000
        var sendBtn: AccessibilityNodeInfo? = null
        while (System.currentTimeMillis() < deadline) {
            Thread.sleep(400)
            val root = rootInActiveWindow ?: continue
            if (root.packageName?.toString() != "com.whatsapp") continue

            if (screenMentions(root, "invalid", "not on whatsapp", "isn't on whatsapp")) {
                return "ERR:that number is not on WhatsApp"
            }
            sendBtn = findSendButton(root)
            if (sendBtn != null) break
        }

        val btn = sendBtn ?: return "ERR:WhatsApp did not open the chat in time — " +
            "check the number, or that WhatsApp isn't showing a login/update screen"

        val clicked = clickable(btn)?.performAction(AccessibilityNodeInfo.ACTION_CLICK) ?: false
        if (!clicked) return "ERR:found WhatsApp's send button but could not tap it"

        Thread.sleep(900)
        return "OK:sent to $digits"
    }

    private fun findSendButton(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        // Stable resource id first -- survives UI language changes.
        root.findAccessibilityNodeInfosByViewId("com.whatsapp:id/send")
            ?.firstOrNull { it.isVisibleToUser }
            ?.let { return it }

        var found: AccessibilityNodeInfo? = null
        walk(root) { n ->
            val desc = n.contentDescription?.toString()?.trim()?.lowercase()
            if (n.isVisibleToUser && (desc == "send" || desc == "send message")) {
                found = n
                false
            } else {
                true
            }
        }
        return found
    }

    private fun screenMentions(root: AccessibilityNodeInfo, vararg needles: String): Boolean {
        var hit = false
        walk(root) { n ->
            val t = (n.text ?: n.contentDescription)?.toString()?.lowercase()
            if (t != null && needles.any { t.contains(it) }) {
                hit = true
                false
            } else {
                true
            }
        }
        return hit
    }

    // -- helpers ----------------------------------------------------------

    /** Nearest ancestor (or self) that will actually accept a click. */
    private fun clickable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        var n: AccessibilityNodeInfo? = node
        var hops = 0
        while (n != null && hops < 12) {
            if (n.isClickable && n.isEnabled) return n
            n = n.parent
            hops++
        }
        return null
    }

    /** Depth-first walk; [visit] returns false to stop the traversal early. */
    private fun walk(root: AccessibilityNodeInfo, visit: (AccessibilityNodeInfo) -> Boolean) {
        val stack = ArrayDeque<Pair<AccessibilityNodeInfo, Int>>()
        stack.addLast(root to 0)
        var budget = 3000
        while (stack.isNotEmpty() && budget-- > 0) {
            val (node, depth) = stack.removeLast()
            if (!visit(node)) return
            if (depth >= MAX_DEPTH) continue
            for (i in node.childCount - 1 downTo 0) {
                node.getChild(i)?.let { stack.addLast(it to depth + 1) }
            }
        }
    }
}
