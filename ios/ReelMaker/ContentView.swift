import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
import AVKit

enum Tab: String, CaseIterable { case frame = "Frame", layers = "Layers", cover = "Cover", export = "Export" }

/// A video picked from Photos, copied into the app.
struct Movie: Transferable {
    let url: URL
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { SentTransferredFile($0.url) } importing: { r in
            let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("Videos")
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let ext = r.file.pathExtension.isEmpty ? "mov" : r.file.pathExtension
            let dst = dir.appendingPathComponent("video-\(Int(Date().timeIntervalSince1970)).\(ext)")
            try? FileManager.default.removeItem(at: dst)
            try FileManager.default.copyItem(at: r.file, to: dst)
            return Movie(url: dst)
        }
    }
}

struct ContentView: View {
    @EnvironmentObject var p: Project
    @EnvironmentObject var cloud: Cloud
    @State private var tab: Tab = .layers
    @State private var videoItem: PhotosPickerItem?
    @State private var logoItem: PhotosPickerItem?
    @State private var showVideoPicker = false
    @State private var showLogoPicker = false
    @State private var fileMode: UTType?
    @State private var showX = false
    @State private var showCloud = false
    @State private var saveName = ""
    @State private var showSave = false

    var body: some View {
        VStack(spacing: 0) {
            topBar
            Group {
                if tab == .cover { CoverEditor() } else { CanvasView(onSelect: { tab = .layers }) }
            }
            .frame(maxWidth: .infinity)
            .frame(maxHeight: .infinity)
            .padding(.horizontal, 12)
            .padding(.top, 6)
            TransportBar().padding(.horizontal, 14).padding(.vertical, 6)
            Picker("", selection: $tab) {
                ForEach(Tab.allCases, id: \.self) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal, 14)
            ScrollView {
                Group {
                    switch tab {
                    case .frame: FramePanel()
                    case .layers: LayersPanel(addLogoPhotos: { showLogoPicker = true }, addLogoFiles: { fileMode = .image })
                    case .cover: CoverPanel()
                    case .export: ExportPanel()
                    }
                }
                .padding(14)
            }
            .frame(height: 300)
            Text(p.status)
                .font(.footnote).foregroundStyle(.secondary).lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 14).padding(.bottom, 4)
        }
        .background(Color(UIColor(hex: "#0D0E10")).ignoresSafeArea())
        .photosPicker(isPresented: $showVideoPicker, selection: $videoItem, matching: .videos)
        .photosPicker(isPresented: $showLogoPicker, selection: $logoItem, matching: .images)
        .onChange(of: videoItem) { item in
            guard let item = item else { return }
            p.status = "Copying the video…"
            Task {
                if let m = try? await item.loadTransferable(type: Movie.self) {
                    await MainActor.run { p.load(url: m.url); tab = .layers }
                } else {
                    await MainActor.run { p.status = "Couldn't open that video." }
                }
                await MainActor.run { videoItem = nil }
            }
        }
        .onChange(of: logoItem) { item in
            guard let item = item else { return }
            Task {
                if let d = try? await item.loadTransferable(type: Data.self) {
                    await MainActor.run { p.addImage(data: d, name: "photo.png") }
                }
                await MainActor.run { logoItem = nil }
            }
        }
        .fileImporter(isPresented: Binding(get: { fileMode != nil }, set: { if !$0 { fileMode = nil } }),
                      allowedContentTypes: fileMode == .movie ? [.movie] : [.image]) { result in
            let mode = fileMode
            guard case .success(let url) = result else { return }
            let ok = url.startAccessingSecurityScopedResource()
            defer { if ok { url.stopAccessingSecurityScopedResource() } }
            if mode == .movie {
                let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("Videos")
                try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
                let dst = dir.appendingPathComponent(url.lastPathComponent)
                try? FileManager.default.removeItem(at: dst)
                if (try? FileManager.default.copyItem(at: url, to: dst)) != nil { p.load(url: dst) }
            } else if let d = try? Data(contentsOf: url) {
                p.addImage(data: d, name: url.lastPathComponent)
            }
        }
        .sheet(isPresented: $showX) { XImportSheet(onDone: { tab = .cover }) }
        .sheet(isPresented: $showCloud) { CloudSheet() }
        .alert("Save template", isPresented: $showSave) {
            TextField("Name", text: $saveName)
            Button("Save") { saveTemplate() }
            Button("Cancel", role: .cancel) {}
        } message: { Text("Saves the layout so every new video uses it, locked in place.") }
    }

    private var topBar: some View {
        HStack(spacing: 14) {
            Image(systemName: "rectangle.stack.fill").font(.title3).foregroundStyle(accent)
            Menu {
                Button { showVideoPicker = true } label: { Label("Video from Photos", systemImage: "photo.on.rectangle") }
                Button { fileMode = .movie } label: { Label("Video from Files", systemImage: "folder") }
                Button { showX = true } label: { Label("From X link", systemImage: "link") }
            } label: { Label("Open", systemImage: "plus.circle.fill").font(.headline) }
            Spacer()
            Menu {
                if cloud.templates.isEmpty { Text("No templates yet") }
                ForEach(cloud.templates) { t in
                    Button(t.name) { applyTemplate(t.file) }
                }
                Divider()
                Button { saveName = p.templateName ?? ""; showSave = true } label: { Label("Save as template…", systemImage: "square.and.arrow.down") }
                Button { showCloud = true } label: {
                    Label(cloud.signedIn ? "Cloud (\(cloud.login ?? "GitHub"))" : "Sign in with GitHub", systemImage: "icloud")
                }
            } label: {
                Label(p.templateName ?? "Templates", systemImage: "square.stack").lineLimit(1)
            }
            Button { p.locked.toggle() } label: {
                Image(systemName: p.locked ? "lock.fill" : "lock.open").foregroundStyle(p.locked ? accent : .secondary)
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 8)
    }

    private func applyTemplate(_ url: URL) {
        guard let d = try? Data(contentsOf: url), let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else {
            p.status = "Couldn't open that template."; return
        }
        p.apply(template: j)
        p.status = "Using “\(p.templateName ?? "template")”. Layout locked; you can still change the words."
    }

    private func saveTemplate() {
        let name = saveName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty, let d = try? JSONSerialization.data(withJSONObject: p.templateDict(name: name), options: [.prettyPrinted]) else { return }
        try? d.write(to: Cloud.folder.appendingPathComponent(Cloud.fileName(name)))
        p.templateName = name
        p.locked = true
        cloud.reloadLocal()
        p.status = "Saved “\(name)”."
        if cloud.signedIn {
            Task { let m = (try? await cloud.sync()) ?? "Saved here; cloud sync failed."; await MainActor.run { p.status = m } }
        }
    }
}

