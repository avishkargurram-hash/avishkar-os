package `in`.tryvanta.laylavoice

import android.content.Context
import android.util.Log
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Biometric Voiceprint Signature & Verification Engine.
 *
 * Combines:
 * 1. Fundamental Pitch (F0) tracking via Normalized Autocorrelation (vocal cord dynamics).
 * 2. 16-Band Mel-scale Spectral Filterbank Embeddings (vocal tract & formant resonance).
 *
 * Supports on-device enrollment of Avishkar's voice and real-time biometric verification
 * for hands-free ear pods mode without requiring the "Layla" wake-word.
 */
class VoiceMatcher(private val context: Context? = null) {

    private val prefs = context?.getSharedPreferences("layla", Context.MODE_PRIVATE)

    var minPitchHz: Double = prefs?.getFloat("voice_pitch_min", 85f)?.toDouble() ?: 85.0
    var maxPitchHz: Double = prefs?.getFloat("voice_pitch_max", 185f)?.toDouble() ?: 185.0
    var voiceMatchEnabled: Boolean = prefs?.getBoolean("voice_match_enabled", true) ?: true
    var wakeWordFree: Boolean = prefs?.getBoolean("voiceprint_wakeword_free", true) ?: true
    var matchThreshold: Float = prefs?.getFloat("voiceprint_threshold", 0.72f) ?: 0.72f

    companion object {
        private const val TAG = "LaylaVoiceMatcher"
        const val SAMPLE_RATE = 16000
        const val FRAME_SIZE = 1024       // 64 ms window
        const val HOP_SIZE = 512          // 32 ms hop
        private const val MIN_RMS = 250.0         // Speech presence floor
        private const val MIN_CORRELATION = 0.40  // Harmonic periodicity threshold
        const val MEL_BANDS = 16          // 16 spectral feature dimensions

        fun isEnrolled(context: Context): Boolean {
            val p = context.getSharedPreferences("layla", Context.MODE_PRIVATE)
            return p.getBoolean("voiceprint_enrolled", false)
        }

        fun getEnrolledDetails(context: Context): String {
            val p = context.getSharedPreferences("layla", Context.MODE_PRIVATE)
            if (!p.getBoolean("voiceprint_enrolled", false)) return "Not Enrolled (Using Default Calibration)"
            val meanF0 = p.getFloat("voiceprint_mean_f0", 120f).toInt()
            val minF0 = p.getFloat("voiceprint_min_f0", 85f).toInt()
            val maxF0 = p.getFloat("voiceprint_max_f0", 185f).toInt()
            return "Enrolled • Pitch $meanF0 Hz ($minF0-$maxF0 Hz) • 16-D Biometric Active"
        }
    }

    data class BiometricResult(
        val isMatch: Boolean,
        val similarityScore: Float,
        val medianPitchHz: Double,
        val voicedFrames: Int,
        val details: String
    )

    data class EnrollmentResult(
        val success: Boolean,
        val meanF0: Float,
        val minF0: Float,
        val maxF0: Float,
        val voicedFrameCount: Int,
        val errorMessage: String? = null
    )

    fun pcmToShorts(bytes: ByteArray): ShortArray {
        val count = bytes.size / 2
        val shorts = ShortArray(count)
        for (i in 0 until count) {
            val b0 = bytes[i * 2].toInt() and 0xFF
            val b1 = bytes[i * 2 + 1].toInt()
            shorts[i] = ((b1 shl 8) or b0).toShort()
        }
        return shorts
    }

