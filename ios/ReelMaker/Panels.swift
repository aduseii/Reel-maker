import SwiftUI
import AVKit
import Photos

// MARK: - small building blocks
struct Section_<Content: View>: View {
    let title: String
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title.uppercased()).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.bottom, 14)
    }
}

struct SliderRow: View {
    let label: String
    @Binding var value: CGFloat
    let range: ClosedRange<CGFloat>
    var step: CGFloat = 1
    var suffix = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label).font(.subheadline)
                Spacer()
                Text("\(Int(value.rounded()))\(suffix)").font(.subheadline.monospacedDigit()).foregroundStyle(.secondary)
            }
            Slider(value: $value, in: range, step: step)
        }
    }
}

extension Project {
    /// A binding to a field of the selected layer that redraws on change.
    func lb<T>(_ kp: WritableKeyPath<Layer, T>, _ def: T) -> Binding<T> {
        Binding(get: { [weak self] in
                    guard let s = self, let l = s.layers.first(where: { $0.id == s.selectedID }) else { return def }
                    return l[keyPath: kp]
                },
                set: { [weak self] v in self?.edit(self?.selectedID) { $0[keyPath: kp] = v } })
    }

    func fb(_ kp: ReferenceWritableKeyPath<Project, CGFloat>) -> Binding<CGFloat> {
        Binding(get: { [weak self] in self?[keyPath: kp] ?? 0 }, set: { [weak self] v in self?[keyPath: kp] = v; self?.refresh() })
    }
}

// MARK: - Frame
struct FramePanel: View {
    @EnvironmentObject var p: Project

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Section_(title: "Background") {
                Picker("", selection: Binding(get: { p.bgMode }, set: { p.bgMode = $0; p.grabBackground(at: p.playhead) })) {
                    Text("Black").tag("black"); Text("White").tag("white"); Text("Blur").tag("blur"); Text("Colour").tag("custom")
                }
                .pickerStyle(.segmented)
                if p.bgMode == "custom" {
                    ColorPicker("Colour", selection: hexBinding({ p.bgColor }, { p.bgColor = $0 }), supportsOpacity: false)
                }
            }
            Section_(title: "Safe zone") {
                Picker("Preset", selection: Binding(get: { p.preset }, set: { name in
                    p.preset = name
                    if let z = PRESETS.first(where: { $0.0 == name })?.1 { p.zone = z }
                    p.refresh()
                })) { ForEach(PRESETS.map { $0.0 }, id: \.self) { Text($0).tag($0) } }
                if p.preset == "Custom" {
                    ForEach(0..<4) { i in
                        SliderRow(label: ["Top", "Bottom", "Left", "Right"][i],
                                  value: Binding(get: { p.zone[i] }, set: { p.zone[i] = $0; p.refresh() }),
                                  range: 0...900, step: 5, suffix: " px")
                    }
                }
                Toggle("Show safe zone", isOn: $p.showZone)
                Toggle("Keep layers inside safe zone", isOn: $p.clamp)
            }
            Section_(title: "Video") {
                SliderRow(label: "Size", value: p.fb(\.scale), range: 40...300, suffix: "%")
                SliderRow(label: "Across", value: p.fb(\.dx), range: -540...540, step: 5, suffix: " px")
                SliderRow(label: "Up / down", value: p.fb(\.dy), range: -960...960, step: 5, suffix: " px")
                SliderRow(label: "Corners", value: p.fb(\.radius), range: 0...200, step: 2, suffix: " px")
                Button("Centre and reset size") { p.scale = 100; p.dx = 0; p.dy = 0; p.refresh() }
            }
        }
        .disabled(p.locked)
        .overlay(alignment: .topTrailing) { if p.locked { LockedNote() } }
    }
}

struct LockedNote: View {
    @EnvironmentObject var p: Project
    var body: some View {
        Button { p.locked = false } label: { Label("Locked · unlock", systemImage: "lock.fill").font(.caption) }
            .buttonStyle(.bordered).disabled(false)
    }
}

