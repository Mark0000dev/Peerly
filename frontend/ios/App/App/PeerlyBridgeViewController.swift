import Capacitor

final class PeerlyBridgeViewController: CAPBridgeViewController {
    override func capacitorDidLoad() {
        bridge?.registerPluginInstance(PeerlyTransportPlugin())
    }
}
