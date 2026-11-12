package dev.alekseiorlov.peerly.transport;

import android.os.Handler;
import android.os.Looper;
import android.webkit.CookieManager;
import android.util.Base64;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import okhttp3.Call;
import okhttp3.Cookie;
import okhttp3.CookieJar;
import okhttp3.HttpUrl;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

/** Fixed-origin API only. No secrets in plugin results, headers or error messages. */
@CapacitorPlugin(name = "PeerlyTransport")
public final class PeerlyTransportPlugin extends Plugin {
    private static final int MAX_BYTES = 16 * 1024 * 1024;
    private static final int MAX_STREAM = 1024 * 1024;
    private static final int MAX_REQUESTS = 16;
    private static final Set<String> REQUEST_HEADERS = new HashSet<>(Arrays.asList(
        "accept", "content-type", "x-csrf-token", "idempotency-key", "if-match", "last-event-id", "traceparent", "x-action-id"
    ));
    private static final List<String> RESPONSE_HEADERS = Arrays.asList(
        "content-type", "retry-after", "etag", "cache-control", "x-request-id"
    );
    private final ExecutorService gate = Executors.newSingleThreadExecutor();
    private final ExecutorService workers = Executors.newFixedThreadPool(4);
    private final Handler main = new Handler(Looper.getMainLooper());
    // Accessed on gate only, including cookie reads/writes and epoch transitions.
    private final Map<String, Work> active = new HashMap<>();
    private String epoch = UUID.randomUUID().toString();
    private HttpUrl origin;
    private CookieManager jar;
    private OkHttpClient client;

    private static final class Work {
        final String id;
        final String epoch;
        final long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(90);
        final AtomicBoolean cancelled = new AtomicBoolean(false);
        final AtomicReference<Call> call = new AtomicReference<>();
        Work(String id, String epoch) { this.id = id; this.epoch = epoch; }
        void cancel() {
            cancelled.set(true);
            Call current = call.get();
            if (current != null) current.cancel();
        }
    }

    @Override public void load() {
        String configured = getConfig().getString("apiOrigin", "");
        HttpUrl parsed = HttpUrl.parse(configured);
        if (parsed == null || !parsed.isHttps() || !parsed.encodedPath().equals("/") ||
            parsed.query() != null || parsed.fragment() != null || !parsed.username().isEmpty() ||
            !parsed.password().isEmpty() || !configured.equals(parsed.scheme() + "://" + parsed.host() +
                (parsed.port() == 443 ? "" : ":" + parsed.port())) ||
            getBridge().getConfig().isLoggingEnabled()) return;
        origin = parsed;
        jar = CookieManager.getInstance();
        // Do not use URLConnection's global Capacitor CookieHandler: it logs values.
        client = new OkHttpClient.Builder().cookieJar(CookieJar.NO_COOKIES)
            .retryOnConnectionFailure(false).followRedirects(false).followSslRedirects(false).cache(null)
            .connectTimeout(10, TimeUnit.SECONDS).readTimeout(35, TimeUnit.SECONDS)
            .callTimeout(90, TimeUnit.SECONDS).build();
    }

    @PluginMethod public void configuration(PluginCall call) {
        if (client == null) { call.reject("native_transport_unavailable"); return; }
        JSObject result = new JSObject();
        result.put("appId", getContext().getPackageName());
        result.put("apiOrigin", origin.toString().replaceAll("/$", ""));
        result.put("wakeUrl", getConfig().getString("wakeUrl", ""));
        call.resolve(result);
    }

    @PluginMethod public void advance(PluginCall call) {
        gate.execute(() -> {
            if (client == null) { call.reject("native_transport_unavailable"); return; }
            for (Work work : active.values()) work.cancel();
            active.clear();
            epoch = UUID.randomUUID().toString();
            if (Boolean.TRUE.equals(call.getBoolean("clearSession", false))) {
                if (!writeCookie("__Host-studymate_session=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax")) {
                    call.reject("native_cookie_store_failed"); return;
                }
            }
            JSObject result = new JSObject(); result.put("epoch", epoch); call.resolve(result);
        });
    }

