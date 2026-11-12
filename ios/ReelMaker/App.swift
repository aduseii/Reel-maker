import SwiftUI
import AVFoundation

let accent = Color(UIColor(hex: "#FFA53A"))

@main
struct ReelMakerApp: App {
    @StateObject private var project = Project()
    @StateObject private var cloud = Cloud()

    init() {
        try? AVAudioSession.sharedInstance().setCategory(.playback)
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(project)
                .environmentObject(cloud)
                .preferredColorScheme(.dark)
                .tint(accent)
        }
    }
}
