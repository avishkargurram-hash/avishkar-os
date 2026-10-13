package `in`.tryvanta.laylatv

import android.content.Context
import android.media.AudioAttributes
import android.speech.tts.TextToSpeech
import android.util.Log
import java.util.Locale

/** TTS straight to the TV's hardware audio sink (STREAM/USAGE_MEDIA). For
 *  Layla's real ElevenLabs voice instead of on-device TTS, fetch the MP3 from
 *  the brain's /tts and play via MediaPlayer with the same AudioAttributes.
 *
 *  The TextToSpeech constructor initialises ASYNCHRONOUSLY: its listener
 *  fires some time after the call returns. The original version called
 *  speak() on the very next line, so the FIRST utterance after a cold start
 *  (or after Android recycled the service) was always dropped silently --
 *  found in the 2026-10-06 audit. Anything spoken before the engine is ready
 *  is now buffered and flushed from the init callback instead. */
object LaylaTts {
    private const val TAG = "LaylaTts"
    private const val MAX_PENDING = 8

    private var tts: TextToSpeech? = null
    private var isReady = false
    private var isDead = false          // engine reported init failure
    private val pending = ArrayDeque<String>()

    fun speak(ctx: Context, text: String) {
        if (text.isBlank()) return
        synchronized(this) {
            if (isDead) return
            if (isReady) {
                tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "layla")
                return
            }
            // Not ready yet: buffer, and kick off init if this is the first call.
            while (pending.size >= MAX_PENDING) pending.removeFirst()
            pending.addLast(text)
            if (tts == null) {
                tts = TextToSpeech(ctx.applicationContext) { status -> onInit(status) }
            }
        }
    }

    private fun onInit(status: Int) {
        synchronized(this) {
            if (status != TextToSpeech.SUCCESS) {
                Log.e(TAG, "TTS init failed (status=$status); dropping ${pending.size} queued")
                isDead = true
                pending.clear()
                tts = null
                return
            }
            tts?.language = Locale.UK
            tts?.setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build()
            )
            isReady = true
            // Flush whatever arrived while the engine was still starting. The
            // first one flushes any stale queue, the rest append in order.
            var first = true
            while (pending.isNotEmpty()) {
                val next = pending.removeFirst()
                val mode = if (first) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD
                tts?.speak(next, mode, null, "layla")
                first = false
            }
        }
    }

    /** Called from the service's onDestroy so a recycled service re-inits
     *  cleanly instead of speaking into a shut-down engine. */
    fun shutdown() {
        synchronized(this) {
            runCatching { tts?.stop(); tts?.shutdown() }
            tts = null; isReady = false; isDead = false; pending.clear()
        }
    }
}
