package `in`.tryvanta.laylatv

import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.view.KeyEvent
import org.json.JSONObject

/**
 * The TV controls that DON'T need INJECT_EVENTS and therefore actually work on
 * a stock non-rooted Google TV:
 *   - volume            -> AudioManager
 *   - media play/pause  -> AudioManager.dispatchMediaKeyEvent (routes to the
 *                          active MediaSession, e.g. YouTube/Netflix/Plex)
 *   - launch app        -> leanback launch intent
 *   - back/home/recents -> AccessibilityService global actions
 * DPAD navigation of a third-party app's UI is deliberately NOT here — it needs
 * ADB-over-TCP (adb_setup.sh), which the laptop bridge drives.
 */
object TvController {

    fun dispatch(ctx: Context, action: String, body: JSONObject) {
        when (action) {
            "volume_up"   -> volume(ctx, AudioManager.ADJUST_RAISE)
            "volume_down" -> volume(ctx, AudioManager.ADJUST_LOWER)
            "mute"        -> volume(ctx, AudioManager.ADJUST_TOGGLE_MUTE)
            "play_pause"  -> media(ctx, KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE)
            "next"        -> media(ctx, KeyEvent.KEYCODE_MEDIA_NEXT)
            "previous"    -> media(ctx, KeyEvent.KEYCODE_MEDIA_PREVIOUS)
            "back"        -> LaylaAccessibilityService.instance?.back()
            "home"        -> LaylaAccessibilityService.instance?.home()
            "recents"     -> LaylaAccessibilityService.instance?.recents()
            "enter"       -> LaylaAccessibilityService.instance?.clickFocused()
            "launch"      -> launch(ctx, body.optString("package"))
            "speak"       -> LaylaTts.speak(ctx, body.optString("text"))
        }
    }

    private fun volume(ctx: Context, dir: Int) {
        val am = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        am.adjustStreamVolume(AudioManager.STREAM_MUSIC, dir, AudioManager.FLAG_SHOW_UI)
    }

    private fun media(ctx: Context, code: Int) {
        val am = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        am.dispatchMediaKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, code))
        am.dispatchMediaKeyEvent(KeyEvent(KeyEvent.ACTION_UP, code))
    }

    private fun launch(ctx: Context, pkg: String) {
        if (pkg.isBlank()) return
        val i = ctx.packageManager.getLeanbackLaunchIntentForPackage(pkg)
            ?: ctx.packageManager.getLaunchIntentForPackage(pkg)
        i?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        i?.let { ctx.startActivity(it) }
    }
}