// MARK: - Layers
struct LayersPanel: View {
    @EnvironmentObject var p: Project
    var addLogoPhotos: () -> Void
    var addLogoFiles: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Button { p.addText() } label: { Label("Text", systemImage: "textformat") }
                Menu {
                    Button("From Photos", action: addLogoPhotos)
                    Button("From Files", action: addLogoFiles)
                } label: { Label("Logo / photo", systemImage: "photo") }
                Spacer()
                Button { p.moveSelected(1) } label: { Image(systemName: "arrow.up") }
                Button { p.moveSelected(-1) } label: { Image(systemName: "arrow.down") }
                Button(role: .destructive) { p.deleteSelected() } label: { Image(systemName: "trash") }
            }
            .buttonStyle(.bordered)
            .disabled(p.locked)
            .padding(.bottom, 10)

            ForEach(p.layers.reversed()) { l in
                Button { p.selectedID = l.id } label: {
                    HStack {
                        Image(systemName: l.kind == .text ? "textformat" : "photo")
                        Text(l.label).lineLimit(1)
                        Spacer()
                        if l.fromPost { Text("X caption").font(.caption2).foregroundStyle(.secondary) }
                    }
                    .padding(.vertical, 8).padding(.horizontal, 10)
                    .background(RoundedRectangle(cornerRadius: 8).fill(l.id == p.selectedID ? accent.opacity(0.22) : Color.white.opacity(0.05)))
                }
                .buttonStyle(.plain)
            }
            .padding(.bottom, 12)

            if let i = p.selectedIndex {
                if p.layers[i].kind == .text { TextControls() } else { ImageControls() }
            } else if p.layers.isEmpty {
                Text("Add text, a logo or a photo. Tap a layer on the preview to select it, drag to move it.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
    }
}

struct TextControls: View {
    @EnvironmentObject var p: Project

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Section_(title: "Words") {
                TextEditor(text: p.lb(\.text, ""))
                    .frame(height: 90)
                    .scrollContentBackground(.hidden)
                    .background(RoundedRectangle(cornerRadius: 8).fill(Color.white.opacity(0.06)))
            }
            Group {
                Section_(title: "Look") {
                    SliderRow(label: "Size", value: Binding(get: { p.layers[p.selectedIndex ?? 0].baseSize }, set: { v in
                        p.edit(p.selectedID) { l in if l.fitBase != nil { l.fitBase = v } else { l.size = v } }
                    }), range: 16...200, suffix: " px")
                    Picker("Weight", selection: p.lb(\.weight, 700)) {
                        Text("Regular").tag(400); Text("Medium").tag(500); Text("Semibold").tag(600)
                        Text("Bold").tag(700); Text("Heavy").tag(800); Text("Black").tag(900)
                    }
                    ColorPicker("Text colour", selection: hexBinding({ p.layers[p.selectedIndex ?? 0].color }, { v in p.edit(p.selectedID) { $0.color = v } }))
                    Picker("Align", selection: p.lb(\.align, "center")) {
                        Image(systemName: "text.alignleft").tag("left")
                        Image(systemName: "text.aligncenter").tag("center")
                        Image(systemName: "text.alignright").tag("right")
                    }.pickerStyle(.segmented)
                    Toggle("Shadow", isOn: p.lb(\.shadow, false))
                    SliderRow(label: "Box width", value: p.lb(\.w, 760), range: 100...1080, step: 10, suffix: " px")
                }
                Section_(title: "Background") {
                    Picker("Style", selection: p.lb(\.style, "box")) {
                        Text("None").tag("plain"); Text("Box").tag("box"); Text("Highlight").tag("highlight")
                    }.pickerStyle(.segmented)
                    ColorPicker("Box colour", selection: hexBinding({ p.layers[p.selectedIndex ?? 0].boxColor }, { v in p.edit(p.selectedID) { $0.boxColor = v } }), supportsOpacity: false)
                    SliderRow(label: "Opacity", value: Binding(get: { p.layers[p.selectedIndex ?? 0].boxAlpha * 100 },
                                                               set: { v in p.edit(p.selectedID) { $0.boxAlpha = v / 100 } }), range: 0...100, suffix: "%")
                    SliderRow(label: "Corners", value: p.lb(\.radius, 28), range: 0...80)
                    SliderRow(label: "Padding", value: p.lb(\.pad, 30), range: 0...100)
                }
                Section_(title: "Placement") {
                    Toggle("Sit on video", isOn: Binding(get: { p.layers[p.selectedIndex ?? 0].attachGap != nil },
                                                         set: { on in p.edit(p.selectedID) { $0.attachGap = on ? 24 : nil } }))
                    Toggle("Auto size and place one-line text", isOn: Binding(get: { p.layers[p.selectedIndex ?? 0].fitOneLine },
                                                                             set: { on in p.edit(p.selectedID) { l in l.fitOneLine = on; if !on { p.unfit(&l) } } }))
                    Toggle("Caption box for X imports", isOn: p.lb(\.fromPost, false))
                }
            }
            .disabled(p.locked)
        }
    }
}

struct ImageControls: View {
    @EnvironmentObject var p: Project

