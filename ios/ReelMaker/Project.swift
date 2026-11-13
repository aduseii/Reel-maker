import SwiftUI
import UIKit
import AVFoundation
import CoreImage
import CoreImage.CIFilterBuiltins

/// Everything about the reel being made: layout, layers, video, trim, cover and export settings.
final class Project: ObservableObject {
    // frame
    @Published var bgMode = "black"                 // black | white | blur | custom
    @Published var bgColor = "#FF1F6F5C"
    @Published var preset = PRESETS[0].0
    @Published var zone: [CGFloat] = [250, 450, 120, 120]   // top, bottom, left, right
    @Published var scale: CGFloat = 100
    @Published var dx: CGFloat = 0
    @Published var dy: CGFloat = 0
    @Published var radius: CGFloat = 0
    @Published var clamp = true
    @Published var showZone = true

    // layers
    @Published var layers: [Layer] = []
    @Published var selectedID: UUID?
    @Published var overlay: UIImage?               // all layers drawn at 1080 × 1920

    // cover
    @Published var coverTitle = ""
    @Published var coverTitleSize: CGFloat = 110
    @Published var coverTitleColor = "#FFFFFFFF"
    @Published var coverTitleY: CGFloat = 8
    @Published var coverIncludeLayers = false
    @Published var coverZoom: CGFloat = 100
    @Published var coverCX: CGFloat = 0.5
    @Published var coverCY: CGFloat = 0.5
    @Published var coverTime: Double = 0
    @Published var coverFrame: UIImage?
    @Published var coverPreview: UIImage?

    // export
    @Published var quality = 0
    @Published var fps = 0                          // 30 | 60 | source
    @Published var coverFirst = true
    @Published var saveCoverToo = false

    // template
    @Published var templateName: String?
    @Published var locked = false

    // video
    @Published var videoURL: URL?
    @Published var duration: Double = 0
    @Published var trimStart: Double = 0
    @Published var trimEnd: Double = 0
    @Published var playhead: Double = 0
    @Published var isPlaying = false
    @Published var videoSize = CGSize(width: 1920, height: 1080)
    @Published var bgBlur: UIImage?
    @Published var status = "Open a video to start."
    @Published var pendingCaption: String?

    let player = AVPlayer()
    private var timeObserver: Any?
    let ci = CIContext()

    init() {
        timeObserver = player.addPeriodicTimeObserver(forInterval: CMTime(value: 1, timescale: 30), queue: .main) { [weak self] t in
            self?.tick(t.seconds)
        }
        refresh()
    }

    // MARK: geometry
    var zoneRect: CGRect {
        CGRect(x: zone[2], y: zone[0], width: max(10, RW - zone[2] - zone[3]), height: max(10, RH - zone[0] - zone[1]))
    }
    var aspect: CGFloat { videoSize.height > 0 ? videoSize.width / videoSize.height : 16 / 9 }

    func videoRect(_ ar: CGFloat? = nil) -> CGRect {
        let a = ar ?? aspect
        let z = zoneRect
        let bw = min(z.width, z.height * a)
        let k = scale / 100
        let w = bw * k, h = bw / a * k
        return CGRect(x: z.midX + dx - w / 2, y: z.midY + dy - h / 2, width: w, height: h)
    }

    var selectedIndex: Int? { layers.firstIndex { $0.id == selectedID } }

    // MARK: changes
    /// Re-place attached layers, fit one-line captions and redraw the overlay.
    func refresh() {
        for i in layers.indices { place(&layers[i]) }
        overlay = Render.overlay(self)
        if !coverEditing { renderCoverPreviewSoon() }
    }

    var coverEditing = false

    func place(_ l: inout Layer) {
        if l.kind == .text && l.fitOneLine {
            if !fitOneLiner(&l) { sitOnVideo(&l, l.attachGap ?? 24) }
            return
        }
        if let g = l.attachGap { sitOnVideo(&l, g) }
    }

    func sitOnVideo(_ l: inout Layer, _ gap: CGFloat) {
        let r = l.rect
        l.moveTo(left: r.minX, top: videoRect().minY - gap - r.height)
    }