// MARK: - video view
struct PlayerView: UIViewRepresentable {
    let player: AVPlayer
    final class V: UIView {
        override class var layerClass: AnyClass { AVPlayerLayer.self }
        var pl: AVPlayerLayer { layer as! AVPlayerLayer }
    }
    func makeUIView(context: Context) -> V {
        let v = V()
        v.pl.player = player
        v.pl.videoGravity = .resizeAspectFill
        v.isUserInteractionEnabled = false
        return v
    }
    func updateUIView(_ v: V, context: Context) {}
}

// MARK: - the 9:16 preview
struct CanvasView: View {
    @EnvironmentObject var p: Project
    var onSelect: () -> Void
    @State private var dragID: UUID?
    @State private var grab = CGPoint.zero
    @State private var began = false
    @State private var guideX = false

    var body: some View {
        GeometryReader { g in
            let k = g.size.width / RW
            let vr = p.videoRect()
            ZStack(alignment: .topLeading) {
                background
                if p.videoURL != nil {
                    PlayerView(player: p.player)
                        .frame(width: vr.width * k, height: vr.height * k)
                        .clipShape(RoundedRectangle(cornerRadius: p.radius * k))
                        .offset(x: vr.minX * k, y: vr.minY * k)
                } else {
                    Rectangle().fill(Color.white.opacity(0.07))
                        .overlay(Text("Your video goes here").font(.footnote).foregroundStyle(.secondary))
                        .frame(width: vr.width * k, height: vr.height * k)
                        .offset(x: vr.minX * k, y: vr.minY * k)
                }
                if let ov = p.overlay {
                    Image(uiImage: ov).resizable().interpolation(.high).frame(width: g.size.width, height: g.size.height)
                }
                if p.showZone {
                    let z = p.zoneRect
                    Rectangle().strokeBorder(Color.yellow.opacity(0.6), style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
                        .frame(width: z.width * k, height: z.height * k).offset(x: z.minX * k, y: z.minY * k)
                }
                if let i = p.selectedIndex {
                    let r = p.layers[i].rect
                    Rectangle().stroke(accent, lineWidth: 1.5)
                        .frame(width: r.width * k, height: r.height * k).offset(x: r.minX * k, y: r.minY * k)
                }
                if guideX {
                    Rectangle().fill(Color.pink).frame(width: 1, height: g.size.height).offset(x: g.size.width / 2)
                }
            }
            .frame(width: g.size.width, height: g.size.height)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .contentShape(Rectangle())
            .gesture(DragGesture(minimumDistance: 0)
                .onChanged { v in dragChanged(CGPoint(x: v.location.x / k, y: v.location.y / k)) }
                .onEnded { _ in dragID = nil; began = false; guideX = false })
        }
        .aspectRatio(9 / 16, contentMode: .fit)
    }

    @ViewBuilder private var background: some View {
        switch p.bgMode {
        case "white": Color.white
        case "custom": Color(UIColor(hex: p.bgColor))
        case "blur":
            if let b = p.bgBlur { Image(uiImage: b).resizable() } else { Color.black }
        default: Color.black
        }
    }

    private func dragChanged(_ pt: CGPoint) {
        if !began {
            began = true
            if let l = p.layers.last(where: { $0.rect.insetBy(dx: -12, dy: -12).contains(pt) }) {
                p.selectedID = l.id
                dragID = l.id
                grab = CGPoint(x: pt.x - l.x, y: pt.y - l.y)
                onSelect()
            } else {
                p.selectedID = nil
                dragID = nil
            }
            return
        }
        guard let id = dragID, !p.locked, let l = p.layers.first(where: { $0.id == id }) else { return }
        var nx = pt.x - grab.x
        let ny = pt.y - grab.y
        guideX = abs(nx - RW / 2) < 10
        if guideX { nx = RW / 2 }
        let held = l.attachGap != nil || l.fitOneLine
        p.edit(id) { layer in
            layer.x = nx
            if held && abs(ny - layer.y) < 12 { return }      // small wobble keeps an attached layer in place
            if held {
                layer.attachGap = nil
                layer.fitOneLine = false
                p.unfit(&layer)
            }
            layer.y = ny
            p.clampLayer(&layer)
        }
    }
}

// MARK: - play / trim
struct TransportBar: View {
    @EnvironmentObject var p: Project

