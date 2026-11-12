import Foundation
import JavaScriptCore

/// Import a video and its text from an X (Twitter) post link, using X's public embed data
/// (the same data X's own embedded-post widget loads).
enum XImport {
    struct Post {
        var id: String
        var caption: String
        var user: String
        var videos: [URL]
    }

    enum XError: LocalizedError {
        case badLink, noVideo, unavailable, network, failed(String)
        var errorDescription: String? {
            switch self {
            case .badLink: return "That doesn't look like a link to an X post."
            case .noVideo: return "That post doesn't have a video."
            case .unavailable: return "That post isn't available. It may be deleted, from a protected account, or marked sensitive (X only shows those to signed-in people)."
            case .network: return "Couldn't reach X. Check your connection and try again."
            case .failed(let s): return s
            }
        }
    }

    static let linkPattern = try! NSRegularExpression(
        pattern: #"https?://(?:www\.|mobile\.|m\.)?(?:x|twitter|fxtwitter|vxtwitter|fixupx|fixvx)\.com/(?:[A-Za-z0-9_]{1,30}|i(?:/web)?)/status(?:es)?/(\d{5,25})(?:/video/(\d))?"#,
        options: [.caseInsensitive])

    static func postID(in text: String) -> (String, Int?)? {
        let ns = text as NSString
        guard let m = linkPattern.firstMatch(in: text, range: NSRange(location: 0, length: ns.length)) else { return nil }
        let id = ns.substring(with: m.range(at: 1))
        let idx = m.range(at: 2).location != NSNotFound ? Int(ns.substring(with: m.range(at: 2))) : nil
        return (id, idx)
    }

    /// The embed widget's token for a post id.
    static func token(_ id: String) -> String {
        let js = JSContext()
        let v = js?.evaluateScript("((Number('\(id)') / 1e15) * Math.PI).toString(36).replace(/(0+|\\.)/g, '')")
        return v?.toString() ?? "0"
    }

    static func cleanCaption(_ s: String) -> String {
        var t = s.replacingOccurrences(of: "&amp;", with: "&").replacingOccurrences(of: "&lt;", with: "<")
            .replacingOccurrences(of: "&gt;", with: ">").replacingOccurrences(of: "&quot;", with: "\"")
            .replacingOccurrences(of: "&#39;", with: "'").replacingOccurrences(of: "\r\n", with: "\n")
        t = t.replacingOccurrences(of: #"\s*https?://t\.co/\w+"#, with: "", options: .regularExpression)
        t = t.trimmingCharacters(in: .whitespacesAndNewlines)
        t = t.replacingOccurrences(of: #"^(?:@\w{1,15}\s+)+(?=\S)"#, with: "", options: .regularExpression)
        t = t.split(separator: "\n", omittingEmptySubsequences: false)
            .map { $0.replacingOccurrences(of: #"\s+$"#, with: "", options: .regularExpression) }.joined(separator: "\n")
        t = t.replacingOccurrences(of: #"[ \t]{2,}"#, with: " ", options: .regularExpression)
        t = t.replacingOccurrences(of: #"\n{3,}"#, with: "\n\n", options: .regularExpression)
        return t.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func fetch(_ id: String) async throws -> Post {
        var c = URLComponents(string: "https://cdn.syndication.twimg.com/tweet-result")!
        c.queryItems = [URLQueryItem(name: "id", value: id), URLQueryItem(name: "token", value: token(id)),
                        URLQueryItem(name: "lang", value: "en")]
        let data: Data, resp: URLResponse
        do { (data, resp) = try await URLSession.shared.data(from: c.url!) } catch { throw XError.network }
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard code == 200, let d = try? JSONSerialization.jsonObject(with: data) as? [String: Any], !d.isEmpty else {
            throw code == 404 || code == 200 ? XError.unavailable : XError.failed("X answered with an error (\(code)). Try again in a minute.")
        }
        if (d["__typename"] as? String) == "TweetTombstone" { throw XError.unavailable }
        var media = d["mediaDetails"] as? [[String: Any]] ?? []
        if media.isEmpty, let q = d["quoted_tweet"] as? [String: Any] { media = q["mediaDetails"] as? [[String: Any]] ?? [] }
        let videos: [URL] = media.compactMap { m in
            guard let vi = m["video_info"] as? [String: Any], let vs = vi["variants"] as? [[String: Any]] else { return nil }
            let mp4 = vs.filter { ($0["content_type"] as? String) == "video/mp4" }
            let best = mp4.max { (($0["bitrate"] as? NSNumber)?.intValue ?? 0) < (($1["bitrate"] as? NSNumber)?.intValue ?? 0) }
            return (best?["url"] as? String).flatMap(URL.init(string:))
        }
        guard !videos.isEmpty else { throw XError.noVideo }
        let user = (d["user"] as? [String: Any])?["screen_name"] as? String ?? "post"
        return Post(id: id, caption: cleanCaption(d["text"] as? String ?? ""), user: user, videos: videos)
    }

    static func download(_ url: URL, name: String, progress: @escaping (Double) -> Void) async throws -> URL {
        let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("From X")
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let dest = folder.appendingPathComponent(name + ".mp4")
        let (tmp, resp): (URL, URLResponse)
        do {
            (tmp, resp) = try await URLSession.shared.download(from: url, delegate: ProgressDelegate(progress))
        } catch { throw XError.network }
        guard (resp as? HTTPURLResponse)?.statusCode == 200 else { throw XError.failed("The video didn't download.") }
        try? FileManager.default.removeItem(at: dest)
        try FileManager.default.moveItem(at: tmp, to: dest)
        return dest
    }

    final class ProgressDelegate: NSObject, URLSessionTaskDelegate {
        let cb: (Double) -> Void
        var obs: NSKeyValueObservation?
        init(_ cb: @escaping (Double) -> Void) { self.cb = cb }
        func urlSession(_ session: URLSession, didCreateTask task: URLSessionTask) {
            obs = task.progress.observe(\.fractionCompleted) { [cb] p, _ in DispatchQueue.main.async { cb(p.fractionCompleted) } }
        }
    }
}