    var body: some View {
        Section_(title: "Image") {
            SliderRow(label: "Width", value: p.lb(\.w, 240), range: 30...1080, step: 2, suffix: " px")
            SliderRow(label: "Opacity", value: Binding(get: { p.layers[p.selectedIndex ?? 0].opacity * 100 },
                                                       set: { v in p.edit(p.selectedID) { $0.opacity = v / 100 } }), range: 5...100, suffix: "%")
            Toggle("Sit on video", isOn: Binding(get: { p.layers[p.selectedIndex ?? 0].attachGap != nil },
                                                 set: { on in p.edit(p.selectedID) { $0.attachGap = on ? 24 : nil } }))
            Button("Crispest size") { crispest() }
            if let i = p.selectedIndex, let img = p.layers[i].image {
                let px = img.size.width * img.scale
                if p.layers[i].w > px * 1.1 {
                    Text("This picture is only \(Int(px)) px wide but is shown \(Int(p.layers[i].w)) px wide, so it will look soft. Use a bigger file for crisp edges.")
                        .font(.footnote).foregroundStyle(accent)
                }
            }
        }
        .disabled(p.locked)
    }

    /// Its own size, or exactly 1/2, 1/3 … of it: the sharpest sizes for a picture.
    func crispest() {
        guard let i = p.selectedIndex, let img = p.layers[i].image else { return }
        let px = img.size.width * img.scale
        let maxW = p.zoneRect.width
        let options = (1...40).map { px / CGFloat($0) }.filter { $0 <= maxW + 0.01 && $0 >= 30 }
        guard let w = options.min(by: { abs($0 - p.layers[i].w) < abs($1 - p.layers[i].w) }) else { return }
        p.edit(p.selectedID) { $0.w = w }
        p.status = "Now \(Int(w)) px wide: the sharpest size near what you had."
    }
}

// MARK: - Cover
struct CoverEditor: View {
    @EnvironmentObject var p: Project
    @State private var start: (CGFloat, CGFloat)?

    var body: some View {
        VStack(spacing: 8) {
            GeometryReader { g in
                if let f = p.coverFrame, let cg = f.cgImage {
                    let size = CGSize(width: cg.width, height: cg.height)
                    let k = min(g.size.width / size.width, g.size.height / size.height)
                    let shown = CGSize(width: size.width * k, height: size.height * k)
                    let crop = p.coverCrop(size)
                    ZStack(alignment: .topLeading) {
                        Image(uiImage: f).resizable().frame(width: shown.width, height: shown.height).opacity(0.45)
                        Image(uiImage: f).resizable().frame(width: shown.width, height: shown.height)
                            .mask(Rectangle().frame(width: crop.width * k, height: crop.height * k)
                                    .offset(x: crop.minX * k, y: crop.minY * k)
                                    .frame(width: shown.width, height: shown.height, alignment: .topLeading))
                        Rectangle().stroke(accent, lineWidth: 2)
                            .frame(width: crop.width * k, height: crop.height * k).offset(x: crop.minX * k, y: crop.minY * k)
                    }
                    .frame(width: shown.width, height: shown.height)
                    .position(x: g.size.width / 2, y: g.size.height / 2)
                    .gesture(DragGesture().onChanged { v in
                        if start == nil { start = (p.coverCX, p.coverCY) }
                        let c = p.coverCrop(size, cx: start!.0 + v.translation.width / shown.width,
                                            cy: start!.1 + v.translation.height / shown.height)
                        p.coverCX = c.midX / size.width; p.coverCY = c.midY / size.height
                    }.onEnded { _ in start = nil; p.renderCoverPreviewSoon() })
                } else {
                    Text("Open a video to pick a cover.").foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            HStack {
                Image(systemName: "clock")
                Slider(value: Binding(get: { p.coverTime }, set: { p.coverTime = $0 }),
                       in: p.trimStart...max(p.trimStart + 0.01, p.trimEnd),
                       onEditingChanged: { editing in if !editing { p.grabCoverFrame() } })
            }
            .disabled(p.videoURL == nil)
        }
    }
}

struct CoverPanel: View {
    @EnvironmentObject var p: Project

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Group {
                if let c = p.coverPreview { Image(uiImage: c).resizable() } else { Color.black }
            }
            .aspectRatio(9 / 16, contentMode: .fit)
            .frame(width: 110)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            VStack(alignment: .leading, spacing: 10) {
                Text("Drag the frame above to choose the 9:16 window, and slide to pick the moment.")
                    .font(.footnote).foregroundStyle(.secondary)
                SliderRow(label: "Zoom", value: Binding(get: { p.coverZoom }, set: { p.coverZoom = $0; p.renderCoverPreviewSoon() }), range: 100...400, suffix: "%")
                TextField("Title (optional)", text: Binding(get: { p.coverTitle }, set: { p.coverTitle = $0; p.renderCoverPreviewSoon() }))
                    .textFieldStyle(.roundedBorder)
                if !p.coverTitle.isEmpty {
                    SliderRow(label: "Title size", value: Binding(get: { p.coverTitleSize }, set: { p.coverTitleSize = $0; p.renderCoverPreviewSoon() }), range: 30...260)
                    SliderRow(label: "Title position", value: Binding(get: { p.coverTitleY }, set: { p.coverTitleY = $0; p.renderCoverPreviewSoon() }), range: 0...100, suffix: "%")
                    ColorPicker("Title colour", selection: hexBinding({ p.coverTitleColor }, { p.coverTitleColor = $0; p.renderCoverPreviewSoon() }), supportsOpacity: false)
                }
                Toggle("Include text and logos", isOn: Binding(get: { p.coverIncludeLayers }, set: { p.coverIncludeLayers = $0; p.renderCoverPreviewSoon() }))
            }
        }
    }
}