    func unfit(_ l: inout Layer) { if let b = l.fitBase { l.size = b; l.fitBase = nil } }

    /// One-line text: as big as fits (up to 140 px, using up to 55% of the room above the video),
    /// placed a little closer to the video than to the top of the safe zone.
    func fitOneLiner(_ l: inout Layer) -> Bool {
        let base = l.baseSize
        unfit(&l)
        let vr = videoRect(), z = zoneRect
        let text = l.text.trimmingCharacters(in: .whitespacesAndNewlines)
        let space = vr.minY - z.minY
        guard !text.isEmpty, !text.contains("\n"), TextLayout.layout(l).lines.count == 1, space > l.height + 28 else { return false }
        var best = base
        var s = base + 2
        while s <= 140 {
            var t = l; t.size = s
            if TextLayout.layout(t).lines.count > 1 || t.height > space * 0.55 { break }
            best = s; s += 2
        }
        if best != base { l.size = best; l.fitBase = base }
        let free = vr.minY - z.minY - l.height
        let gap = max(28, free * 0.38)
        l.moveTo(left: l.x - l.w / 2, top: vr.minY - gap - l.height)
        return true
    }

    func clampLayer(_ l: inout Layer) {
        guard clamp, !locked else { return }
        let z = zoneRect
        if l.w > z.width { l.w = z.width }
        let r = l.rect
        let left = min(max(r.minX, z.minX), z.maxX - r.width)
        let top = min(max(r.minY, z.minY), max(z.minY, z.maxY - r.height))
        l.moveTo(left: left, top: top)
    }

    func edit(_ id: UUID?, _ f: (inout Layer) -> Void) {
        guard let id = id, let i = layers.firstIndex(where: { $0.id == id }) else { return }
        f(&layers[i])
        refresh()
    }

    // MARK: layers
    func addText() {
        var t = Layer.newText()
        t.w = min(760, zoneRect.width - 40)
        t.moveTo(left: zoneRect.midX - t.w / 2, top: zoneRect.minY + 40)
        t.attachGap = 24
        layers.append(t)
        selectedID = t.id
        refresh()
    }

    func addImage(data: Data, name: String) {
        guard let img = UIImage(data: data) else { status = "Couldn't read that picture."; return }
        var l = Layer(kind: .image)
        l.image = img.normalizedUp(); l.imageData = data; l.name = name
        l.w = min(zoneRect.width * 0.3, img.size.width * img.scale)
        let z = zoneRect
        l.moveTo(left: z.maxX - l.w, top: z.minY)
        layers.append(l)
        selectedID = l.id
        refresh()
    }

    func deleteSelected() {
        guard !locked, let i = selectedIndex else { return }
        layers.remove(at: i); selectedID = nil; refresh()
    }

    func moveSelected(_ by: Int) {
        guard !locked, let i = selectedIndex else { return }
        let j = i + by
        guard layers.indices.contains(j) else { return }
        layers.swapAt(i, j); refresh()
    }

    // MARK: X caption
    func fillCaption(_ text: String) -> String {
        guard !text.isEmpty else { return "The post has no text, so the caption box wasn't changed. " }
        var targets = Project.captionIndices(layers)
        if targets.isEmpty {
            var t = Layer.newText(text)
            t.w = max(200, zoneRect.width - 80); t.fromPost = true; t.fitOneLine = true; t.attachGap = 24; t.size = 48
            layers.append(t)
            targets = [layers.count - 1]
        }
        for i in targets { layers[i].text = text }
        selectedID = layers[targets[0]].id
        refresh()
        let z = zoneRect
        if targets.contains(where: { layers[$0].rect.minY < z.minY - 1 || layers[$0].rect.maxY > z.maxY + 1 }) {
            return "The caption is long and runs outside the safe zone; shorten it in Layers. "
        }
        return ""
    }

