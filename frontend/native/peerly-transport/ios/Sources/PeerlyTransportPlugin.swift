import Foundation
import WebKit
import Capacitor

/// Fixed API origin, native HttpOnly jar, no token/header/error reflection to JS.
@objc(PeerlyTransportPlugin)
public final class PeerlyTransportPlugin: CAPPlugin, CAPBridgedPlugin, URLSessionDataDelegate {
    public let identifier = "PeerlyTransportPlugin"
    public let jsName = "PeerlyTransport"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "configuration", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "advance", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "start", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "cancel", returnType: CAPPluginReturnPromise)
    ]
    private let maxBytes = 16 * 1024 * 1024
    private let maxStream = 1024 * 1024
    private let requestHeaders = Set(["accept", "content-type", "x-csrf-token", "idempotency-key", "if-match", "last-event-id", "traceparent", "x-action-id"])
    private let responseHeaders = ["content-type", "retry-after", "etag", "cache-control", "x-request-id"]
    private var epoch = UUID().uuidString.lowercased()
    private var origin: URL?
    private var jar: WKHTTPCookieStore?
    private var network: URLSession?
    // All state, delegates and cookie operations run on the main queue.
    private var active: [String: Work] = [:]
    private var cookieJobs: [(@escaping () -> Void) -> Void] = []
    private var cookieBusy = false

    private final class Work {
        let id: String
        let epoch: String
        let mode: String
        let path: String
        var task: URLSessionDataTask?
        var response: HTTPURLResponse?
        var body = Data()
        var streamBytes = 0
        init(_ id: String, _ epoch: String, _ mode: String, _ path: String) {
            self.id = id; self.epoch = epoch; self.mode = mode; self.path = path
        }
    }

    // URLSession retains its delegate: this weak proxy prevents retaining the plugin
    // and network tasks after its owning WebView has been released.
    private final class Delegate: NSObject, URLSessionDataDelegate {
        weak var owner: PeerlyTransportPlugin?
        init(_ owner: PeerlyTransportPlugin) { self.owner = owner }
        func urlSession(_ session: URLSession, task: URLSessionTask,
                        willPerformHTTPRedirection response: HTTPURLResponse,
                        newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
            completionHandler(nil)
        }
        func urlSession(_ session: URLSession, dataTask: URLSessionDataTask,
                        didReceive response: URLResponse,
                        completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
            guard let owner = owner else { completionHandler(.cancel); return }
            owner.urlSession(session, dataTask: dataTask, didReceive: response, completionHandler: completionHandler)
        }
        func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
            owner?.urlSession(session, dataTask: dataTask, didReceive: data)
        }
        func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
            owner?.urlSession(session, task: task, didCompleteWithError: error)
        }
    }

    public override func load() {
        guard let configured = Bundle.main.object(forInfoDictionaryKey: "PeerlyAPIOrigin") as? String,
              let parsed = URL(string: configured), let host = parsed.host,
              parsed.scheme == "https", parsed.user == nil, parsed.password == nil,
              parsed.query == nil, parsed.fragment == nil, parsed.path.isEmpty,
              configured == "https://" + host + (parsed.port.map { ":\($0)" } ?? ""),
              bridge?.config.loggingEnabled == false,
              let store = bridge?.webView?.configuration.websiteDataStore.httpCookieStore else { return }
        origin = parsed; jar = store
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpShouldSetCookies = false
        configuration.httpCookieStorage = nil
        configuration.urlCredentialStorage = nil
        configuration.waitsForConnectivity = false
        configuration.urlCache = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest = 35
        configuration.timeoutIntervalForResource = 90
        network = URLSession(configuration: configuration, delegate: Delegate(self), delegateQueue: .main)
    }

    private func enqueueCookie(_ job: @escaping (@escaping () -> Void) -> Void) {
        cookieJobs.append(job)
        nextCookie()
    }

    private func nextCookie() {
        guard !cookieBusy, !cookieJobs.isEmpty else { return }
        cookieBusy = true
        let job = cookieJobs.removeFirst()
        job { self.cookieBusy = false; self.nextCookie() }
    }

    @objc func configuration(_ call: CAPPluginCall) {
        guard network != nil, let origin = origin else { call.reject("native_transport_unavailable"); return }
        call.resolve(["appId": Bundle.main.bundleIdentifier ?? "",
                      "apiOrigin": origin.absoluteString,
                      "wakeUrl": Bundle.main.object(forInfoDictionaryKey: "PeerlyWakeURL") as? String ?? ""])
    }

    @objc func advance(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            guard self.network != nil, let jar = self.jar, let origin = self.origin else {
                call.reject("native_transport_unavailable"); return
            }
            self.enqueueCookie { done in
                self.active.values.forEach { $0.task?.cancel() }
                self.active.removeAll()
                self.epoch = UUID().uuidString.lowercased()
                let finish = { call.resolve(["epoch": self.epoch]); done() }
                if call.getBool("clearSession", false) {
                    jar.getAllCookies { cookies in
                        let group = DispatchGroup()
                        for cookie in cookies where cookie.domain == origin.host && cookie.name == "__Host-studymate_session" {
                            group.enter(); jar.delete(cookie) { group.leave() }
                        }
                        group.notify(queue: .main, execute: finish)
                    }
                } else { finish() }
            }
        }
    }

    @objc func cancel(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            if let id = call.getString("id"), let work = self.active[id],
               work.epoch == call.getString("epoch") {
                work.task?.cancel(); self.active.removeValue(forKey: id)
            }
            call.resolve()
        }
    }

    @objc func start(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            guard let origin = self.origin, let network = self.network, let jar = self.jar else {
                call.reject("native_transport_unavailable"); return
            }
            guard let id = call.getString("id"), UUID(uuidString: id) != nil,
                  call.getString("epoch") == self.epoch, self.active[id] == nil, self.active.count < 16,
                  let path = call.getString("path"), self.validPath(path),
                  let url = URL(string: path, relativeTo: origin)?.absoluteURL,
                  url.scheme == origin.scheme, url.host == origin.host, url.port == origin.port,
                  url.path.hasPrefix("/api/v1/"),
                  let method = call.getString("method"), ["GET", "POST", "PUT", "DELETE", "PATCH"].contains(method),
                  let mode = call.getString("mode"), ["text", "binary", "stream"].contains(mode),
                  let body = Data(base64Encoded: call.getString("body", "")), body.count <= self.maxBytes,
                  let headers = call.getObject("headers") as? [String: String],
                  headers.keys.allSatisfy({ self.requestHeaders.contains($0.lowercased()) }) else {
                call.reject("native_transport_invalid"); return
            }
            let work = Work(id, self.epoch, mode, path)
            self.active[id] = work
            jar.getAllCookies { cookies in
                guard self.live(work) else { call.reject("native_transport_cancelled"); return }
                var request = URLRequest(url: url)
                request.httpMethod = method
                request.httpShouldHandleCookies = false
                if method != "GET" { request.httpBody = body }
                headers.forEach { request.setValue($0.value, forHTTPHeaderField: $0.key) }
                request.setValue(origin.absoluteString, forHTTPHeaderField: "Origin")
                request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
                let selected = cookies.filter {
                    $0.domain == origin.host && $0.path == "/" && $0.isSecure && $0.isHTTPOnly &&
                    $0.name.hasPrefix("__Host-") && ($0.expiresDate.map { $0 > Date() } ?? true)
                }
                HTTPCookie.requestHeaderFields(with: selected).forEach {
                    request.setValue($0.value, forHTTPHeaderField: $0.key)
                }
                let task = network.dataTask(with: request)
                work.task = task; task.resume(); call.resolve()
            }
        }
    }

    private func validPath(_ path: String) -> Bool {
        let lower = (path.components(separatedBy: "?").first ?? "").lowercased()
        return path.hasPrefix("/api/v1/") && !path.contains("#") && !path.contains("\\") &&
            !["%2e", "%2f", "%5c", "/../", "/./"].contains(where: lower.contains) &&
            !lower.hasSuffix("/..") && !lower.hasSuffix("/.") &&
            !lower.hasPrefix("/api/v1/auth/google/") && !lower.hasPrefix("/api/v1/auth/native/start")
    }

    private func live(_ work: Work) -> Bool {
        return active[work.id] === work && work.epoch == epoch
    }

    private func lookup(_ task: URLSessionTask) -> Work? {
        active.values.first { $0.task === task }
    }

    private func emit(_ work: Work, _ type: String, _ fields: [String: Any] = [:]) {
        guard live(work) else { return }
        var event = fields
        event["id"] = work.id; event["epoch"] = work.epoch; event["type"] = type
        notifyListeners("response", data: event)
        if type == "complete" || type == "error" { active.removeValue(forKey: work.id) }
    }

    public func urlSession(_ session: URLSession, task: URLSessionTask,
                           willPerformHTTPRedirection response: HTTPURLResponse,
                           newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil) // Never send cookies/CSRF or proof to a redirect target.
    }

    public func urlSession(_ session: URLSession, dataTask: URLSessionDataTask,
                           didReceive response: URLResponse,
                           completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        guard let work = lookup(dataTask), live(work), let http = response as? HTTPURLResponse,
              !(300..<400).contains(http.statusCode) else { completionHandler(.cancel); return }
        work.response = http
        var headers: [String: String] = [:]
        responseHeaders.forEach { name in
            if let value = http.value(forHTTPHeaderField: name) { headers[name] = value }
        }
        emit(work, "headers", ["status": http.statusCode, "headers": headers])
        completionHandler(.allow)
    }

    public func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        guard let work = lookup(dataTask), live(work) else { return }
        if work.mode == "stream", let status = work.response?.statusCode, (200..<300).contains(status) {
            work.streamBytes += data.count
            guard work.streamBytes <= maxStream else { dataTask.cancel(); emit(work, "error"); return }
            emit(work, "chunk", ["body": data.base64EncodedString()])
        } else {
            guard work.body.count + data.count <= maxBytes else { dataTask.cancel(); emit(work, "error"); return }
            work.body.append(data)
        }
    }

    public func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        guard let work = lookup(task), live(work) else { return }
        guard error == nil, let response = work.response, let origin = origin, let jar = jar else {
            emit(work, "error"); return
        }
        // Split only cookie boundaries, never commas inside an Expires attribute.
        let raw = response.value(forHTTPHeaderField: "Set-Cookie") ?? ""
        let lines = raw.replacingOccurrences(of: ",(?=\\s*__Host-)", with: "\n", options: .regularExpression).components(separatedBy: "\n")
        let cookies = lines.flatMap { line -> [HTTPCookie] in
            let attributes = line.components(separatedBy: ";").dropFirst().map { $0.trimmingCharacters(in: .whitespaces).lowercased() }
            guard !attributes.contains(where: { ($0.components(separatedBy: "=").first ?? "").trimmingCharacters(in: .whitespaces) == "domain" }) else { return [] }
            return HTTPCookie.cookies(withResponseHeaderFields: ["Set-Cookie": line], for: origin).filter {
                $0.name.hasPrefix("__Host-") && $0.path == "/" && $0.isSecure && $0.isHTTPOnly && $0.domain == origin.host
            }
        }
        enqueueCookie { done in
            guard self.live(work) else { done(); return }
            let group = DispatchGroup()
            cookies.forEach { cookie in group.enter(); jar.setCookie(cookie) { group.leave() } }
            group.notify(queue: .main) {
                if work.path == "/api/v1/auth/native/exchange" && response.statusCode == 204 {
                    let expected = cookies.first { $0.name == "__Host-studymate_session" && $0.value.count == 43 }
                    jar.getAllCookies { retained in
                        let installed = expected.map { candidate in retained.contains {
                            $0.name == candidate.name && $0.value == candidate.value &&
                            $0.domain == origin.host && $0.path == "/" && $0.isSecure && $0.isHTTPOnly &&
                            ($0.expiresDate.map { $0 > Date() } ?? true)
                        } } ?? false
                        if installed { self.emit(work, "complete", ["body": work.body.base64EncodedString()]) }
                        else { self.emit(work, "error") }
                        done()
                    }
                } else { self.emit(work, "complete", ["body": work.body.base64EncodedString()]); done() }
            }
        }
    }

    deinit { network?.invalidateAndCancel() }
}
