import XCTest
import WebKit

/// Actual WKHTTPCookieStore test; isolated store and local HTML, no provider calls.
@MainActor
final class NativeCookieStoreTests: XCTestCase {
    private final class Finished: NSObject, WKNavigationDelegate {
        let ready: XCTestExpectation
        init(_ ready: XCTestExpectation) { self.ready = ready }
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { ready.fulfill() }
    }

    func testHttpOnlyNeverEntersJavaScript() async throws {
        guard let origin = URL(string: "https://peerly-native.invalid/") else {
            XCTFail("Invalid synthetic origin"); return
        }
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        let view = WKWebView(frame: .zero, configuration: configuration)
        let jar = configuration.websiteDataStore.httpCookieStore
        let fixtures = [
            "__Host-native_fixture=synthetic-secret; Path=/; Secure; HttpOnly",
            "native_control=visible; Path=/; Secure"
        ].flatMap { HTTPCookie.cookies(withResponseHeaderFields: ["Set-Cookie": $0], for: origin) }
        XCTAssertEqual(fixtures.count, 2)
        for cookie in fixtures { await jar.setCookie(cookie) }
        let ready = expectation(description: "Local HTML loaded")
        let navigation = Finished(ready)
        view.navigationDelegate = navigation
        view.loadHTMLString("<!doctype html><title>Native cookie test</title>", baseURL: origin)
        await fulfillment(of: [ready], timeout: 10)
        let raw = try await view.evaluateJavaScript("document.cookie")
        guard let visible = raw as? String else { XCTFail("Invalid JS response"); return }
        XCTAssertTrue(visible.contains("native_control=visible"))
        XCTAssertFalse(visible.contains("synthetic-secret"))
        let stored: [HTTPCookie] = await withCheckedContinuation { continuation in
            jar.getAllCookies { continuation.resume(returning: $0) }
        }
        XCTAssertTrue(stored.contains { $0.name == "__Host-native_fixture" && $0.isHTTPOnly })
        for cookie in fixtures { await jar.delete(cookie) }
    }
}
