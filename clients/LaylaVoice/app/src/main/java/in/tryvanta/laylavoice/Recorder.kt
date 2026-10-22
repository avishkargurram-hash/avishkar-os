package `in`.tryvanta.laylavoice

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Base64
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Push-to-talk recorder: 16 kHz mono 16-bit PCM -> base64 WAV (what the brain's /stt expects, 0.3-20 s). */
class Recorder {
    private val rate = 16000
    @Volatile private var running = false
    private var thread: Thread? = null
    private val pcm = ByteArrayOutputStream()

    @SuppressLint("MissingPermission")
    fun start() {
        if (running) return
        pcm.reset()
        val min = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val rec = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, rate,
            AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, maxOf(min, 8192))
        running = true
        thread = Thread {
            val buf = ByteArray(4096)
            rec.startRecording()
            val limit = rate * 2 * 19                    // stay under the 20 s server cap
            while (running && pcm.size() < limit) {
                val n = rec.read(buf, 0, buf.size)
                if (n > 0) pcm.write(buf, 0, n)
            }
            rec.stop(); rec.release()
        }.also { it.start() }
    }

    /** Stops and returns base64 WAV, or null if nothing usable was captured. */
    fun stop(): String? {
        running = false
        thread?.join(2000)
        val data = pcm.toByteArray()
        if (data.size < rate * 2 * 0.4) return null
        val h = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        h.put("RIFF".toByteArray()).putInt(36 + data.size).put("WAVE".toByteArray())
        h.put("fmt ".toByteArray()).putInt(16).putShort(1).putShort(1).putInt(rate).putInt(rate * 2)
        h.putShort(2).putShort(16).put("data".toByteArray()).putInt(data.size)
        return Base64.encodeToString(h.array() + data, Base64.NO_WRAP)
    }
}