    /**
     * Estimates fundamental pitch F0 in Hz for a single frame of samples using Normalized Autocorrelation.
     */
    fun estimatePitch(samples: ShortArray, start: Int, length: Int): Pair<Double, Double> {
        if (length < FRAME_SIZE) return Pair(0.0, 0.0)

        var sumSquares = 0.0
        for (i in 0 until length) {
            val v = samples[start + i].toDouble()
            sumSquares += v * v
        }
        val rms = sqrt(sumSquares / length)
        if (rms < MIN_RMS) return Pair(0.0, 0.0)

        val minLag = (SAMPLE_RATE / 300.0).toInt() // ~53 samples
        val maxLag = (SAMPLE_RATE / 70.0).toInt()  // ~228 samples

        var bestLag = 0
        var bestNormCorr = 0.0

        for (lag in minLag..maxLag) {
            var rLag = 0.0
            var e0 = 0.0
            var eLag = 0.0

            val count = length - lag
            for (n in 0 until count) {
                val s0 = samples[start + n].toDouble()
                val sl = samples[start + n + lag].toDouble()
                rLag += s0 * sl
                e0 += s0 * s0
                eLag += sl * sl
            }

            val denom = sqrt(e0 * eLag)
            if (denom > 1e-4) {
                val normCorr = rLag / denom
                if (normCorr > bestNormCorr) {
                    bestNormCorr = normCorr
                    bestLag = lag
                }
            }
        }

        if (bestNormCorr >= MIN_CORRELATION && bestLag > 0) {
            val f0 = SAMPLE_RATE.toDouble() / bestLag
            return Pair(f0, bestNormCorr)
        }

        return Pair(0.0, bestNormCorr)
    }

    /**
     * Extracts a 16-band normalized Mel-scale spectral energy vector from a 1024-sample frame.
     */
    fun extractMelVector(samples: ShortArray, start: Int): FloatArray {
        val n = FRAME_SIZE
        val real = DoubleArray(n)
        val imag = DoubleArray(n)

        // Apply Hann window
        for (i in 0 until n) {
            val w = 0.5 * (1.0 - cos(2.0 * PI * i / (n - 1)))
            real[i] = samples[start + i].toDouble() * w
            imag[i] = 0.0
        }

        // Fast In-Place Radix-2 FFT
        fft(real, imag)

        // Power Spectrum (first N/2 bins)
        val numBins = n / 2
        val power = DoubleArray(numBins)
        for (i in 0 until numBins) {
            power[i] = real[i] * real[i] + imag[i] * imag[i]
        }

        // Compute 16 Mel-spaced band energies (80 Hz to 7600 Hz)
        val melLow = hzToMel(80.0)
        val melHigh = hzToMel(7600.0)
        val melStep = (melHigh - melLow) / (MEL_BANDS + 1)

        val melFilters = FloatArray(MEL_BANDS)
        val binFreq = SAMPLE_RATE.toDouble() / n

        for (m in 1..MEL_BANDS) {
            val centerMel = melLow + m * melStep
            val leftMel = centerMel - melStep
            val rightMel = centerMel + melStep

            val leftHz = melToHz(leftMel)
            val centerHz = melToHz(centerMel)
            val rightHz = melToHz(rightMel)

            var bandEnergy = 0.0
            for (k in 0 until numBins) {
                val freq = k * binFreq
                if (freq in leftHz..rightHz) {
                    val weight = if (freq <= centerHz) {
                        (freq - leftHz) / (centerHz - leftHz)
                    } else {
                        (rightHz - freq) / (rightHz - centerHz)
                    }
                    bandEnergy += power[k] * weight
                }
            }
            melFilters[m - 1] = ln(max(bandEnergy, 1.0)).toFloat()
        }

        // L2 Normalize the vector
        var normSq = 0f
        for (v in melFilters) normSq += v * v
        val norm = sqrt(max(normSq.toDouble(), 1e-8)).toFloat()
        for (i in melFilters.indices) melFilters[i] = melFilters[i] / norm

        return melFilters
    }

    private fun hzToMel(hz: Double): Double = 2595.0 * kotlin.math.log10(1.0 + hz / 700.0)
    private fun melToHz(mel: Double): Double = 700.0 * (Math.pow(10.0, mel / 2595.0) - 1.0)

