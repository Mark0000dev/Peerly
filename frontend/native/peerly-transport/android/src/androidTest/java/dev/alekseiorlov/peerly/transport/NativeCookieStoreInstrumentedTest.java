package dev.alekseiorlov.peerly.transport;

import android.webkit.CookieManager;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.test.core.app.ApplicationProvider;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.Assert.assertTrue;

/** Actual Android WebView/CookieManager test. No provider/DNS/network requests. */
@RunWith(AndroidJUnit4.class)
public final class NativeCookieStoreInstrumentedTest {
    @Test public void httpOnlyRemainsNativeAndDeletionCompletes() throws Exception {
        String origin = "https://peerly-native.invalid/";
        CookieManager jar = CookieManager.getInstance();
        CountDownLatch written = new CountDownLatch(2);
        AtomicReference<WebView> view = new AtomicReference<>();
        CountDownLatch loaded = new CountDownLatch(1);
        InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> {
            jar.setCookie(origin, "__Host-native_fixture=synthetic-secret; Path=/; Secure; HttpOnly", accepted -> written.countDown());
            jar.setCookie(origin, "native_control=visible; Path=/; Secure", accepted -> written.countDown());
            WebView web = new WebView(ApplicationProvider.getApplicationContext());
            web.getSettings().setJavaScriptEnabled(true);
            web.setWebViewClient(new WebViewClient() {
                @Override public void onPageFinished(WebView current, String url) { loaded.countDown(); }
            });
            view.set(web);
        });
        try {
            assertTrue("Cookie operation must complete", written.await(10, TimeUnit.SECONDS));
            InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> view.get().loadDataWithBaseURL(
                origin, "<!doctype html><title>Native cookie test</title>", "text/html", "UTF-8", null));
            assertTrue("Local HTML must load", loaded.await(10, TimeUnit.SECONDS));
            assertTrue("Native jar must retain HttpOnly cookie", jar.getCookie(origin).contains("__Host-native_fixture="));
            CountDownLatch evaluated = new CountDownLatch(1);
            AtomicReference<String> visible = new AtomicReference<>("");
            InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> view.get().evaluateJavascript(
                "document.cookie", result -> { visible.set(result); evaluated.countDown(); }));
            assertTrue("JS operation must complete", evaluated.await(10, TimeUnit.SECONDS));
            assertTrue("Control cookie must be visible", visible.get().contains("native_control=visible"));
            assertTrue("HttpOnly cookie must not enter JS", !visible.get().contains("synthetic-secret"));
        } finally {
            CountDownLatch deleted = new CountDownLatch(2);
            InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> {
                jar.setCookie(origin, "__Host-native_fixture=; Max-Age=0; Path=/; Secure; HttpOnly", accepted -> deleted.countDown());
                jar.setCookie(origin, "native_control=; Max-Age=0; Path=/; Secure", accepted -> deleted.countDown());
                view.get().destroy();
            });
            assertTrue("Fixture cleanup must complete", deleted.await(10, TimeUnit.SECONDS));
        }
    }
}
