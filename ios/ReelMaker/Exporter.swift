import UIKit
import AVFoundation
import CoreImage
import Photos

/// Builds the 1080 × 1920 reel: background, video, layers, and the cover as the first frame.
final class Exporter {
    enum ExportError: LocalizedError {
        case noVideo, failed(String)
        var errorDescription: String? {
            switch self {
            case .noVideo: return "Open a video first."
            case .failed(let s): return s
            }
        }
    }

    private var session: AVAssetExportSession?
    private var timer: Timer?

    func cancel() { session?.cancelExport() }

    @MainActor
    func run(_ p: Project, progress: @escaping (Float) -> Void) async throws -> URL {
        guard let url = p.videoURL else { throw ExportError.noVideo }
        let asset = AVURLAsset(url: url)
        guard let srcV = try await asset.loadTracks(withMediaType: .video).first else { throw ExportError.noVideo }
        let srcA = try await asset.loadTracks(withMediaType: .audio).first
        let (natural, transform, rate) = try await srcV.load(.naturalSize, .preferredTransform, .nominalFrameRate)

        let start = CMTime(seconds: p.trimStart, preferredTimescale: 600)
        let end = CMTime(seconds: max(p.trimStart + 0.1, p.trimEnd), preferredTimescale: 600)
        let range = CMTimeRange(start: start, end: end)

        let comp = AVMutableComposition()
        guard let cv = comp.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) else {
            throw ExportError.failed("Couldn't prepare the video.")
        }
        try cv.insertTimeRange(range, of: srcV, at: .zero)
        cv.preferredTransform = transform
        if let a = srcA, let ca = comp.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) {
            try? ca.insertTimeRange(range, of: a, at: .zero)
        }

        // everything that doesn't change from frame to frame is prepared once
        let oriented = natural.applying(transform)
        let ar = abs(oriented.width) / max(1, abs(oriented.height))
        let vr = p.videoRect(ar)
        let canvas = CGRect(x: 0, y: 0, width: RW, height: RH)
        let ciRect = CGRect(x: vr.minX, y: RH - vr.maxY, width: vr.width, height: vr.height)   // CI's origin is bottom-left
        let overlay = Render.overlay(p).cgImage.map { CIImage(cgImage: $0) } ?? CIImage.empty()
        let coverCI = p.coverFirst ? Render.cover(p).cgImage.map { CIImage(cgImage: $0) } : nil
        let maskCI = p.radius > 0 ? Render.mask(vr, radius: p.radius).cgImage.map { CIImage(cgImage: $0) } : nil
        let mode = p.bgMode
        let solid: CIImage = {
            let c = mode == "white" ? UIColor.white : (mode == "custom" ? UIColor(hex: p.bgColor) : UIColor.black)
            return CIImage(color: CIColor(color: c)).cropped(to: canvas)
        }()
        let fpsValue: Float = p.fps == 1 ? 60 : (p.fps == 2 ? min(60, max(1, rate)) : 30)
        let frame = CMTime(value: 1, timescale: CMTimeScale(fpsValue.rounded()))

        let vc = AVMutableVideoComposition(asset: comp) { request in
            if let cover = coverCI, request.compositionTime.seconds < frame.seconds * 0.5 {
                request.finish(with: cover, context: nil)
                return
            }
            var src = request.sourceImage
            let e = src.extent
            src = src.transformed(by: CGAffineTransform(translationX: -e.minX, y: -e.minY))
            let bg = mode == "blur" ? Render.blurredBackgroundCI(src) : solid
            let placed = src.transformed(by: CGAffineTransform(scaleX: ciRect.width / max(1, e.width), y: ciRect.height / max(1, e.height)))
                .transformed(by: CGAffineTransform(translationX: ciRect.minX, y: ciRect.minY))
            var out: CIImage
            if let m = maskCI {
                out = placed.applyingFilter("CIBlendWithMask", parameters: [kCIInputBackgroundImageKey: bg, kCIInputMaskImageKey: m])
            } else {
                out = placed.cropped(to: ciRect).composited(over: bg)
            }
            out = overlay.composited(over: out).cropped(to: canvas)
            request.finish(with: out, context: nil)
        }
        vc.renderSize = CGSize(width: RW, height: RH)
        vc.frameDuration = frame

        let out = FileManager.default.temporaryDirectory.appendingPathComponent("reel-\(Int(Date().timeIntervalSince1970)).mp4")
        try? FileManager.default.removeItem(at: out)
        let preset = p.quality == 2 ? AVAssetExportPresetMediumQuality : AVAssetExportPresetHighestQuality
        guard let s = AVAssetExportSession(asset: comp, presetName: preset) else { throw ExportError.failed("Export isn't available.") }
        s.outputURL = out
        s.outputFileType = .mp4
        s.videoComposition = vc
        s.shouldOptimizeForNetworkUse = true
        session = s
        timer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { _ in progress(s.progress) }
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in s.exportAsynchronously { c.resume() } }
        timer?.invalidate()
        switch s.status {
        case .completed: return out
        case .cancelled: throw ExportError.failed("Export cancelled.")
        default: throw ExportError.failed(s.error?.localizedDescription ?? "The export failed.")
        }
    }

    /// Save to Photos. Returns the new photo's identifier (Instagram opens it directly).
    static func saveToPhotos(video: URL, cover: UIImage?) async throws -> String? {
        let st = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
        guard st == .authorized || st == .limited else {
            throw ExportError.failed("Reel Maker isn't allowed to add to your photos. Turn it on in Settings → Privacy → Photos.")
        }
        var id: String?
        try await PHPhotoLibrary.shared().performChanges {
            let r = PHAssetCreationRequest.forAsset()
            r.addResource(with: .video, fileURL: video, options: nil)
            id = r.placeholderForCreatedAsset?.localIdentifier
            if let c = cover, let data = c.pngData() {
                PHAssetCreationRequest.forAsset().addResource(with: .photo, data: data, options: nil)
            }
        }
        return id
    }
}
