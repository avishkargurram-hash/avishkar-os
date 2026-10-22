package `in`.tryvanta.laylacarface

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.pm.PackageManager
import android.net.http.SslError
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient

/**
 * Layla's face on the car's Android head unit: a full-screen kiosk WebView that
 * keeps her existing web face (FACE_URL) always open. It carries the owner
 * session cookie so the auth-gated page loads logged-in, grants the mic + USB
 * camera to the page (her ears + eyes), keeps the screen awake, hides the system
 * UI, and auto-reloads if the WiFi drops (the robot roams on weak WiFi). No
 * separate face is built here -- this is purely a shell around her one real face.
 */
class MainActivity : Activity() {

    private lateinit var web: WebView
    private val ui = Handler(Looper.getMainLooper())

    companion object {
        private const val HOST = "https://layla.tryvanta.in"
        private const val RETRY_MS = 5000L
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        hideSystemUi()
        requestRuntimePermissions()
        installAuthCookie()

        web = WebView(this)
        setContentView(web)

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            mediaPlaybackRequiresUserGesture = false      // let her speak/animate without a tap
            useWideViewPort = true
            loadWithOverviewMode = true
            cacheMode = WebSettings.LOAD_DEFAULT
            javaScriptCanOpenWindowsAutomatically = false
        }
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true)

        web.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                // grant whatever the face page asks for (audio capture + video capture)
                ui.post { request.grant(request.resources) }
            }
        }

        web.webViewClient = object : WebViewClient() {
            override fun onReceivedError(view: WebView, req: WebResourceRequest?, err: WebResourceError?) {
                if (req?.isForMainFrame == true) scheduleReload()
            }
            override fun onReceivedSslError(view: WebView, handler: SslErrorHandler, error: SslError) {
                handler.cancel()          // real Let's Encrypt cert -- never bypass TLS
            }
        }

        web.loadUrl(BuildConfig.FACE_URL)
    }

    private fun scheduleReload() {
        ui.removeCallbacksAndMessages(null)
        ui.postDelayed({ web.loadUrl(BuildConfig.FACE_URL) }, RETRY_MS)
    }

    private fun installAuthCookie() {
        val token = BuildConfig.DEFAULT_TOKEN
        if (token.isEmpty()) return
        val cm = CookieManager.getInstance()
        cm.setAcceptCookie(true)
        cm.setCookie(HOST, "layla_session=$token; Path=/; Secure; SameSite=Lax")
        cm.flush()
    }

    private fun requestRuntimePermissions() {
        val need = arrayOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.CAMERA)
            .filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
            .toTypedArray()
        if (need.isNotEmpty()) requestPermissions(need, 1)
    }

    @Suppress("DEPRECATION")
    private fun hideSystemUi() {
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                or View.SYSTEM_UI_FLAG_FULLSCREEN
                or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            )
    }

    override fun onResume() {
        super.onResume()
        hideSystemUi()
        if (this::web.isInitialized && web.url == null) web.loadUrl(BuildConfig.FACE_URL)
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) hideSystemUi()
    }

    // kiosk: back never leaves the face; just navigate within it if possible
    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        if (this::web.isInitialized && web.canGoBack()) web.goBack()
    }

    override fun onDestroy() {
        ui.removeCallbacksAndMessages(null)
        super.onDestroy()
    }
}