    var body: some View {
        HStack(spacing: 12) {
            Button { p.togglePlay() } label: {
                Image(systemName: p.isPlaying ? "pause.fill" : "play.fill")
                    .font(.title3).frame(width: 40, height: 40)
                    .background(Circle().fill(accent)).foregroundStyle(.black)
            }
            .disabled(p.videoURL == nil)
            VStack(spacing: 4) {
                TrimBar()
                HStack {
                    Text(fmt(p.playhead - p.trimStart))
                    Spacer()
                    Text("Clip \(fmt(p.trimEnd - p.trimStart))")
                }
                .font(.caption2.monospacedDigit()).foregroundStyle(.secondary)
            }
        }
    }

    func fmt(_ t: Double) -> String {
        let s = max(0, t)
        return String(format: "%d:%04.1f", Int(s) / 60, s.truncatingRemainder(dividingBy: 60))
    }
}

struct TrimBar: View {
    @EnvironmentObject var p: Project
    @State private var mode = 0     // 0 none, 1 start handle, 2 end handle, 3 seek
    @State private var wasPlaying = false

    var body: some View {
        GeometryReader { g in
            let w = g.size.width
            let d = max(0.01, p.duration)
            let xs = CGFloat(p.trimStart / d) * w, xe = CGFloat(p.trimEnd / d) * w
            let xp = CGFloat(p.playhead / d) * w
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 4).fill(Color.white.opacity(0.08))
                RoundedRectangle(cornerRadius: 4).fill(accent.opacity(0.28)).frame(width: max(0, xe - xs)).offset(x: xs)
                handle.offset(x: xs - 6)
                handle.offset(x: xe - 6)
                Rectangle().fill(Color.white).frame(width: 2).offset(x: xp - 1)
            }
            .contentShape(Rectangle())
            .gesture(DragGesture(minimumDistance: 0).onChanged { v in
                let t = Double(min(max(0, v.location.x / w), 1)) * d
                if mode == 0 {
                    let x = v.startLocation.x
                    mode = abs(x - xs) < 22 ? 1 : (abs(x - xe) < 22 ? 2 : 3)
                    wasPlaying = p.isPlaying
                    if wasPlaying { p.player.pause(); p.isPlaying = false }
                }
                guard p.videoURL != nil else { return }
                switch mode {
                case 1: p.trimStart = min(t, p.trimEnd - 0.2); p.seek(p.trimStart)
                case 2: p.trimEnd = max(t, p.trimStart + 0.2); p.seek(p.trimEnd)
                default: p.seek(t)
                }
            }.onEnded { _ in
                if mode == 1 || mode == 2 { p.seek(p.trimStart); p.coverTime = min(max(p.coverTime, p.trimStart), p.trimEnd) }
                mode = 0
                if wasPlaying { p.togglePlay() } else { p.grabBackground(at: p.playhead) }
            })
        }
        .frame(height: 30)
    }

    private var handle: some View {
        RoundedRectangle(cornerRadius: 3).fill(accent).frame(width: 12, height: 30)
    }
}
