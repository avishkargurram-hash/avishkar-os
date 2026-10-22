package `in`.tryvanta.laylawa

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

object WaApi {
    fun post(path: String, body: JSONObject): JSONObject = call("POST", path, body)

    fun get(path: String): JSONObject = call("GET", path, null)

    private fun call(method: String, path: String, body: JSONObject?): JSONObject {
        val c = URL(BuildConfig.WA_BASE.trimEnd('/') + path).openConnection() as HttpURLConnection
        try {
            c.requestMethod = method
            c.connectTimeout = 15_000
            c.readTimeout = 60_000
            c.setRequestProperty("Authorization", "Bearer " + BuildConfig.WA_TOKEN)
            if (body != null) {
                c.doOutput = true
                c.setRequestProperty("Content-Type", "application/json")
                c.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            val code = c.responseCode
            val stream = if (code in 200..299) c.inputStream else c.errorStream
            val text = stream?.bufferedReader()?.use { it.readText() } ?: ""
            if (code !in 200..299) throw RuntimeException("HTTP $code")
            return JSONObject(text)
        } finally {
            c.disconnect()
        }
    }
}

/** Small on-device event log, because there is no adb to read logcat with. */
object WaLog {
    private const val PREFS = "wa_log"
    private const val KEY = "lines"
    private const val MAX = 60

    @Synchronized
    fun add(ctx: Context, line: String) {
        val p = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val stamp = java.text.SimpleDateFormat("dd HH:mm:ss", java.util.Locale.US).format(java.util.Date())
        val lines = (p.getString(KEY, "") ?: "").split("\n").filter { it.isNotBlank() }.toMutableList()
        lines.add("$stamp  ${line.take(160)}")
        p.edit().putString(KEY, lines.takeLast(MAX).joinToString("\n")).apply()
    }

    @Synchronized
    fun read(ctx: Context): String =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, "")?.split("\n")
            ?.reversed()?.joinToString("\n") ?: ""
}