    /**
     * In-place Radix-2 Cooley-Tukey FFT.
     */
    private fun fft(real: DoubleArray, imag: DoubleArray) {
        val n = real.size
        var j = 0
        for (i in 0 until n) {
            if (j > i) {
                val tr = real[j]; real[j] = real[i]; real[i] = tr
                val ti = imag[j]; imag[j] = imag[i]; imag[i] = ti
            }
            var m = n shr 1
            while (m >= 1 && j >= m) {
                j -= m
                m = m shr 1
            }
            j += m
        }

        var len = 2
        while (len <= n) {
            val half = len shr 1
            val theta = -2.0 * PI / len
            val wStepR = cos(theta)
            val wStepI = sin(theta)

            var i = 0
            while (i < n) {
                var wR = 1.0
                var wI = 0.0
                for (k in 0 until half) {
                    val pos = i + k + half
                    val tr = wR * real[pos] - wI * imag[pos]
                    val ti = wR * imag[pos] + wI * real[pos]
                    real[pos] = real[i + k] - tr
                    imag[pos] = imag[i + k] - ti
                    real[i + k] += tr
                    imag[i + k] += ti
                    val nextWR = wR * wStepR - wI * wStepI
                    val nextWI = wR * wStepI + wI * wStepR
                    wR = nextWR
                    wI = nextWI
                }
                i += len
            }
            len = len shl 1
        }
    }

    /**
     * Enrolls Avishkar's voice from a 3-5 second sample of speech.
     * Extracts vocal frequency dynamics (F0 min, max, mean) and 16-D spectral voiceprint.
     */
    fun enroll(pcmBytes: ByteArray, speakerName: String = "Avishkar"): EnrollmentResult {
        val samples = pcmToShorts(pcmBytes)
        if (samples.size < FRAME_SIZE * 5) {
            return EnrollmentResult(false, 0f, 0f, 0f, 0, "Recording too short (minimum 1 second of speech needed)")
        }

        val pitches = mutableListOf<Double>()
        val avgVector = FloatArray(MEL_BANDS)
        var voicedCount = 0

        var offset = 0
        while (offset + FRAME_SIZE <= samples.size) {
            val (f0, _) = estimatePitch(samples, offset, FRAME_SIZE)
            if (f0 > 0.0) {
                pitches.add(f0)
                val vec = extractMelVector(samples, offset)
                for (i in 0 until MEL_BANDS) avgVector[i] += vec[i]
                voicedCount++
            }
            offset += HOP_SIZE
        }

        if (voicedCount < 10) {
            return EnrollmentResult(false, 0f, 0f, 0f, voicedCount, "Could not detect clear speech. Please speak louder into your pods mic.")
        }

        // Normalize average spectral vector
        var normSq = 0f
        for (i in 0 until MEL_BANDS) {
            avgVector[i] = avgVector[i] / voicedCount.toFloat()
            normSq += avgVector[i] * avgVector[i]
        }
        val norm = sqrt(max(normSq.toDouble(), 1e-8)).toFloat()
        for (i in 0 until MEL_BANDS) avgVector[i] = avgVector[i] / norm

        pitches.sort()
        val meanF0 = pitches.average().toFloat()
        val p10 = pitches[(pitches.size * 0.08).toInt()].toFloat()
        val p90 = pitches[(pitches.size * 0.92).toInt()].toFloat()

        val minBound = max(70f, p10 - 15f)
        val maxBound = min(260f, p90 + 20f)

        // Save to preferences
        prefs?.edit()?.apply {
            putBoolean("voiceprint_enrolled", true)
            putString("voiceprint_speaker", speakerName)
            putFloat("voiceprint_mean_f0", meanF0)
            putFloat("voiceprint_min_f0", minBound)
            putFloat("voiceprint_max_f0", maxBound)
            putString("voiceprint_vector", avgVector.joinToString(","))
            putBoolean("voiceprint_wakeword_free", true)
            putFloat("voice_pitch_min", minBound)
            putFloat("voice_pitch_max", maxBound)
            apply()
        }

        Log.i(TAG, "Voiceprint ENROLLED successfully: speaker=$speakerName, mean=$meanF0, range=$minBound-$maxBound Hz, frames=$voicedCount")
        return EnrollmentResult(true, meanF0, minBound, maxBound, voicedCount, null)
    }