    // MARK: video
    func load(url: URL) {
        videoURL = url
        let asset = AVURLAsset(url: url)
        let item = AVPlayerItem(asset: asset)
        player.replaceCurrentItem(with: item)
        isPlaying = false
        status = "Loading the video…"
        Task { @MainActor in
            do {
                let tracks = try await asset.loadTracks(withMediaType: .video)
                let dur = try await asset.load(.duration).seconds
                if let v = tracks.first {
                    let (ns, tf) = try await v.load(.naturalSize, .preferredTransform)
                    let s = ns.applying(tf)
                    self.videoSize = CGSize(width: abs(s.width), height: abs(s.height))
                }
                self.duration = dur
                self.trimStart = 0; self.trimEnd = dur; self.playhead = 0
                self.coverTime = min(dur, 0.5)
                self.status = "\(Int(self.videoSize.width)) × \(Int(self.videoSize.height)) loaded. Trim, then pick a cover."
                self.refresh()
                self.grabBackground(at: 0)
                self.grabCoverFrame()
                if let c = self.pendingCaption {
                    self.pendingCaption = nil
                    let note = self.fillCaption(c)
                    self.status = "Imported the post. \(note)Pick a cover, then export."
                }
            } catch {
                self.status = "Couldn't open that video."
            }
        }
    }

    func tick(_ t: Double) {
        guard duration > 0, t.isFinite else { return }
        if isPlaying && (t >= trimEnd - 0.03 || t < trimStart - 0.25) {
            seek(trimStart)
            return
        }
        playhead = t
    }

    func togglePlay() {
        guard videoURL != nil else { return }
        if isPlaying {
            player.pause(); isPlaying = false
            grabBackground(at: playhead)
        } else {
            if playhead < trimStart || playhead >= trimEnd - 0.05 { seek(trimStart) }
            player.play(); isPlaying = true
        }
    }

