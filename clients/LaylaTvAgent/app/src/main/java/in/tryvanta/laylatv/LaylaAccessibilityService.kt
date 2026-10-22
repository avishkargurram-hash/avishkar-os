package `in`.tryvanta.laylatv

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.view.accessibility.AccessibilityEvent
import android.util.Log

/**
 * What an AccessibilityService on a stock, non-rooted Google TV CAN actually do:
 *   - performGlobalAction: BACK, HOME, RECENTS, DISMISS_NOTIFICATION_SHADE, etc.
 *   - read the current foreground package (what app is on screen)
 *   - find on-screen nodes and ACTION_CLICK / ACTION_FOCUS them
 *
 * What it CANNOT do (important — this is the hard wall in the spec):
 *   - inject raw DPAD_UP/DOWN/LEFT/RIGHT/ENTER/VOLUME keycodes into OTHER apps.
 *     Key injection needs INJECT_EVENTS, a signature|privileged permission that
 *     is NOT grantable with `pm grant` and NOT exposed to AccessibilityService.
 *     On a non-rooted TV, arbitrary keycode navigation of third-party apps is
 *     only possible via ADB-over-TCP (see adb_setup.sh) driven from the laptop
 *     bridge / VM, OR via node-click where the app exposes clickable nodes.
 *
 * So: use global actions + node clicks here; use TvController for volume/media/
 * app-launch (those have real non-accessibility APIs); use ADB-over-TCP for
 * true DPAD navigation.
 */
class LaylaAccessibilityService : AccessibilityService() {

    companion object {
        @Volatile var instance: LaylaAccessibilityService? = null
        @Volatile var foregroundPkg: String = ""
    }

    override fun onServiceConnected() {
        instance = this
        serviceInfo = AccessibilityServiceInfo().apply {
            eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
            feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
            flags = AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS or
                    AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
            notificationTimeout = 50
        }
        Log.i("LaylaA11y", "connected")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event?.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            event.packageName?.let { foregroundPkg = it.toString() }
        }
    }

    override fun onInterrupt() {}

    override fun onDestroy() { instance = null; super.onDestroy() }

    // ---- the real capabilities, callable from MQTT command handlers ----
    fun back()    = performGlobalAction(GLOBAL_ACTION_BACK)
    fun home()    = performGlobalAction(GLOBAL_ACTION_HOME)
    fun recents() = performGlobalAction(GLOBAL_ACTION_RECENTS)

    /** Click the currently-focused node, the closest thing to "ENTER" that an
     *  AccessibilityService can do without INJECT_EVENTS. */
    fun clickFocused(): Boolean {
        val root = rootInActiveWindow ?: return false
        val focused = root.findFocus(android.view.accessibility.AccessibilityNodeInfo.FOCUS_INPUT)
            ?: root.findFocus(android.view.accessibility.AccessibilityNodeInfo.FOCUS_ACCESSIBILITY)
            ?: return false
        return focused.performAction(android.view.accessibility.AccessibilityNodeInfo.ACTION_CLICK)
    }

    fun currentApp(): String = foregroundPkg
}
