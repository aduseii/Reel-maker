import UIKit
import CoreImage
import CoreImage.CIFilterBuiltins

enum Render {
    static func renderer(_ size: CGSize, opaque: Bool = false) -> UIGraphicsImageRenderer {
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1
        fmt.opaque = opaque
        fmt.preferredRange = .standard
        return UIGraphicsImageRenderer(size: size, format: fmt)
    }

    /// Draw one image layer as sharply as possible: pixel for pixel when shown within 2% of its own
    /// size, otherwise one high-quality resize, always on whole pixels.
    static func drawImageLayer(_ l: Layer, in ctx: CGContext) {
        guard let img = l.image, let cg = img.cgImage else { return }
        let r = l.rect
        var w = r.width.rounded(), h = r.height.rounded()
        let iw = CGFloat(cg.width), ih = CGFloat(cg.height)
        if abs(w - iw) <= max(1, iw * 0.02) && abs(h - ih) <= max(1, ih * 0.02) { w = iw; h = ih }
        let dst = CGRect(x: (r.midX - w / 2).rounded(), y: (r.midY - h / 2).rounded(), width: w, height: h)
        ctx.saveGState()
        ctx.setAlpha(l.opacity)
        ctx.interpolationQuality = .high
        img.draw(in: dst)
        ctx.restoreGState()
    }

    static func drawLayers(_ layers: [Layer], in ctx: CGContext, editingID: UUID? = nil) {
        for l in layers {
            if l.kind == .text { TextLayout.draw(l, in: ctx) } else { drawImageLayer(l, in: ctx) }
        }
    }

    /// All layers on a transparent 1080 × 1920 image (what the export lays over the video).
    static func overlay(_ p: Project) -> UIImage {
        renderer(CGSize(width: RW, height: RH)).image { c in drawLayers(p.layers, in: c.cgContext) }
    }

    /// The cover: the chosen 9:16 window of a frame, plus layers and title if wanted.
    static func cover(_ p: Project, scale: CGFloat = 1) -> UIImage {
        renderer(CGSize(width: RW * scale, height: RH * scale), opaque: true).image { c in
            let ctx = c.cgContext
            UIColor.black.setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: RW * scale, height: RH * scale))
            ctx.scaleBy(x: scale, y: scale)
            if let f = p.coverFrame, let cg = f.cgImage {
                let crop = p.coverCrop(CGSize(width: cg.width, height: cg.height)).integral
                if let part = cg.cropping(to: crop) {
                    ctx.interpolationQuality = .high
                    UIImage(cgImage: part).draw(in: CGRect(x: 0, y: 0, width: RW, height: RH))
                }
            }
            if p.coverIncludeLayers { drawLayers(p.layers, in: ctx) }
            let text = p.coverTitle.trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty {
                let z = p.zoneRect
                var t = Layer.newText(text)
                t.style = "plain"; t.shadow = true; t.weight = 900; t.size = p.coverTitleSize
                t.color = p.coverTitleColor; t.w = z.width - 40; t.x = z.midX
                t.y = z.minY + (z.height - t.height) * p.coverTitleY / 100
                TextLayout.draw(t, in: ctx)
            }
        }
    }

    /// The blurred, dimmed background made from a frame, at 1080 × 1920 (CIImage coordinates).
    static func blurredBackgroundCI(_ src: CIImage) -> CIImage {
        let e = src.extent
        let s = max(RW / e.width, RH / e.height) * 1.08
        let moved = src.transformed(by: CGAffineTransform(translationX: -e.minX, y: -e.minY))
            .transformed(by: CGAffineTransform(scaleX: s, y: s))
        let placed = moved.transformed(by: CGAffineTransform(translationX: (RW - e.width * s) / 2, y: (RH - e.height * s) / 2))
        let canvas = CGRect(x: 0, y: 0, width: RW, height: RH)
        let blurred = placed.clampedToExtent().applyingGaussianBlur(sigma: 11 * s).cropped(to: canvas)
        let dim = CIImage(color: CIColor(red: 0, green: 0, blue: 0, alpha: 90 / 255)).cropped(to: canvas)
        return dim.composited(over: blurred)
    }

    static func blurredBackground(_ src: CIImage, context: CIContext) -> CGImage? {
        context.createCGImage(blurredBackgroundCI(src), from: CGRect(x: 0, y: 0, width: RW, height: RH))
    }

    /// A white rounded rectangle on transparent, used to round the video's corners.
    static func mask(_ rect: CGRect, radius: CGFloat) -> UIImage {
        renderer(CGSize(width: RW, height: RH)).image { _ in
            UIColor.white.setFill()
            UIBezierPath(roundedRect: rect, cornerRadius: radius).fill()
        }
    }
}
