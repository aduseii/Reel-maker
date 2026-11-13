import SwiftUI
import UIKit
import AVFoundation

/// The reel is laid out on a 1080 × 1920 canvas, the same coordinates the Windows app uses,
/// so templates move between the two unchanged.
let RW: CGFloat = 1080
let RH: CGFloat = 1920

let PRESETS: [(String, [CGFloat]?)] = [
    ("Level 1 — clear of all Instagram UI", [250, 450, 120, 120]),
    ("Level 2 — looser", [160, 340, 60, 60]),
    ("Profile grid crop (3:4)", [240, 240, 0, 0]),
    ("Full frame", [0, 0, 0, 0]),
    ("Custom", nil),
]

enum LayerKind: String { case text, image }

struct Layer: Identifiable, Equatable {
    var id = UUID()
    var kind: LayerKind
    var x: CGFloat = RW / 2
    var y: CGFloat = RH / 2
    var w: CGFloat = 760
    var opacity: CGFloat = 1
    var attachGap: CGFloat? = nil      // sits this far above the video and follows it

    // text
    var text = "Your text here"
    var family = "Inter Display"
    var weight = 700
    var italic = false
    var size: CGFloat = 64
    var color = "#FFFFFFFF"            // its alpha is the text's own opacity (words and emoji)
    var align = "center"
    var style = "box"                  // plain | box | highlight
    var boxColor = "#FF000000"
    var boxAlpha: CGFloat = 0.55
    var radius: CGFloat = 28
    var pad: CGFloat = 30
    var spacing: CGFloat = 1.18
    var shadow = false
    var fromPost = false               // gets the post's text on an X import
    var fitOneLine = false             // one-line text: bigger and placed above the video
    var fitBase: CGFloat? = nil        // the box's own size while a bigger one-line size shows

    // image
    var name = "image.png"
    var imageData: Data? = nil         // the original file, kept byte for byte
    var raster: Data? = nil            // a PNG copy of an SVG logo (made by the Windows app)
    var svg = false
    var image: UIImage? = nil

    static func newText(_ t: String = "Your text here") -> Layer { var l = Layer(kind: .text); l.text = t; return l }

    var baseSize: CGFloat { fitBase ?? size }

    var height: CGFloat {
        switch kind {
        case .text:
            let lay = TextLayout.layout(self)
            return CGFloat(lay.lines.count) * lay.lh + 2 * (style == "box" ? pad : 0)
        case .image:
            guard let img = image, img.size.width > 0 else { return w }
            return w * img.size.height / img.size.width
        }
    }

    var rect: CGRect {
        kind == .text ? CGRect(x: x - w / 2, y: y, width: w, height: height)
                      : CGRect(x: x - w / 2, y: y - height / 2, width: w, height: height)
    }

    mutating func moveTo(left: CGFloat, top: CGFloat) {
        x = left + w / 2
        y = kind == .text ? top : top + height / 2
    }

    var label: String {
        if kind == .image { return name }
        let t = text.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
        return t.isEmpty ? "Empty text" : (t.count > 30 ? String(t.prefix(30)) + "…" : t)
    }

    // MARK: template JSON (same keys as the Windows app)
    func toDict() -> [String: Any] {
        if kind == .image {
            var d: [String: Any] = ["kind": "image", "name": name, "w": w, "x": x, "y": y, "opacity": opacity,
                                    "svg": svg, "png": (imageData ?? image?.pngData() ?? Data()).base64EncodedString()]
            d["attach_gap"] = attachGap ?? NSNull()
            if let r = raster { d["raster"] = r.base64EncodedString() }
            return d
        }
        var d: [String: Any] = ["kind": "text", "text": text, "family": family, "weight": weight, "italic": italic, "size": baseSize,
                                "align": align, "style": style, "box_alpha": boxAlpha, "radius": radius, "pad": pad,
                                "spacing": spacing, "shadow": shadow, "opacity": opacity, "w": w, "x": x, "y": y,
                                "from_post": fromPost, "fit_one_line": fitOneLine, "color": color, "box_color": boxColor]
        d["attach_gap"] = attachGap ?? NSNull()
        return d
    }

