package dev.alekseiorlov.peerly;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;
import dev.alekseiorlov.peerly.transport.PeerlyTransportPlugin;

public class MainActivity extends BridgeActivity {
    @Override public void onCreate(Bundle state) {
        registerPlugin(PeerlyTransportPlugin.class);
        super.onCreate(state);
    }
}