// MARK: - Export
struct ExportPanel: View {
    @EnvironmentObject var p: Project
    @State private var exporter = Exporter()
    @State private var progress: Float?
    @State private var result: URL?
    @State private var assetID: String?
    @State private var watch = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Section_(title: "Output") {
                Picker("Quality", selection: $p.quality) { Text("Best").tag(0); Text("High").tag(1); Text("Small").tag(2) }
                    .pickerStyle(.segmented)
                Picker("Frame rate", selection: $p.fps) { Text("30 fps").tag(0); Text("60 fps").tag(1); Text("Source").tag(2) }
                    .pickerStyle(.segmented)
                Toggle("Start the reel with the cover", isOn: $p.coverFirst)
                Toggle("Also save the cover to Photos", isOn: $p.saveCoverToo)
            }
            if let pr = progress {
                ProgressView(value: pr) { Text("Exporting… \(Int(pr * 100))%") }
                Button("Cancel", role: .cancel) { exporter.cancel() }.padding(.top, 6)
            } else {
                Button { Task { await run() } } label: {
                    Label("Export reel", systemImage: "square.and.arrow.up").frame(maxWidth: .infinity).padding(.vertical, 6)
                }
                .buttonStyle(.borderedProminent).foregroundStyle(.black)
                .disabled(p.videoURL == nil)
            }
            if let e = error { Text(e).font(.footnote).foregroundStyle(.red).padding(.top, 8) }
            if result != nil {
                Text("Saved to Photos.").font(.subheadline.weight(.semibold)).padding(.top, 12)
                HStack {
                    Button { watch = true } label: { Label("Watch", systemImage: "play.rectangle") }
                    Button { openInstagram() } label: { Label("Post to Instagram", systemImage: "camera") }
                }
                .buttonStyle(.bordered).padding(.top, 6)
            }
        }
        .sheet(isPresented: $watch) { if let r = result { VideoPlayer(player: AVPlayer(url: r)).ignoresSafeArea() } }
    }

    @MainActor
    func run() async {
        error = nil; result = nil; progress = 0
        p.player.pause(); p.isPlaying = false
        do {
            let url = try await exporter.run(p) { progress = $0 }
            progress = nil
            assetID = try await Exporter.saveToPhotos(video: url, cover: p.saveCoverToo ? Render.cover(p) : nil)
            result = url
            p.status = "Reel saved to Photos."
        } catch {
            progress = nil
            self.error = error.localizedDescription
        }
    }

    func openInstagram() {
        let id = assetID.flatMap { $0.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) } ?? ""
        if let u = URL(string: "instagram://library?LocalIdentifier=\(id)"), UIApplication.shared.canOpenURL(u) {
            UIApplication.shared.open(u)
        } else if let u = URL(string: "https://www.instagram.com/") {
            UIApplication.shared.open(u)
        }
    }
}

