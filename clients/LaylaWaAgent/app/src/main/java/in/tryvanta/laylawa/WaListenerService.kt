package `in`.tryvanta.laylawa

import android.app.Notification
import android.app.PendingIntent
import android.content.ComponentName
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import androidx.core.app.NotificationCompat
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.ScheduledThreadPoolExecutor
import java.util.concurrent.TimeUnit

/**
 * Watches WhatsApp notifications, asks the server what (if anything) to reply,
 * waits the server-chosen human-like delay, re-checks the chat is still unread,
 * asks the server for the final go-ahead (kill switch), then sends through the
 * notification's own inline-reply action. Every step fails closed.
 */
class WaListenerService : NotificationListenerService() {

    private class Slot(var key: String = "") {
        var lastId: String = ""
        var rid: String? = null
        var future: ScheduledFuture<*>? = null
    }

    private val exec = ScheduledThreadPoolExecutor(3)
    private val slots = HashMap<String, Slot>()

    override fun onListenerConnected() {
        WaLog.add(this, "listener connected")
    }

    override fun onListenerDisconnected() {
        WaLog.add(this, "listener disconnected, rebinding")
        if (Build.VERSION.SDK_INT >= 24) {
            requestRebind(ComponentName(this, WaListenerService::class.java))
        }
    }

    override fun onDestroy() {
        exec.shutdownNow()
        super.onDestroy()
    }