    @PluginMethod public void cancel(PluginCall call) {
        gate.execute(() -> {
            String id = call.getString("id", "");
            Work work = active.get(id);
            if (work != null && work.epoch.equals(call.getString("epoch", ""))) {
                work.cancel(); active.remove(id);
            }
            call.resolve();
        });
    }

    @PluginMethod public void start(PluginCall call) {
        gate.execute(() -> {
            if (client == null) { call.reject("native_transport_unavailable"); return; }
            String id = call.getString("id", "");
            String suppliedEpoch = call.getString("epoch", "");
            String path = call.getString("path", "");
            String method = call.getString("method", "GET");
            String mode = call.getString("mode", "text");
            if (!id.matches("[a-f0-9-]{36}") || !epoch.equals(suppliedEpoch) || active.containsKey(id) ||
                active.size() >= MAX_REQUESTS || !Arrays.asList("GET", "POST", "PUT", "DELETE", "PATCH").contains(method) ||
                !Arrays.asList("text", "binary", "stream").contains(mode) ||
                !validPath(path)) { call.reject("native_transport_invalid"); return; }
            HttpUrl target = origin.resolve(path);
            if (target == null || !target.host().equals(origin.host()) || target.port() != origin.port() || !target.encodedPath().startsWith("/api/v1/")) {
                call.reject("native_transport_invalid"); return;
            }
            try {
                Request.Builder builder = new Request.Builder().url(target)
                    .header("Origin", origin.toString().replaceAll("/$", ""))
                    .header("Cache-Control", "no-store");
                JSObject headers = call.getObject("headers", new JSObject());
                for (String name : iterableKeys(headers)) {
                    if (!REQUEST_HEADERS.contains(name.toLowerCase(Locale.ROOT))) {
                        call.reject("native_transport_invalid"); return;
                    }
                    builder.header(name, headers.getString(name));
                }
                String cookie = jar.getCookie(origin.toString());
                if (cookie != null) builder.header("Cookie", cookie);
                String encoded = call.getString("body", "");
                if (encoded.length() > MAX_BYTES * 2) { call.reject("native_transport_invalid"); return; }
                byte[] body = Base64.decode(encoded, Base64.DEFAULT);
                if (body.length > MAX_BYTES) { call.reject("native_transport_invalid"); return; }
                RequestBody payload = Arrays.asList("GET", "HEAD").contains(method) ? null :
                    RequestBody.create(body, MediaType.parse(headers.optString("content-type", headers.optString("Content-Type", "application/json"))));
                builder.method(method, payload);
                Work work = new Work(id, epoch);
                active.put(id, work);
                Request request = builder.build();
                workers.execute(() -> perform(work, request, mode));
                call.resolve();
            } catch (IllegalArgumentException error) { call.reject("native_transport_invalid"); }
        });
    }

    private static List<String> iterableKeys(JSONObject object) {
        List<String> names = new ArrayList<>(); object.keys().forEachRemaining(names::add); return names;
    }

    private static boolean validPath(String path) {
        String lower = path.split("\\?", 2)[0].toLowerCase(Locale.ROOT);
        return path.startsWith("/api/v1/") && !path.contains("#") && !path.contains("\\") &&
            !lower.contains("%2e") && !lower.contains("%2f") && !lower.contains("%5c") &&
            !lower.contains("/../") && !lower.contains("/./") && !lower.endsWith("/..") && !lower.endsWith("/.") &&
            !lower.startsWith("/api/v1/auth/google/") && !lower.startsWith("/api/v1/auth/native/start");
    }

    private boolean live(Work work) {
        return !work.cancelled.get() && epoch.equals(work.epoch) && active.get(work.id) == work;
    }

    private void event(Work work, String type, JSObject fields) {
        gate.execute(() -> {
            if (!live(work)) return;
            fields.put("id", work.id); fields.put("epoch", work.epoch); fields.put("type", type);
            notifyListeners("response", fields);
            if (type.equals("complete") || type.equals("error")) active.remove(work.id);
        });
    }

