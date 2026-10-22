package in.tryvanta.almanac;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

import app.tryvanta.laylanative.LaylaNativePlugin;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        // Local plugins must be registered before super.onCreate() builds the bridge.
        registerPlugin(LaylaNativePlugin.class);
        super.onCreate(savedInstanceState);
    }
}
