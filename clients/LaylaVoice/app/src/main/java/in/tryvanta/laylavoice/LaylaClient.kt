package `in`.tryvanta.laylavoice

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/** Thin client for the Layla brain. Auth is a Bearer device token (same signed token as the web cookie). */
class LaylaClient(private val base: String, private val token: String) {

    private fun postBytes(path: String, body: JSONObject, timeoutMs: Int = 60000): ByteArray {
        val c = URL(base + path).openConnection() as HttpURLConnection
        try {
            c.requestMethod = "POST"
            c.connectTimeout = 15000
            c.readTimeout = timeoutMs
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/json")
            c.setRequestProperty("Authorization", "Bearer $token")
            c.outputStream.use { it.write(body.toString().toByteArray()) }
            val code = c.responseCode
            val raw = (if (code in 200..299) c.inputStream else c.errorStream)?.use { it.readBytes() } ?: ByteArray(0)
            if (code !in 200..299) throw RuntimeException("HTTP $code ${String(raw).take(120)}")
            return raw
        } finally {
            c.disconnect()
        }
    }

    private fun post(path: String, body: JSONObject, timeoutMs: Int = 60000) = String(postBytes(path, body, timeoutMs))

    fun stt(wavB64: String): String = JSONObject(post("/stt", JSONObject().put("audio", wavB64))).optString("text")

    /** Layla answers; the brain speaks the reply on the TV through its own push channel. */
    fun ask(message: String): Pair<String, String> {
        val j = JSONObject(post("/ask", JSONObject().put("message", message)))
        return j.optString("answer") to j.optString("tone", "warm").ifBlank { "warm" }
    }

    /** ElevenLabs voice from the brain, as mp3 bytes, to play on this phone. */
    fun tts(text: String, tone: String): ByteArray = postBytes("/tts", JSONObject().put("text", text).put("tone", tone))

    /** Make the TV page speak and show the text (SSE "say" event). */
    fun sayOnTv(text: String, tone: String) { post("/push", JSONObject().put("type", "say").put("text", text).put("tone", tone)) }
}