// MARK: - X import
struct XImportSheet: View {
    @EnvironmentObject var p: Project
    @Environment(\.dismiss) var dismiss
    var onDone: () -> Void
    @State private var link = ""
    @State private var working = false
    @State private var progress = 0.0
    @State private var error: String?
    @State private var post: XImport.Post?

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 14) {
                Text("Paste the link to a post with a video. Reel Maker downloads the video, puts it in your template and fills the caption box with the post's text. Then just pick a cover and export.")
                    .font(.subheadline).foregroundStyle(.secondary)
                HStack {
                    TextField("https://x.com/…/status/…", text: $link)
                        .textFieldStyle(.roundedBorder).textInputAutocapitalization(.never).autocorrectionDisabled()
                    PasteButton(payloadType: String.self) { s in link = s.first ?? "" }
                        .labelStyle(.iconOnly).buttonBorderShape(.capsule)
                }
                if working {
                    ProgressView(value: progress) { Text(progress > 0 ? "Downloading the video…" : "Getting the post…") }
                }
                if let e = error { Text(e).font(.footnote).foregroundStyle(.red) }
                if let post = post, post.videos.count > 1, !working {
                    Text("This post has \(post.videos.count) videos. Which one?").font(.subheadline)
                    ForEach(post.videos.indices, id: \.self) { i in
                        Button("Video \(i + 1)") { Task { await download(post, i) } }.buttonStyle(.bordered)
                    }
                }
                Spacer()
            }
            .padding()
            .navigationTitle("Import from X")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Import") { Task { await start() } }.disabled(XImport.postID(in: link) == nil || working)
                }
            }
        }
    }

    @MainActor
    func start() async {
        guard let found = XImport.postID(in: link) else { error = XImport.XError.badLink.localizedDescription; return }
        let (id, idx) = found
        error = nil; working = true; progress = 0
        do {
            let got = try await XImport.fetch(id)
            post = got
            if got.videos.count == 1 || idx != nil {
                await download(got, max(0, min(got.videos.count - 1, (idx ?? 1) - 1)))
            } else {
                working = false
            }
        } catch {
            working = false
            self.error = error.localizedDescription
        }
    }

    @MainActor
    func download(_ post: XImport.Post, _ i: Int) async {
        working = true
        do {
            let name = post.user + "_" + post.id + (post.videos.count > 1 ? "_\(i + 1)" : "")
            let url = try await XImport.download(post.videos[i], name: name) { progress = max(0.01, $0) }
            p.pendingCaption = post.caption
            p.load(url: url)
            p.status = "Imported @\(post.user)'s video."
            working = false
            dismiss()
            onDone()
        } catch {
            working = false
            self.error = error.localizedDescription
        }
    }
}

// MARK: - GitHub cloud
struct CloudSheet: View {
    @EnvironmentObject var cloud: Cloud
    @Environment(\.dismiss) var dismiss
    @State private var code: Cloud.DeviceCode?
    @State private var msg = ""
    @State private var busy = false

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 16) {
                if cloud.signedIn {
                    Text("Signed in as \(cloud.login ?? "GitHub"). Your templates sync with the Windows app through a secret gist on your account.")
                        .foregroundStyle(.secondary)
                    Button { Task { await sync() } } label: { Label("Sync now", systemImage: "arrow.triangle.2.circlepath") }
                        .buttonStyle(.borderedProminent).foregroundStyle(.black).disabled(busy)
                    Button("Sign out", role: .destructive) { cloud.signOut() }
                } else if let c = code {
                    Text("1. Copy this code").font(.headline)
                    HStack {
                        Text(c.user).font(.system(.largeTitle, design: .monospaced).weight(.bold))
                        Button { UIPasteboard.general.string = c.user } label: { Image(systemName: "doc.on.doc") }
                    }
                    Text("2. Open GitHub, paste it and approve").font(.headline)
                    Link(destination: c.verify) { Label("Open github.com/login/device", systemImage: "safari") }
                    ProgressView("Waiting for you to approve…")
                } else {
                    Text("Sign in with the same GitHub account as on your PC and your templates will appear here.")
                        .foregroundStyle(.secondary)
                    Button { Task { await signIn() } } label: { Label("Sign in with GitHub", systemImage: "person.badge.key") }
                        .buttonStyle(.borderedProminent).foregroundStyle(.black).disabled(busy)
                }
                if !msg.isEmpty { Text(msg).font(.footnote) }
                Spacer()
            }
            .padding()
            .navigationTitle("Cloud templates")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
    }

    @MainActor
    func signIn() async {
        busy = true; msg = ""
        do {
            let c = try await cloud.startSignIn()
            code = c
            UIPasteboard.general.string = c.user
            try await cloud.finishSignIn(c)
            code = nil
            await sync()
        } catch {
            code = nil
            msg = error.localizedDescription
        }
        busy = false
    }

    @MainActor
    func sync() async {
        busy = true
        do { msg = try await cloud.sync() } catch { msg = error.localizedDescription }
        busy = false
    }
}