    // ---- incoming ---------------------------------------------------------
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        try {
            handlePosted(sbn)
        } catch (e: Throwable) {
            WaLog.add(this, "error: ${e.javaClass.simpleName} ${e.message}")
        }
    }

    private fun handlePosted(sbn: StatusBarNotification) {
        if (sbn.packageName !in WA_PACKAGES) return
        val n = sbn.notification
        if (n.flags and Notification.FLAG_GROUP_SUMMARY != 0) return
        val style = NotificationCompat.MessagingStyle.extractMessagingStyleFromNotification(n)
        if (style == null) {
            WaLog.add(this, "ignored: no MessagingStyle")
            return
        }
        val msgs = style.messages
        val last = msgs.lastOrNull() ?: return
        if (isSelf(last, style)) return

        val text = last.text?.toString()?.trim().orEmpty()
        if (text.isEmpty() || NON_TEXT.containsMatchIn(text)) {
            WaLog.add(this, "skipped non-text message")
            return
        }

        val isGroup = style.isGroupConversation
        val rawTitle = style.conversationTitle?.toString()
            ?: n.extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: return
        val title = rawTitle.replace(Regex("\\s*\\(\\d+ messages?\\)$"), "").trim()
        if (title.isEmpty()) return
        val conv = (if (isGroup) "g:" else "c:") + title
        val senderName = last.person?.name?.toString() ?: title
        val known = last.person?.uri?.startsWith("content://com.android.contacts") == true
        val id = sha1("$conv|${last.timestamp}|$text")

        val history = JSONArray()
        for (m in msgs.dropLast(1).takeLast(8)) {
            history.put(
                JSONObject().put("sender", m.person?.name?.toString() ?: title)
                    .put("text", m.text?.toString() ?: "").put("self", isSelf(m, style))
            )
        }
        val body = JSONObject().put("id", id).put("conv", conv).put("title", title)
            .put("sender", senderName).put("is_group", isGroup).put("text", text).put("history", history)
        if (known) body.put("known", true)

        synchronized(slots) {
            val s = slots.getOrPut(conv) { Slot() }
            if (s.lastId == id) return
            s.future?.cancel(false)
            s.rid?.let { old -> exec.execute { cancelOnServer(old) } }
            s.rid = null
            s.lastId = id
            s.key = sbn.key
            s.future = exec.schedule({ decide(conv, id, body, last.timestamp) }, DEBOUNCE_MS, TimeUnit.MILLISECONDS)
        }
    }

    private fun isSelf(m: NotificationCompat.MessagingStyle.Message, style: NotificationCompat.MessagingStyle): Boolean {
        val p = m.person ?: return true
        val me = style.user
        if (p.key != null && me.key != null) return p.key == me.key
        return p.name?.toString() == me.name?.toString()
    }

    // ---- step 1: ask the server ------------------------------------------
    private fun decide(conv: String, id: String, body: JSONObject, msgTs: Long) {
        val title = body.optString("title")
        try {
            val r = WaApi.post("/message", body)
            if (r.optString("action") != "reply") {
                WaLog.add(this, "no reply to $title: ${r.optString("reason")}")
                return
            }
            val rid = r.getString("id")
            val delay = r.optLong("delay_ms", 0)
            synchronized(slots) {
                val s = slots[conv]
                if (s == null || s.lastId != id) {
                    exec.execute { cancelOnServer(rid) }
                    return
                }
                s.rid = rid
                WaLog.add(this, "reply queued for $title, sending in ${delay / 1000}s")
                s.future = exec.schedule({ commit(conv, rid, msgTs, title) }, delay, TimeUnit.MILLISECONDS)
            }
        } catch (e: Throwable) {
            WaLog.add(this, "server error for $title: ${e.message}")
        }
    }

    // ---- step 2: still unread? kill switch? send --------------------------
    private fun commit(conv: String, rid: String, msgTs: Long, title: String) {
        try {
            val key = synchronized(slots) { slots[conv]?.key }
            val sbn = try {
                activeNotifications?.firstOrNull { it.key == key }
            } catch (e: SecurityException) {
                null
            }
            if (sbn == null) {
                cancelOnServer(rid, "chat opened or notification dismissed")
                WaLog.add(this, "cancelled for $title: already read")
                return
            }
            val style = NotificationCompat.MessagingStyle.extractMessagingStyleFromNotification(sbn.notification)
            val last = style?.messages?.lastOrNull()
            if (last == null || last.timestamp != msgTs || isSelf(last, style)) {
                cancelOnServer(rid, "newer activity in chat")
                WaLog.add(this, "cancelled for $title: newer activity")
                return
            }
            val found = findReplyAction(sbn.notification)
            if (found == null) {
                cancelOnServer(rid, "no reply action")
                WaLog.add(this, "cannot reply to $title: no inline reply action")
                return
            }

            val c = WaApi.post("/commit", JSONObject().put("id", rid))
            if (!c.optBoolean("send")) {
                WaLog.add(this, "blocked for $title: ${c.optString("reason")}")
                return
            }
            val text = c.getString("text")
            try {
                fire(found.first, found.second, text)
            } catch (e: Throwable) {
                WaApi.post("/ack", JSONObject().put("id", rid).put("ok", false).put("error", e.message ?: "send failed"))
                WaLog.add(this, "send FAILED to $title: ${e.message}")
                return
            }
            WaApi.post("/ack", JSONObject().put("id", rid).put("ok", true))
            WaLog.add(this, "sent to $title")
        } catch (e: Throwable) {
            WaLog.add(this, "commit error for $title: ${e.message}")
        } finally {
            synchronized(slots) { if (slots[conv]?.rid == rid) slots[conv]?.rid = null }
        }
    }

    private fun findReplyAction(n: Notification): Pair<Notification.Action, android.app.RemoteInput>? {
        var fallback: Pair<Notification.Action, android.app.RemoteInput>? = null
        for (a in n.actions ?: return null) {
            val ris = a.remoteInputs
            if (ris.isNullOrEmpty()) continue
            if (Build.VERSION.SDK_INT >= 28 && a.semanticAction == Notification.Action.SEMANTIC_ACTION_REPLY) return a to ris[0]
            if (a.title?.toString()?.contains("reply", ignoreCase = true) == true) return a to ris[0]
            if (fallback == null) fallback = a to ris[0]
        }
        return fallback
    }

    private fun fire(action: Notification.Action, ri: android.app.RemoteInput, text: String) {
        val intent = Intent()
        val results = Bundle()
        results.putCharSequence(ri.resultKey, text)
        android.app.RemoteInput.addResultsToIntent(arrayOf(ri), intent, results)
        try {
            action.actionIntent.send(this, 0, intent)
        } catch (e: PendingIntent.CanceledException) {
            throw RuntimeException("reply action no longer valid")
        }
    }

    // ---- cancel paths ----------------------------------------------------
    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        if (sbn.packageName !in WA_PACKAGES) return
        try {
            val rids = ArrayList<String>()
            synchronized(slots) {
                for (s in slots.values) {
                    if (s.key == sbn.key && s.rid != null) {
                        s.future?.cancel(false)
                        rids.add(s.rid!!)
                        s.rid = null
                    }
                }
            }
            for (r in rids) exec.execute {
                cancelOnServer(r, "notification removed")
                WaLog.add(this, "cancelled pending reply: chat was opened or dismissed")
            }
        } catch (e: Throwable) {
            WaLog.add(this, "error: ${e.message}")
        }
    }

    private fun cancelOnServer(rid: String, why: String = "superseded") {
        try {
            WaApi.post("/cancel", JSONObject().put("id", rid).put("why", why))
        } catch (_: Throwable) {
        }
    }

    private fun sha1(s: String): String =
        MessageDigest.getInstance("SHA-1").digest(s.toByteArray()).joinToString("") { "%02x".format(it) }

    companion object {
        val WA_PACKAGES = setOf("com.whatsapp", "com.whatsapp.w4b")   // WhatsApp + WhatsApp Business (owner, 2026-10-22)
        const val DEBOUNCE_MS = 3000L
        private val NON_TEXT = Regex(
            "^(?:[\\u200e\\u200f\\s]*)(?:[\\uD83D\\uD83C][\\uDC00-\\uDFFF]|\\u260E|\\u2709)?\\s*" +
                "(?:photo|video|voice message|audio|document|sticker|gif|contact|location|live location|" +
                "missed (?:voice|video) call|this message was deleted|you deleted this message|" +
                "waiting for this message)\\b",
            RegexOption.IGNORE_CASE
        )
    }
}