    func seek(_ t: Double) {
        playhead = t
        player.seek(to: CMTime(seconds: t, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
    }

    func frame(at t: Double, maxSize: CGFloat = 1920, done: @escaping (UIImage?) -> Void) {
        guard let url = videoURL else { done(nil); return }
        let gen = AVAssetImageGenerator(asset: AVURLAsset(url: url))
        gen.appliesPreferredTrackTransform = true
        gen.requestedTimeToleranceBefore = .zero
        gen.requestedTimeToleranceAfter = .zero
        gen.maximumSize = CGSize(width: maxSize, height: maxSize)
        gen.generateCGImagesAsynchronously(forTimes: [NSValue(time: CMTime(seconds: t, preferredTimescale: 600))]) { _, cg, _, _, _ in
            let img = cg.map { UIImage(cgImage: $0) }
            DispatchQueue.main.async { done(img) }
        }
    }

    /// The blurred background for the preview (export blurs every frame).
    func grabBackground(at t: Double) {
        guard bgMode == "blur" else { return }
        frame(at: t, maxSize: 640) { [weak self] img in
            guard let self = self, let img = img, let cg = img.cgImage else { return }
            self.bgBlur = Render.blurredBackground(CIImage(cgImage: cg), context: self.ci).flatMap { UIImage(cgImage: $0) }
        }
    }

    func grabCoverFrame() {
        frame(at: coverTime) { [weak self] img in
            self?.coverFrame = img
            self?.renderCoverPreviewSoon()
        }
    }

    private var coverWork: DispatchWorkItem?
    func renderCoverPreviewSoon() {
        coverWork?.cancel()
        let w = DispatchWorkItem { [weak self] in
            guard let self = self else { return }
            self.coverPreview = Render.cover(self, scale: 0.5)
        }
        coverWork = w
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15, execute: w)
    }

    /// The 9:16 window over the source frame, in the frame's pixels.
    func coverCrop(_ size: CGSize, cx: CGFloat? = nil, cy: CGFloat? = nil) -> CGRect {
        let sw = max(1, size.width), sh = max(1, size.height)
        let z = coverZoom / 100
        let h = min(sh, sw * 16 / 9) / z
        let w = h * 9 / 16
        let x = min(max(cx ?? coverCX, (w / 2) / sw), 1 - (w / 2) / sw)
        let y = min(max(cy ?? coverCY, (h / 2) / sh), 1 - (h / 2) / sh)
        return CGRect(x: x * sw - w / 2, y: y * sh - h / 2, width: w, height: h)
    }

    // MARK: templates
    /// The caption box(es): ticked "Caption box", otherwise the first text box. X imports fill it, and
    /// templates keep its place and style but not its words.
    static func captionIndices(_ layers: [Layer]) -> [Int] {
        let texts = layers.indices.filter { layers[$0].kind == .text }
        let ticked = texts.filter { layers[$0].fromPost }
        return ticked.isEmpty ? Array(texts.prefix(1)) : ticked
    }

    /// What a template file holds: the layout, with the caption box's words left out.
    func templateDict(name: String) -> [String: Any] {
        var saved = layers
        for i in Project.captionIndices(saved) { saved[i].text = "" }
        return [
            "version": 1, "name": name, "saved_at": Date().timeIntervalSince1970,
            "background": ["mode": bgMode, "color": bgColor],
            "preset": preset, "zone": zone,
            "video": ["scale": scale, "dx": dx, "dy": dy, "radius": radius],
            "clamp": clamp,
            "layers": saved.map { $0.toDict() },
            "cover": ["title": coverTitle, "title_size": coverTitleSize, "title_color": coverTitleColor,
                      "title_y": coverTitleY, "include_layers": coverIncludeLayers, "zoom": coverZoom, "grid": true],
            "export": ["quality": quality, "fps": fps, "save_cover": saveCoverToo, "cover_first": coverFirst,
                       "cover_embed": true],
        ]
    }

    func apply(template d: [String: Any]) {
        func num(_ any: Any?, _ def: CGFloat) -> CGFloat { (any as? NSNumber).map { CGFloat($0.doubleValue) } ?? def }
        let bg = d["background"] as? [String: Any] ?? [:]
        bgMode = bg["mode"] as? String ?? "black"
        bgColor = bg["color"] as? String ?? "#FF1F6F5C"
        preset = d["preset"] as? String ?? "Custom"
        if let z = d["zone"] as? [NSNumber], z.count == 4 { zone = z.map { CGFloat($0.doubleValue) } }
        let v = d["video"] as? [String: Any] ?? [:]
        scale = num(v["scale"], 100); dx = num(v["dx"], 0); dy = num(v["dy"], 0); radius = num(v["radius"], 0)
        clamp = d["clamp"] as? Bool ?? true
        // the words already in your caption box come along (an X import, or the template updated elsewhere)
        let words = Project.captionIndices(layers).map { layers[$0].text }
            .first { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty } ?? ""
        layers = (d["layers"] as? [[String: Any]] ?? []).compactMap { Layer.fromDict($0) }
        for i in Project.captionIndices(layers) { layers[i].text = words }
        let c = d["cover"] as? [String: Any] ?? [:]
        coverTitle = c["title"] as? String ?? ""
        coverTitleSize = num(c["title_size"], 110)
        coverTitleColor = c["title_color"] as? String ?? "#FFFFFFFF"
        coverTitleY = num(c["title_y"], 8)
        coverIncludeLayers = c["include_layers"] as? Bool ?? false
        coverZoom = num(c["zoom"], 100)
        let e = d["export"] as? [String: Any] ?? [:]
        quality = (e["quality"] as? NSNumber)?.intValue ?? 0
        fps = (e["fps"] as? NSNumber)?.intValue ?? 0
        saveCoverToo = e["save_cover"] as? Bool ?? false
        coverFirst = e["cover_first"] as? Bool ?? true
        templateName = d["name"] as? String
        selectedID = nil
        locked = true
        refresh()
        grabBackground(at: playhead)
    }
}

extension UIImage {
    /// Pixels the right way up (photos can carry a rotation flag).
    func normalizedUp() -> UIImage {
        if imageOrientation == .up && scale == 1 { return self }
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1
        let px = CGSize(width: size.width * scale, height: size.height * scale)
        return UIGraphicsImageRenderer(size: px, format: fmt).image { _ in draw(in: CGRect(origin: .zero, size: px)) }
    }
}
