import UIKit

/// Fixed-width text boxes: the width never grows, long text wraps onto new lines.
/// The same rules as the Windows app, so a template's text breaks in the same places.
enum TextLayout {
    enum Token {
        case word(String, CGFloat)
        case space(CGFloat)
        case emoji(String, CGFloat)
        var width: CGFloat {
            switch self { case .word(_, let w), .space(let w), .emoji(_, let w): return w }
        }
        var isSpace: Bool { if case .space = self { return true }; return false }
    }

    struct Result {
        var lines: [[Token]]
        var widths: [CGFloat]
        var lh: CGFloat
        var asc: CGFloat
        var desc: CGFloat
        var maxw: CGFloat
    }

    private static var cache: [String: Result] = [:]

    static func font(_ l: Layer) -> UIFont {
        let names = [400: "InterDisplay-Regular", 500: "InterDisplay-Medium", 600: "InterDisplay-SemiBold",
                     700: "InterDisplay-Bold", 800: "InterDisplay-ExtraBold", 900: "InterDisplay-Black"]
        let w = [400, 500, 600, 700, 800, 900].min(by: { abs($0 - l.weight) < abs($1 - l.weight) }) ?? 700
        if l.family != "Inter Display", let f = UIFont(name: l.family, size: l.size) { return f }
        return UIFont(name: names[w] ?? "InterDisplay-Bold", size: l.size)
            ?? UIFont.systemFont(ofSize: l.size, weight: w >= 700 ? .bold : .regular)
    }

    static func emojiFont(_ size: CGFloat) -> UIFont {
        UIFont(name: "AppleColorEmoji", size: size) ?? UIFont.systemFont(ofSize: size)
    }

    static func innerPad(_ l: Layer) -> CGFloat {
        l.style == "box" ? l.pad : (l.style == "highlight" ? l.size * 0.32 : 0)
    }

    static func isEmoji(_ c: Character) -> Bool {
        let sc = Array(c.unicodeScalars)
        guard let f = sc.first else { return false }
        if f.properties.isEmojiPresentation { return true }
        if f.properties.isEmoji && sc.contains(where: { $0.value == 0xFE0F || $0.value == 0x200D || $0.value == 0x20E3 }) { return true }
        return false
    }

    static func measure(_ s: String, _ font: UIFont) -> CGFloat {
        (s as NSString).size(withAttributes: [.font: font]).width
    }

    static func layout(_ l: Layer) -> Result {
        let key = "\(l.text)|\(l.family)|\(l.weight)|\(l.size)|\(l.w)|\(l.style)|\(l.pad)|\(l.spacing)"
        if let r = cache[key] { return r }
        let f = font(l)
        let ew = l.size * 1.12
        let maxw = max(20, l.w - 2 * innerPad(l))
        let spaceW = measure(" ", f)

        var tokens: [Token?] = []   // nil = line break
        var word = ""
        func flush() { if !word.isEmpty { tokens.append(.word(word, measure(word, f))); word = "" } }
        for c in l.text {
            if c == "\n" || c == "\r\n" { flush(); tokens.append(nil) }
            else if c == " " || c == "\t" { flush(); tokens.append(.space(spaceW)) }
            else if isEmoji(c) { flush(); tokens.append(.emoji(String(c), ew)) }
            else { word.append(c) }
        }
        flush()

        var lines: [[Token]] = [[]]
        var x: CGFloat = 0
        func newline() {
            while let last = lines[lines.count - 1].last, last.isSpace { lines[lines.count - 1].removeLast() }
            lines.append([]); x = 0
        }
        for t in tokens {
            guard let t = t else { newline(); continue }
            if case .space(let sw) = t {
                if x > 0 { lines[lines.count - 1].append(t); x += sw }
                continue
            }
            var tok = t
            if x > 0 && x + tok.width > maxw { newline() }
            if case .word(let s, let tw) = tok, tw > maxw {          // one very long word: break it
                var chunk = ""
                for ch in s {
                    if measure(chunk + String(ch), f) > maxw && !chunk.isEmpty {
                        lines[lines.count - 1].append(.word(chunk, measure(chunk, f)))
                        newline(); chunk = ""
                    }
                    chunk.append(ch)
                }
                tok = .word(chunk, measure(chunk, f))
            }
            lines[lines.count - 1].append(tok)
            x += tok.width
        }
        while let last = lines[lines.count - 1].last, last.isSpace { lines[lines.count - 1].removeLast() }
        let widths = lines.map { $0.reduce(0) { $0 + $1.width } }
        let r = Result(lines: lines, widths: widths, lh: l.size * l.spacing, asc: f.ascender, desc: -f.descender, maxw: maxw)
        if cache.count > 400 { cache.removeAll() }
        cache[key] = r
        return r
    }

