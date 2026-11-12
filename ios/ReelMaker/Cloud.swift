import Foundation
import Security

/// Templates kept in a secret gist on your GitHub account: the same gist the Windows app uses.
final class Cloud: ObservableObject {
    static let clientID = "Ov23li12tITbgPr8zlzd"
    static let gistDescription = "Reel Maker templates (managed by the app)"
    static let index = "_reelmaker_index.json"

    @Published var login: String?
    @Published var busy = false
    @Published var message = ""
    struct TemplateRef: Identifiable { let name: String; let file: URL; var id: URL { file } }
    @Published var templates: [TemplateRef] = []

    private var token: String?
    private var gistID: String?

    static var folder: URL {
        let f = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0].appendingPathComponent("Templates")
        try? FileManager.default.createDirectory(at: f, withIntermediateDirectories: true)
        return f
    }

    init() {
        if let d = Keychain.read(), let j = try? JSONSerialization.jsonObject(with: d) as? [String: String] {
            token = j["token"]; login = j["login"]; gistID = j["gist"]
        }
        reloadLocal()
    }

    var signedIn: Bool { token != nil }

    private func save() {
        let j: [String: String] = ["token": token ?? "", "login": login ?? "", "gist": gistID ?? ""]
        if let d = try? JSONSerialization.data(withJSONObject: j) { Keychain.write(d) }
    }

    func signOut() { token = nil; login = nil; gistID = nil; Keychain.delete() }

    func reloadLocal() {
        let files = (try? FileManager.default.contentsOfDirectory(at: Cloud.folder, includingPropertiesForKeys: nil)) ?? []
        templates = files.filter { $0.pathExtension.lowercased() == "json" }.compactMap { u in
            guard let d = try? Data(contentsOf: u), let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return nil }
            return TemplateRef(name: (j["name"] as? String) ?? u.deletingPathExtension().lastPathComponent, file: u)
        }.sorted { $0.name.lowercased() < $1.name.lowercased() }
    }

    // MARK: http
    struct HTTPError: LocalizedError { let errorDescription: String? }

    private func request(_ method: String, _ url: String, json: Any? = nil, form: [String: String]? = nil, auth: Bool = true) async throws -> (Int, Data) {
        var r = URLRequest(url: URL(string: url)!)
        r.httpMethod = method
        r.setValue("application/json", forHTTPHeaderField: "Accept")
        if auth, let t = token {
            r.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization")
            r.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        }
        if let j = json {
            r.httpBody = try JSONSerialization.data(withJSONObject: j)
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        } else if let f = form {
            r.httpBody = f.map { "\($0.key)=\($0.value.addingPercentEncoding(withAllowedCharacters: .alphanumerics) ?? "")" }
                .joined(separator: "&").data(using: .utf8)
            r.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        }
        do {
            let (d, resp) = try await URLSession.shared.data(for: r)
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            if code == 401 && auth { signOut(); throw HTTPError(errorDescription: "Your GitHub sign-in expired. Sign in again.") }
            return (code, d)
        } catch let e as HTTPError { throw e } catch {
            throw HTTPError(errorDescription: "Couldn't reach GitHub. Check your connection.")
        }
    }

    private func api(_ method: String, _ path: String, json: Any? = nil) async throws -> Any {
        let (code, d) = try await request(method, "https://api.github.com" + path, json: json)
        let obj = try? JSONSerialization.jsonObject(with: d)
        if code >= 400 {
            throw HTTPError(errorDescription: "GitHub: " + (((obj as? [String: Any])?["message"] as? String) ?? "error \(code)"))
        }
        return obj ?? [:]
    }

    // MARK: sign-in (device flow)
    struct DeviceCode { let user: String; let verify: URL; let device: String; let interval: Int; let expires: Int }

    func startSignIn() async throws -> DeviceCode {
        let (_, d) = try await request("POST", "https://github.com/login/device/code",
                                       form: ["client_id": Cloud.clientID, "scope": "gist"], auth: false)
        guard let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any], let dc = j["device_code"] as? String,
              let uc = j["user_code"] as? String else { throw HTTPError(errorDescription: "GitHub didn't start the sign-in.") }
        return DeviceCode(user: uc, verify: URL(string: j["verification_uri"] as? String ?? "https://github.com/login/device")!,
                          device: dc, interval: (j["interval"] as? Int) ?? 5, expires: (j["expires_in"] as? Int) ?? 900)
    }

    func finishSignIn(_ c: DeviceCode) async throws {
        var interval = c.interval
        let end = Date().addingTimeInterval(TimeInterval(c.expires))
        while Date() < end {
            try await Task.sleep(nanoseconds: UInt64(interval) * 1_000_000_000)
            let (_, d) = try await request("POST", "https://github.com/login/oauth/access_token", form: [
                "client_id": Cloud.clientID, "device_code": c.device,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"], auth: false)
            let j = (try? JSONSerialization.jsonObject(with: d) as? [String: Any]) ?? [:]
            if let t = j["access_token"] as? String {
                token = t
                let me = try await api("GET", "/user") as? [String: Any]
                await MainActor.run { self.login = me?["login"] as? String }
                gistID = nil
                save()
                return
            }
            switch j["error"] as? String {
            case "authorization_pending": continue
            case "slow_down": interval += 5
            case "access_denied": throw HTTPError(errorDescription: "Sign-in was cancelled on GitHub.")
            case "expired_token": throw HTTPError(errorDescription: "The code expired. Try again.")
            default: throw HTTPError(errorDescription: "GitHub refused the sign-in.")
            }
        }
        throw HTTPError(errorDescription: "The code expired. Try again.")
    }

    // MARK: the templates gist
    private func gist() async throws -> [String: Any] {
        if let id = gistID, !id.isEmpty, let g = try? await api("GET", "/gists/\(id)") as? [String: Any] { return g }
        var page = 1
        while true {
            let list = try await api("GET", "/gists?per_page=100&page=\(page)") as? [[String: Any]] ?? []
            for g in list where (g["description"] as? String) == Cloud.gistDescription
                && ((g["files"] as? [String: Any])?[Cloud.index] != nil) {
                gistID = g["id"] as? String; save()
                return try await api("GET", "/gists/\(gistID!)") as? [String: Any] ?? [:]
            }
            if list.count < 100 { break }
            page += 1
        }
        let g = try await api("POST", "/gists", json: ["description": Cloud.gistDescription, "public": false,
                                                        "files": [Cloud.index: ["content": "{\"templates\": {}}"]]]) as? [String: Any] ?? [:]
        gistID = g["id"] as? String; save()
        return g
    }

    private func fileText(_ f: [String: Any]) async throws -> String {
        if (f["truncated"] as? Bool) == true || f["content"] == nil, let raw = f["raw_url"] as? String {
            let (_, d) = try await request("GET", raw)
            return String(decoding: d, as: UTF8.self)
        }
        return f["content"] as? String ?? ""
    }

    private func stamp(_ u: URL) -> Double {
        guard let d = try? Data(contentsOf: u), let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return 0 }
        return (j["saved_at"] as? NSNumber)?.doubleValue ?? 0
    }

    /// Two-way: newer templates win on each side. (Deleting is done on the PC.)
    func sync() async throws -> String {
        let g = try await gist()
        let files = g["files"] as? [String: [String: Any]] ?? [:]
        var idx: [String: Any] = [:]
        if let f = files[Cloud.index], let j = try? JSONSerialization.jsonObject(with: Data(try await fileText(f).utf8)) as? [String: Any] {
            idx = j["templates"] as? [String: Any] ?? [:]
        }
        var down = 0, up = 0
        var uploads: [String: Any] = [:]
        let local = Dictionary(uniqueKeysWithValues: ((try? FileManager.default.contentsOfDirectory(at: Cloud.folder, includingPropertiesForKeys: nil)) ?? [])
            .filter { $0.pathExtension.lowercased() == "json" }.map { ($0.lastPathComponent, $0) })
        for (name, f) in files where name != Cloud.index && name.lowercased().hasSuffix(".json") {
            let rs = (idx[name] as? NSNumber)?.doubleValue ?? 0
            let lu = local[name]
            if lu == nil || rs > stamp(lu!) + 0.5 {
                try Data(try await fileText(f).utf8).write(to: Cloud.folder.appendingPathComponent(name))
                down += 1
            }
        }
        for (name, u) in local {
            let ls = stamp(u)
            if files[name] == nil || ls > ((idx[name] as? NSNumber)?.doubleValue ?? 0) + 0.5 {
                uploads[name] = ["content": String(decoding: try Data(contentsOf: u), as: UTF8.self)]
                idx[name] = ls
                up += 1
            }
        }
        if !uploads.isEmpty, let id = gistID {
            uploads[Cloud.index] = ["content": String(decoding: try JSONSerialization.data(withJSONObject: ["templates": idx]), as: UTF8.self)]
            _ = try await api("PATCH", "/gists/\(id)", json: ["files": uploads])
        }
        await MainActor.run { self.reloadLocal() }
        return "Synced: \(down) downloaded, \(up) uploaded."
    }

    static func fileName(_ name: String) -> String {
        let safe = name.replacingOccurrences(of: #"[\\/:*?"<>|]+"#, with: "_", options: .regularExpression)
            .trimmingCharacters(in: .whitespaces)
        return (safe.isEmpty ? "template" : safe) + ".json"
    }
}

enum Keychain {
    static let service = "com.aduseii.reelmaker.github"
    static func write(_ d: Data) {
        delete()
        SecItemAdd([kSecClass: kSecClassGenericPassword, kSecAttrService: service, kSecValueData: d,
                    kSecAttrAccessible: kSecAttrAccessibleAfterFirstUnlock] as CFDictionary, nil)
    }
    static func read() -> Data? {
        var out: AnyObject?
        let st = SecItemCopyMatching([kSecClass: kSecClassGenericPassword, kSecAttrService: service,
                                      kSecReturnData: true, kSecMatchLimit: kSecMatchLimitOne] as CFDictionary, &out)
        return st == errSecSuccess ? out as? Data : nil
    }
    static func delete() {
        SecItemDelete([kSecClass: kSecClassGenericPassword, kSecAttrService: service] as CFDictionary)
    }
}
