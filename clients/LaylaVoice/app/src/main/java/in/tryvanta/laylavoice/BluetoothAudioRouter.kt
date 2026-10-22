package `in`.tryvanta.laylavoice

import android.content.Context
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.os.Build
import android.util.Log

/**
 * Manages audio routing to Bluetooth Earpods (e.g. Boult ear pods) using Android's
 * SCO / Communication Device APIs for both mic input and voice communication output.
 */
class BluetoothAudioRouter(private val context: Context) {
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    companion object {
        private const val TAG = "LaylaBT"
    }

    /**
     * Checks if a Bluetooth SCO or BLE headset is currently paired and connected.
     */
    fun isHeadsetConnected(): Boolean {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                audioManager.availableCommunicationDevices.any {
                    it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO ||
                    it.type == AudioDeviceInfo.TYPE_BLE_HEADSET
                }
            } else {
                @Suppress("DEPRECATION")
                audioManager.isBluetoothScoAvailableOffCall
            }
        } catch (e: Exception) {
            Log.e(TAG, "isHeadsetConnected error: ${e.message}")
            false
        }
    }

    /**
     * Routes both microphone capture and speaker playback to the Bluetooth earpods.
     */
    fun setPodsCommunication(enable: Boolean): Boolean {
        return try {
            if (enable) {
                audioManager.mode = AudioManager.MODE_IN_COMMUNICATION

                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    val btDevice = audioManager.availableCommunicationDevices.firstOrNull {
                        it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO ||
                        it.type == AudioDeviceInfo.TYPE_BLE_HEADSET
                    }
                    if (btDevice != null) {
                        val ok = audioManager.setCommunicationDevice(btDevice)
                        Log.i(TAG, "Communication device set to ${btDevice.productName}: $ok")
                        return ok
                    } else {
                        Log.w(TAG, "No Bluetooth SCO/BLE headset found in available communication devices")
                    }
                }

                // Legacy SCO fallback (API < 31 or if setCommunicationDevice had no device)
                @Suppress("DEPRECATION")
                audioManager.startBluetoothSco()
                @Suppress("DEPRECATION")
                audioManager.isBluetoothScoOn = true
                Log.i(TAG, "Legacy Bluetooth SCO started")
                true
            } else {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    audioManager.clearCommunicationDevice()
                } else {
                    @Suppress("DEPRECATION")
                    audioManager.isBluetoothScoOn = false
                    @Suppress("DEPRECATION")
                    audioManager.stopBluetoothSco()
                }
                audioManager.mode = AudioManager.MODE_NORMAL
                Log.i(TAG, "Bluetooth communication mode disabled, restored NORMAL mode")
                true
            }
        } catch (e: Exception) {
            Log.e(TAG, "Bluetooth routing failed: ${e.message}", e)
            false
        }
    }
}