    /// Draw a text layer into a UIKit context laid out in reel pixels (top-left origin).
    static func draw(_ l: Layer, in ctx: CGContext, hideWords: Bool = false) {
        let lay = layout(l)
        let r = l.rect
        let ip = innerPad(l)
        let top = r.minY + (l.style == "box" ? l.pad : 0)
        let left = r.minX + ip
        ctx.saveGState()
        ctx.setAlpha(l.opacity)
        ctx.beginTransparencyLayer(auxiliaryInfo: nil)
        let bc = UIColor(hex: l.boxColor).withAlphaComponent(l.boxAlpha)
        if l.style == "box" {
            bc.setFill()
            UIBezierPath(roundedRect: r, cornerRadius: l.radius).fill()
        }
        func lineX(_ i: Int) -> CGFloat {
            if l.align == "left" { return left }
            if l.align == "right" { return left + lay.maxw - lay.widths[i] }
            return left + (lay.maxw - lay.widths[i]) / 2
        }
        if l.style == "highlight" {
            let hp = l.size * 0.32
            let path = CGMutablePath()
            for (i, ln) in lay.lines.enumerated() where !ln.isEmpty {
                let rr = CGRect(x: lineX(i) - hp, y: top + CGFloat(i) * lay.lh - lay.lh * 0.02,
                                width: lay.widths[i] + 2 * hp, height: lay.lh * 1.04)
                let rad = min(l.radius, lay.lh / 2)
                path.addPath(UIBezierPath(roundedRect: rr, cornerRadius: rad).cgPath)
            }
            ctx.addPath(path)
            ctx.setFillColor(bc.cgColor)
            ctx.fillPath(using: .winding)
        }
        if !hideWords {
            let f = font(l)
            let textH = lay.asc + lay.desc
            var passes: [(UIColor, CGFloat)] = l.shadow ? [(UIColor(white: 0, alpha: 120 / 255), l.size * 0.05)] : []
            passes.append((UIColor(hex: l.color), 0))
            for (color, off) in passes {
                for (i, ln) in lay.lines.enumerated() {
                    var x = lineX(i)
                    let lineTop = top + CGFloat(i) * lay.lh
                    let base = lineTop + (lay.lh - textH) / 2 + lay.asc
                    for t in ln {
                        switch t {
                        case .word(let s, _):
                            (s as NSString).draw(at: CGPoint(x: x + off, y: base - f.ascender + off),
                                                 withAttributes: [.font: f, .foregroundColor: color])
                        case .emoji(let e, let w) where off == 0:
                            let es = l.size * 1.02
                            let ef = emojiFont(es * 0.84)
                            let sz = (e as NSString).size(withAttributes: [.font: ef])
                            (e as NSString).draw(at: CGPoint(x: x + (w - sz.width) / 2, y: lineTop + (lay.lh - sz.height) / 2),
                                                 withAttributes: [.font: ef])
                        default: break
                        }
                        x += t.width
                    }
                }
            }
        }
        ctx.endTransparencyLayer()
        ctx.restoreGState()
    }
}
