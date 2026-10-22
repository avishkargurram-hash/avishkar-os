package `in`.tryvanta.laylavoice

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Base64
import android.util.Log
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.sqrt

/**
 * Continuous background audio listener optimized for Bluetooth Earpods.
 *
 * Implements Energy-based VAD (Voice Activity Detection), pre-speech buffering,
 * and passes captured utterances to [VoiceMatcher] to ensure only Avishkar's voice
 * triggers speech recognition.
 */
class ContinuousPodsRecorder(
    private val context: Context,
    private val onUtteranceCaptured: (wavB64: String) -> Unit,
    private val onListeningStateChanged: ((isListening: Boolean, isSpeaking: Boolean) -> Unit)? = null
) {
    private val rate = 16000
    private val voiceMatcher = VoiceMatcher(context)

    @Volatile private var isRunning = false
    @Volatile private var isPaused = false
    private var workerThread: Thread? = null

    companion object {
        private const val TAG = "LaylaPodsRec"
        private const val FRAME_SAMPLES = 512          // 32 ms per frame
        private const val FRAME_BYTES = FRAME_SAMPLES * 2
        private const val SPEECH_TRIGGER_RMS = 350.0  // RMS required to begin speech
        private const val SILENCE_FLOOR_RMS = 250.0   // RMS considered ambient silence
        private const val SILENCE_FRAMES_LIMIT = 24    // ~768 ms silence to end utterance
        private const val MIN_UTTERANCE_BYTES = 16000 * 2 * 0.4  // at least 400 ms
        private const val MAX_UTTERANCE_BYTES = 16000 * 2 * 15   // cap at 15 seconds
        private const val PRE_SPEECH_FRAMES = 8       // ~250 ms pre-speech buffer
    }

    @SuppressLint("MissingPermission")
    fun start() {
        if (isRunning) return
        isRunning = true
        isPaused = false

        workerThread = Thread({
            val minBuf = AudioRecord.getMinBufferSize(rate, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
            val audioRecord = AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                rate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                maxOf(minBuf, 8192)
            )

            try {
                audioRecord.startRecording()
                Log.i(TAG, "AudioRecord started for continuous listening")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start AudioRecord: ${e.message}", e)
                isRunning = false
                return@Thread
            }

            val frameBuf = ByteArray(FRAME_BYTES)
            val preSpeechRing = ArrayDeque<ByteArray>(PRE_SPEECH_FRAMES)
            val utteranceStream = ByteArrayOutputStream()
            var isRecordingSpeech = false
            var silenceFrames = 0

            onListeningStateChanged?.invoke(true, false)

            while (isRunning) {
                if (isPaused) {
                    try { Thread.sleep(50) } catch (_: InterruptedException) {}
                    continue
                }

                var readBytes = 0
                while (readBytes < FRAME_BYTES && isRunning && !isPaused) {
                    val n = audioRecord.read(frameBuf, readBytes, FRAME_BYTES - readBytes)
                    if (n > 0) readBytes += n else break
                }
                if (readBytes < FRAME_BYTES) continue

                // Compute RMS energy
                var sumSq = 0.0
                for (i in 0 until FRAME_SAMPLES) {
                    val b0 = frameBuf[i * 2].toInt() and 0xFF
                    val b1 = frameBuf[i * 2 + 1].toInt()
                    val s = ((b1 shl 8) or b0).toDouble()
                    sumSq += s * s
                }
                val rms = sqrt(sumSq / FRAME_SAMPLES)

                if (!isRecordingSpeech) {
                    // Maintain pre-speech ring buffer
                    if (preSpeechRing.size >= PRE_SPEECH_FRAMES) preSpeechRing.removeFirst()
                    preSpeechRing.addLast(frameBuf.clone())

                    if (rms >= SPEECH_TRIGGER_RMS) {
                        isRecordingSpeech = true
                        silenceFrames = 0
                        utteranceStream.reset()
                        for (prev in preSpeechRing) utteranceStream.write(prev)
                        utteranceStream.write(frameBuf)
                        Log.d(TAG, "Speech start detected (RMS: ${rms.toInt()})")
                        onListeningStateChanged?.invoke(true, true)
                    }
                } else {
                    utteranceStream.write(frameBuf)
                    if (rms < SILENCE_FLOOR_RMS) {
                        silenceFrames++
                    } else {
                        silenceFrames = 0
                    }

                    val reachedSilence = silenceFrames >= SILENCE_FRAMES_LIMIT
                    val reachedMax = utteranceStream.size() >= MAX_UTTERANCE_BYTES

                    if (reachedSilence || reachedMax) {
                        isRecordingSpeech = false
                        silenceFrames = 0
                        onListeningStateChanged?.invoke(true, false)

                        val pcmData = utteranceStream.toByteArray()
                        utteranceStream.reset()
                        preSpeechRing.clear()

                        if (pcmData.size >= MIN_UTTERANCE_BYTES) {
                            Log.d(TAG, "Utterance finished (${pcmData.size} bytes). Checking voice biometric...")
                            val voiceMatched = voiceMatcher.matchesSpeaker(pcmData)
                            if (voiceMatched) {
                                Log.i(TAG, "Voice MATCHED Avishkar profile! Encoding WAV...")
                                val wavB64 = pcmToWavB64(pcmData)
                                onUtteranceCaptured(wavB64)
                            } else {
                                Log.w(TAG, "Voice did NOT match Avishkar vocal profile. Discarded.")
                            }
                        } else {
                            Log.d(TAG, "Utterance too short (${pcmData.size} bytes), discarded")
                        }
                    }
                }
            }

            try {
                audioRecord.stop()
                audioRecord.release()
                Log.i(TAG, "AudioRecord released")
            } catch (e: Exception) {
                Log.e(TAG, "Error stopping AudioRecord: ${e.message}")
            }
            onListeningStateChanged?.invoke(false, false)
        }, "LaylaContinuousPodsRecorder").also { it.start() }
    }

    fun pause() {
        isPaused = true
    }

    fun resume() {
        isPaused = false
    }

    fun stop() {
        isRunning = false
        isPaused = false
        workerThread?.interrupt()
        try { workerThread?.join(1500) } catch (_: Exception) {}
        workerThread = null
    }

    private fun pcmToWavB64(data: ByteArray): String {
        val h = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        h.put("RIFF".toByteArray()).putInt(36 + data.size).put("WAVE".toByteArray())
        h.put("fmt ".toByteArray()).putInt(16).putShort(1).putShort(1).putInt(rate).putInt(rate * 2)
        h.putShort(2).putShort(16).put("data".toByteArray()).putInt(data.size)
        return Base64.encodeToString(h.array() + data, Base64.NO_WRAP)
    }
}
