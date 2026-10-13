package `in`.tryvanta.laylaphone

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONArray
import org.json.JSONObject

/**
 * Keeps a small rolling window of what has actually arrived on the phone, so
 * Layla can answer "did anyone message me?" without screen-scraping each app.
 *
 * This is read-only and in-memory only -- nothing is written to disk and
 * nothing leaves the device unless Layla explicitly asks for the list.
 */
class LaylaNotificationListener : NotificationListenerService() {

    data class Item(
        val pkg: String,
        val app: String,
        val title: String,
        val text: String,
        val whenMs: Long,
    )

    companion object {
        private const val CAPACITY = 60

        @Volatile
        private var connected = false
        private val recent = ArrayDeque<Item>()

        fun isReady(): Boolean = connected

        fun snapshot(limit: Int, pkgFilter: String?): JSONArray {
            val out = JSONArray()
            synchronized(recent) {
                recent.reversed()
                    .asSequence()
                    .filter { pkgFilter == null || it.pkg.contains(pkgFilter, ignoreCase = true) ||
                        it.app.contains(pkgFilter, ignoreCase = true) }
                    .take(limit.coerceIn(1, CAPACITY))
                    .forEach { i ->
                        out.put(
                            JSONObject()
                                .put("app", i.app)
                                .put("package", i.pkg)
                                .put("title", i.title)
                                .put("text", i.text)
                                .put("at", i.whenMs),
                        )
                    }
            }
            return out
        }

        private fun push(item: Item) {
            synchronized(recent) {
                // Messaging apps re-post the same notification as a thread
                // grows; keep the newest version rather than a duplicate per
                // keystroke on the sender's side.
                recent.removeAll { it.pkg == item.pkg && it.title == item.title && it.text == item.text }
                recent.addLast(item)
                while (recent.size > CAPACITY) recent.removeFirst()
            }
        }
    }

    override fun onListenerConnected() {
        connected = true
    }

    override fun onListenerDisconnected() {
        connected = false
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        val n = sbn ?: return
        if (n.packageName == packageName) return // our own status notification

        val extras = n.notification?.extras ?: return
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()?.trim().orEmpty()
        val text = (
            extras.getCharSequence(Notification.EXTRA_TEXT)
                ?: extras.getCharSequence(Notification.EXTRA_BIG_TEXT)
            )?.toString()?.trim().orEmpty()
        if (title.isEmpty() && text.isEmpty()) return

        push(
            Item(
                pkg = n.packageName,
                app = appLabel(n.packageName),
                title = title,
                text = text.take(500),
                whenMs = if (n.postTime > 0) n.postTime else System.currentTimeMillis(),
            ),
        )
    }

    private fun appLabel(pkg: String): String = try {
        val pm = packageManager
        pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
    } catch (_: Exception) {
        pkg
    }
}