    private void perform(Work work, Request request, String mode) {
        Call network = client.newCall(request); work.call.set(network);
        long remaining = work.deadline - System.nanoTime();
        if (remaining <= 0) { event(work, "error", new JSObject()); return; }
        network.timeout().timeout(remaining, TimeUnit.NANOSECONDS);
        if (work.cancelled.get()) { network.cancel(); return; }
        try (Response response = network.execute()) {
            if (response.code() >= 300 && response.code() < 400) throw new IOException();
            JSObject safeHeaders = new JSObject();
            for (String name : RESPONSE_HEADERS) {
                String value = response.header(name);
                if (value != null) safeHeaders.put(name, value);
            }
            JSObject headerEvent = new JSObject(); headerEvent.put("status", response.code());
            headerEvent.put("headers", safeHeaders); event(work, "headers", headerEvent);
            ResponseBody entity = response.body();
            ByteArrayOutputStream body = new ByteArrayOutputStream();
            if (entity != null && mode.equals("stream") && response.isSuccessful()) {
                InputStream reader = entity.byteStream();
                byte[] chunk = new byte[4096]; int count; int total = 0;
                while (!work.cancelled.get() && (count = reader.read(chunk)) != -1) {
                    total += count; if (total > MAX_STREAM) throw new IOException();
                    JSObject data = new JSObject();
                    data.put("body", Base64.encodeToString(Arrays.copyOf(chunk, count), Base64.NO_WRAP));
                    event(work, "chunk", data);
                }
            } else if (entity != null) {
                InputStream stream = entity.byteStream(); byte[] chunk = new byte[8192]; int count;
                while (!work.cancelled.get() && (count = stream.read(chunk)) != -1) {
                    if (body.size() + count > MAX_BYTES) throw new IOException();
                    body.write(chunk, 0, count);
                }
            }
            List<String> setCookies = response.headers("Set-Cookie");
            String encoded = Base64.encodeToString(body.toByteArray(), Base64.NO_WRAP);
            gate.execute(() -> {
                if (!live(work)) return;
                String installedSession = null;
                for (String header : setCookies) {
                    Cookie parsed = Cookie.parse(origin, header);
                    if (parsed == null || !parsed.name().startsWith("__Host-") || !parsed.hostOnly() ||
                        !parsed.secure() || !parsed.httpOnly() || !parsed.path().equals("/")) continue;
                    if (!writeCookie(header)) { event(work, "error", new JSObject()); return; }
                    if (parsed.name().equals("__Host-studymate_session") && parsed.value().matches("[A-Za-z0-9_-]{43}"))
                        installedSession = parsed.name() + "=" + parsed.value();
                }
                if (request.url().encodedPath().equals("/api/v1/auth/native/exchange") && response.code() == 204) {
                    String retained = jar.getCookie(origin.toString());
                    if (installedSession == null || retained == null ||
                        !Arrays.asList(retained.split(";\\s*")).contains(installedSession)) {
                        event(work, "error", new JSObject()); return;
                    }
                }
                // Cookie operations finish on this gate before advance can clear/change epoch.
                JSObject result = new JSObject(); result.put("body", encoded);
                event(work, "complete", result);
            });
        } catch (IOException | IllegalArgumentException error) {
            event(work, "error", new JSObject());
        }
    }

    private boolean writeCookie(String value) {
        CountDownLatch done = new CountDownLatch(1);
        AtomicBoolean stored = new AtomicBoolean(false);
        main.post(() -> jar.setCookie(origin.toString(), value, accepted -> {
            stored.set(Boolean.TRUE.equals(accepted)); done.countDown();
        }));
        try { done.await(); jar.flush(); return stored.get(); }
        catch (InterruptedException error) { Thread.currentThread().interrupt(); return false; }
    }

    @Override protected void handleOnDestroy() {
        gate.execute(() -> { for (Work work : active.values()) work.cancel(); active.clear(); });
        workers.shutdownNow(); gate.shutdown();
        if (client != null) client.dispatcher().cancelAll();
    }
}
