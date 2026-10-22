package `in`.tryvanta.laylavoice

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.view.View
import android.view.animation.LinearInterpolator

/** The Tryvanta mark: a white "T" with a rose flame curling off the crossbar. */
class LogoView(c: Context) : View(c) {
    private val white = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#F4F4F8") }
    private val rose = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#E8456F") }
    private val flame = Path()

    override fun onDraw(cv: Canvas) {
        val w = width.toFloat()
        val h = height.toFloat()
        cv.drawRoundRect(RectF(w * .08f, h * .06f, w * .92f, h * .24f), 3f, 3f, white)
        cv.drawRect(w * .40f, h * .24f, w * .56f, h * .98f, white)
        flame.reset()
        flame.moveTo(w * .62f, h * .98f)
        flame.cubicTo(w * .60f, h * .62f, w * .80f, h * .56f, w * .94f, h * .34f)
        flame.cubicTo(w * .92f, h * .62f, w * .84f, h * .80f, w * .62f, h * .98f)
        flame.close()
        cv.drawPath(flame, rose)
    }
}

/** Glowing ring + glass orb. Holding pulses the ring and brightens the orb. */
class OrbView(c: Context) : View(c) {
    private var phase = 0f
    private val pulse = ValueAnimator.ofFloat(0f, 1f).apply {
        duration = 1400
        repeatCount = ValueAnimator.INFINITE
        interpolator = LinearInterpolator()
        addUpdateListener { phase = it.animatedValue as Float; invalidate() }
    }
    private fun sync() { if (holding || speaking) { if (!pulse.isRunning) pulse.start() } else { pulse.cancel(); phase = 0f }; invalidate() }
    var holding = false
        set(v) { field = v; sync() }
    /** Layla is talking: same pulse as holding, orb stays at rest size. */
    var speaking = false
        set(v) { field = v; sync() }
    private val rose = Color.parseColor("#FF5C93")
    private val ring = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; color = rose }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
    private val line = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }

    init { setLayerType(LAYER_TYPE_SOFTWARE, null) }

    override fun onDraw(cv: Canvas) {
        val cx = width / 2f
        val cy = height / 2f
        val r = minOf(width, height) / 2f * .90f
        fill.shader = RadialGradient(cx, cy, r,
            intArrayOf(Color.argb(if (holding) 70 else 35, 255, 92, 147), Color.TRANSPARENT),
            floatArrayOf(.55f, 1f), Shader.TileMode.CLAMP)
        cv.drawCircle(cx, cy, r, fill)

        ring.strokeWidth = r * .028f
        ring.setShadowLayer(r * (if (holding) .10f else .06f), 0f, 0f, rose)
        cv.drawCircle(cx, cy, r, ring)
        if (holding || speaking) {
            line.strokeWidth = r * .012f
            line.color = Color.argb((120 * (1 - phase)).toInt(), 255, 92, 147)
            cv.drawCircle(cx, cy, r * (1f + .08f * phase), line)
        }

        val orbR = r * .26f * (if (holding) 1.07f else 1f)
        val oy = cy - r * .12f
        fill.shader = RadialGradient(cx - orbR * .25f, oy - orbR * .3f, orbR * 1.25f,
            intArrayOf(Color.parseColor("#FFFFFF"), Color.parseColor("#D8D2EC"), Color.parseColor("#6E6A92"), Color.parseColor("#2A2942")),
            floatArrayOf(0f, .35f, .8f, 1f), Shader.TileMode.CLAMP)
        fill.setShadowLayer(orbR * .5f, 0f, 0f, Color.argb(if (holding) 200 else 110, 255, 255, 255))
        cv.drawCircle(cx, oy, orbR, fill)
        fill.clearShadowLayer()
        line.strokeWidth = orbR * .06f
        line.color = Color.argb(120, 255, 255, 255)
        cv.drawCircle(cx, oy, orbR * 1.18f, line)
        line.color = Color.argb(60, 255, 255, 255)
        cv.drawCircle(cx, oy, orbR * 1.34f, line)
    }
}