    static func fromDict(_ d: [String: Any]) -> Layer? {
        func num(_ k: String, _ def: CGFloat) -> CGFloat { (d[k] as? NSNumber).map { CGFloat($0.doubleValue) } ?? def }
        if (d["kind"] as? String) == "image" {
            var l = Layer(kind: .image)
            l.name = d["name"] as? String ?? "image.png"
            l.svg = d["svg"] as? Bool ?? false
            let data = (d["png"] as? String).flatMap { Data(base64Encoded: $0) }
            l.imageData = data
            l.raster = (d["raster"] as? String).flatMap { Data(base64Encoded: $0) }
            l.image = (l.svg ? l.raster.flatMap { UIImage(data: $0) } : nil) ?? data.flatMap { UIImage(data: $0) }
            guard l.image != nil else { return nil }
            l.w = num("w", 240); l.x = num("x", RW / 2); l.y = num("y", RH / 2); l.opacity = num("opacity", 1)
            l.attachGap = (d["attach_gap"] as? NSNumber).map { CGFloat($0.doubleValue) }
            return l
        }
        var l = Layer(kind: .text)
        l.text = d["text"] as? String ?? ""
        l.family = d["family"] as? String ?? "Inter Display"
        l.weight = (d["weight"] as? NSNumber)?.intValue ?? 700
        l.italic = d["italic"] as? Bool ?? false
        l.size = num("size", 64)
        l.align = d["align"] as? String ?? "center"
        l.style = d["style"] as? String ?? "box"
        l.boxAlpha = num("box_alpha", 0.55); l.radius = num("radius", 28); l.pad = num("pad", 30)
        l.spacing = num("spacing", 1.18); l.opacity = num("opacity", 1)
        l.shadow = d["shadow"] as? Bool ?? false
        l.w = num("w", 760); l.x = num("x", RW / 2); l.y = num("y", RH / 2)
        l.fromPost = d["from_post"] as? Bool ?? false
        l.fitOneLine = d["fit_one_line"] as? Bool ?? false
        l.color = d["color"] as? String ?? "#FFFFFFFF"
        l.boxColor = d["box_color"] as? String ?? "#FF000000"
        l.attachGap = (d["attach_gap"] as? NSNumber).map { CGFloat($0.doubleValue) }
        return l
    }
}

extension UIColor {
    /// "#RRGGBB" or Qt's "#AARRGGBB".
    convenience init(hex: String) {
        var s = hex.trimmingCharacters(in: .whitespaces)
        if s.hasPrefix("#") { s.removeFirst() }
        var v: UInt64 = 0
        Scanner(string: s).scanHexInt64(&v)
        let a, r, g, b: CGFloat
        if s.count == 8 {
            a = CGFloat((v >> 24) & 0xFF) / 255; r = CGFloat((v >> 16) & 0xFF) / 255
            g = CGFloat((v >> 8) & 0xFF) / 255; b = CGFloat(v & 0xFF) / 255
        } else {
            a = 1; r = CGFloat((v >> 16) & 0xFF) / 255; g = CGFloat((v >> 8) & 0xFF) / 255; b = CGFloat(v & 0xFF) / 255
        }
        self.init(red: r, green: g, blue: b, alpha: a)
    }

    var hexARGB: String {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        getRed(&r, green: &g, blue: &b, alpha: &a)
        func c(_ x: CGFloat) -> Int { Int((min(max(x, 0), 1) * 255).rounded()) }
        return String(format: "#%02X%02X%02X%02X", c(a), c(r), c(g), c(b))
    }
}

/// The opacity stored in an "#AARRGGBB" colour (1 for "#RRGGBB").
func hexAlpha(_ hex: String) -> CGFloat {
    var a: CGFloat = 0
    UIColor(hex: hex).getRed(nil, green: nil, blue: nil, alpha: &a)
    return a
}

/// The same colour with a different opacity.
func hexWithAlpha(_ hex: String, _ alpha: CGFloat) -> String {
    UIColor(hex: hex).withAlphaComponent(min(max(alpha, 0), 1)).hexARGB
}

/// Binds a SwiftUI ColorPicker to a hex string.
func hexBinding(_ get: @escaping () -> String, _ set: @escaping (String) -> Void) -> Binding<Color> {
    Binding(get: { Color(UIColor(hex: get())) }, set: { set(UIColor($0).hexARGB) })
}
