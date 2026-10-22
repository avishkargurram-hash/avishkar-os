package app.tryvanta.laylaremote

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.view.MotionEvent
import android.view.View
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.min
import kotlin.math.sin

/**
 * A round turntable-style joystick: dark bezel with white tick marks and a pink
 * disc that follows the thumb and springs back to centre on release.
 * Reports x (right = +1) and y (up = +1), both in -1..1.
 */
class JoystickView(context: Context) : View(context) {

    fun interface OnMove {
        fun onMove(x: Float, y: Float)
    }

    var onMove: OnMove? = null

    private var knobDx = 0f   // knob offset from centre, in px
    private var knobDy = 0f
    private var pointerId = -1

    private val bezel = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#2B2E35") }
    private val bezelEdge = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#5A5F6B"); style = Paint.Style.STROKE; strokeWidth = 6f
    }
    private val tick = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#E6E8EE"); strokeWidth = 5f; strokeCap = Paint.Cap.ROUND
    }
    private val platter = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#14161B") }
    private val disc = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#E9B8DC") }
    private val discRing = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#B06A9C"); style = Paint.Style.STROKE; strokeWidth = 4f
    }
    private val hub = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#F7F2F6") }

    private fun radius() = min(width, height) / 2f * 0.96f

    override fun onDraw(canvas: Canvas) {
        val cx = width / 2f
        val cy = height / 2f
        val r = radius()
        canvas.drawCircle(cx, cy, r, bezel)
        canvas.drawCircle(cx, cy, r, bezelEdge)
        for (i in 0 until 48) {
            val a = Math.toRadians(i * 7.5)
            val x1 = cx + (r * 0.80f) * cos(a).toFloat()
            val y1 = cy + (r * 0.80f) * sin(a).toFloat()
            val x2 = cx + (r * 0.92f) * cos(a).toFloat()
            val y2 = cy + (r * 0.92f) * sin(a).toFloat()
            canvas.drawLine(x1, y1, x2, y2, tick)
        }
        canvas.drawCircle(cx, cy, r * 0.74f, platter)
        val kx = cx + knobDx
        val ky = cy + knobDy
        canvas.drawCircle(kx, ky, r * 0.34f, disc)
        canvas.drawCircle(kx, ky, r * 0.34f, discRing)
        canvas.drawCircle(kx, ky, r * 0.06f, hub)
    }

    override fun onTouchEvent(e: MotionEvent): Boolean {
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> {
                if (pointerId == -1) {
                    pointerId = e.getPointerId(e.actionIndex)
                    parent?.requestDisallowInterceptTouchEvent(true)
                    follow(e, e.actionIndex)
                }
            }
            MotionEvent.ACTION_MOVE -> {
                val i = e.findPointerIndex(pointerId)
                if (i >= 0) follow(e, i)
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP, MotionEvent.ACTION_CANCEL -> {
                val released = e.getPointerId(e.actionIndex)
                if (e.actionMasked == MotionEvent.ACTION_CANCEL || released == pointerId) {
                    pointerId = -1
                    knobDx = 0f
                    knobDy = 0f
                    invalidate()
                    onMove?.onMove(0f, 0f)
                }
            }
        }
        return true
    }

    private fun follow(e: MotionEvent, index: Int) {
        val reach = radius() * 0.62f           // how far the knob centre may travel
        var dx = e.getX(index) - width / 2f
        var dy = e.getY(index) - height / 2f
        val d = hypot(dx, dy)
        if (d > reach) {
            dx *= reach / d
            dy *= reach / d
        }
        knobDx = dx
        knobDy = dy
        invalidate()
        onMove?.onMove(dx / reach, -dy / reach)
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val w = MeasureSpec.getSize(widthMeasureSpec)
        val h = MeasureSpec.getSize(heightMeasureSpec)
        val s = min(w, h)
        setMeasuredDimension(s, s)
    }
}
