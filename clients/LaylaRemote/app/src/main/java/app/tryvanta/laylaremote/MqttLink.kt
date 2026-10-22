package app.tryvanta.laylaremote

import org.eclipse.paho.client.mqttv3.IMqttActionListener
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken
import org.eclipse.paho.client.mqttv3.IMqttToken
import org.eclipse.paho.client.mqttv3.MqttAsyncClient
import org.eclipse.paho.client.mqttv3.MqttCallbackExtended
import org.eclipse.paho.client.mqttv3.MqttConnectOptions
import org.eclipse.paho.client.mqttv3.MqttMessage
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence

/**
 * Thin MQTT-over-TLS link to the Layla GR robot. Publishes motor commands on
 * `<prefix>/motor/set` and listens to the robot's retained state topics so the
 * screen can show whether the body is actually online.
 *
 * Every callback comes from a Paho thread -- the Activity hops to the UI thread.
 */
class MqttLink(private val listener: Listener) {

    interface Listener {
        fun onLink(connected: Boolean, detail: String)
        fun onTopic(suffix: String, payload: String)
    }

    companion object {
        const val PREFIX = "tryvanta/robot/001"
        private val STATE_TOPICS = arrayOf(
            "$PREFIX/status", "$PREFIX/motor/state", "$PREFIX/obstacle/state", "$PREFIX/distance/state"
        )
    }

    private var client: MqttAsyncClient? = null

    @Synchronized
    fun connect() {
        if (client?.isConnected == true) return
        try {
            val id = "layla-remote-" + System.currentTimeMillis().toString(36)
            val c = MqttAsyncClient("ssl://${BuildConfig.MQTT_HOST}:${BuildConfig.MQTT_PORT}", id, MemoryPersistence())
            c.setCallback(object : MqttCallbackExtended {
                override fun connectComplete(reconnect: Boolean, serverURI: String?) {
                    listener.onLink(true, if (reconnect) "reconnected" else "connected")
                    try {
                        c.subscribe(STATE_TOPICS, IntArray(STATE_TOPICS.size) { 0 })
                    } catch (_: Exception) {
                    }
                }

                override fun connectionLost(cause: Throwable?) {
                    listener.onLink(false, "link lost - retrying")
                }

                override fun messageArrived(topic: String?, message: MqttMessage?) {
                    if (topic == null || message == null) return
                    listener.onTopic(topic.removePrefix("$PREFIX/"), String(message.payload, Charsets.UTF_8))
                }

                override fun deliveryComplete(token: IMqttDeliveryToken?) {}
            })
            val opts = MqttConnectOptions().apply {
                userName = BuildConfig.MQTT_USER
                password = BuildConfig.MQTT_PASS.toCharArray()
                isCleanSession = true
                isAutomaticReconnect = true
                connectionTimeout = 10
                keepAliveInterval = 20
                mqttVersion = MqttConnectOptions.MQTT_VERSION_3_1_1
            }
            client = c
            listener.onLink(false, "connecting...")
            c.connect(opts, null, object : IMqttActionListener {
                override fun onSuccess(asyncActionToken: IMqttToken?) {}
                override fun onFailure(asyncActionToken: IMqttToken?, exception: Throwable?) {
                    listener.onLink(false, "failed: " + (exception?.message ?: "unknown"))
                }
            })
        } catch (e: Exception) {
            listener.onLink(false, "error: " + (e.message ?: e.javaClass.simpleName))
        }
    }

    @Synchronized
    fun disconnect() {
        val c = client ?: return
        client = null
        try {
            if (c.isConnected) c.disconnect(1000)
        } catch (_: Exception) {
        }
        try {
            c.close()
        } catch (_: Exception) {
        }
        listener.onLink(false, "off")
    }

    /** One motor command. The robot firmware auto-stops after durationMs (max 2000). */
    fun drive(action: String, speed: Int, durationMs: Int) {
        val c = client ?: return
        if (!c.isConnected) return
        val json = "{\"action\":\"$action\",\"speed\":${speed.coerceIn(0, 255)},\"duration_ms\":${durationMs.coerceIn(1, 2000)}}"
        try {
            val m = MqttMessage(json.toByteArray(Charsets.UTF_8))
            m.qos = 0
            m.isRetained = false
            c.publish("$PREFIX/motor/set", m)
        } catch (_: Exception) {
        }
    }

    fun stop() = drive("stop", 0, 1)
}