    /**
     * Performs real-time Biometric Match against the enrolled voiceprint.
     */
    fun verifyUtterance(pcmBytes: ByteArray): BiometricResult {
        if (!voiceMatchEnabled) {
            return BiometricResult(true, 1.0f, 120.0, 10, "Voice matching disabled")
        }

        val samples = pcmToShorts(pcmBytes)
        if (samples.size < FRAME_SIZE) {
            return BiometricResult(false, 0f, 0.0, 0, "Audio too short")
        }

        val isEnrolled = prefs?.getBoolean("voiceprint_enrolled", false) ?: false
        val enrolledVecStr = prefs?.getString("voiceprint_vector", null)
        val enrolledVec = if (isEnrolled && !enrolledVecStr.isNullOrBlank()) {
            enrolledVecStr.split(",").mapNotNull { it.toFloatOrNull() }.toFloatArray().takeIf { it.size == MEL_BANDS }
        } else null

        val minHz = prefs?.getFloat("voiceprint_min_f0", minPitchHz.toFloat())?.toDouble() ?: minPitchHz
        val maxHz = prefs?.getFloat("voiceprint_max_f0", maxPitchHz.toFloat())?.toDouble() ?: maxPitchHz

        val pitches = mutableListOf<Double>()
        val utteranceVec = FloatArray(MEL_BANDS)
        var voicedCount = 0

        var offset = 0
        while (offset + FRAME_SIZE <= samples.size) {
            val (f0, _) = estimatePitch(samples, offset, FRAME_SIZE)
            if (f0 > 0.0) {
                pitches.add(f0)
                val vec = extractMelVector(samples, offset)
                for (i in 0 until MEL_BANDS) utteranceVec[i] += vec[i]
                voicedCount++
            }
            offset += HOP_SIZE
        }

        if (voicedCount < 3) {
            return BiometricResult(false, 0f, 0.0, voicedCount, "Insufficient voiced frames ($voicedCount)")
        }

        // Pitch matching ratio
        val matchingPitchCount = pitches.count { it in minHz..maxHz }
        val pitchMatchRatio = matchingPitchCount.toFloat() / pitches.size
        pitches.sort()
        val medianPitch = pitches[pitches.size / 2]

        // Spectral cosine similarity (if enrolled)
        var spectralScore = pitchMatchRatio
        if (enrolledVec != null) {
            var normSq = 0f
            for (i in 0 until MEL_BANDS) {
                utteranceVec[i] = utteranceVec[i] / voicedCount.toFloat()
                normSq += utteranceVec[i] * utteranceVec[i]
            }
            val norm = sqrt(max(normSq.toDouble(), 1e-8)).toFloat()
            for (i in 0 until MEL_BANDS) utteranceVec[i] = utteranceVec[i] / norm

            var dot = 0f
            for (i in 0 until MEL_BANDS) dot += utteranceVec[i] * enrolledVec[i]
            spectralScore = max(0f, dot)
        }

        // Combined score
        val finalScore = if (enrolledVec != null) {
            (0.35f * pitchMatchRatio) + (0.65f * spectralScore)
        } else {
            pitchMatchRatio
        }

        val passed = finalScore >= matchThreshold && medianPitch in (minHz - 10.0)..(maxHz + 15.0)

        val detail = "Score: ${String.format("%.2f", finalScore)} (threshold: $matchThreshold, pitch: ${medianPitch.toInt()} Hz [$minHz-$maxHz], voiced: $voicedCount)"
        Log.i(TAG, "Biometric check: passed=$passed, $detail")

        return BiometricResult(passed, finalScore, medianPitch, voicedCount, detail)
    }

    /**
     * Backward-compatible helper for existing calls.
     */
    fun matchesSpeaker(pcmBytes: ByteArray): Boolean {
        return verifyUtterance(pcmBytes).isMatch
    }
}
