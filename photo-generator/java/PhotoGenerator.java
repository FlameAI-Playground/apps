import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Iterator;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * FlameAI Photo Generator — text-to-image console app with an image Cortex such as Qwen Image (Java 21+, no libraries).
 *
 *   java PhotoGenerator.java "A red vintage bicycle leaning against a blue door, photorealistic"
 *   java PhotoGenerator.java --size 1024x768 --seed 42 -o bike.png "a red bicycle"
 *   java PhotoGenerator.java                      (asks for the prompt)
 *
 * Image models need a lot of GPU memory (VRAM). Run it on a FlameBox with enough VRAM,
 * and do not keep a large chat model loaded on the same machine at the same time.
 *
 * Put your own values in the two constants below, or set the environment variables
 * FLAMEAI_API_URL / FLAMEAI_SECRET_KEY. Do not share or commit this file with your real Secret Key in it.
 */
public class PhotoGenerator {

    // ── Settings — copy from the FlameAI console ─────────────────────────────
    static final String API_URL    = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/imageGenerate"; // Cortex list › API URL
    static final String SECRET_KEY = "YOUR_SECRET_KEY";                                                          // Settings › My API › Secret key

    // Constants left as placeholders -> environment variables FLAMEAI_API_URL / FLAMEAI_SECRET_KEY
    static final String BASE = setting(API_URL, "FLAMEAI_API_URL").replaceFirst("^POST\\s+", "").replaceFirst("(/cortex/[^/]+).*$", "$1");
    static final String KEY  = setting(SECRET_KEY, "FLAMEAI_SECRET_KEY");

    static final Map<String, String> ERRORS = Map.of(
            "bearer_invalid", "API URL 또는 Secret Key 가 틀렸습니다. Cortex 목록·설정 화면에서 다시 복사하세요.",
            "cortexbox_offline", "FlameBox 가 꺼져 있습니다. PC/서버에서 FlameBox 를 켜 주세요.",
            "cortex_not_found", "API URL 의 Cortex 가 없거나 삭제되었습니다.",
            "unsupported_cortex_type", "이미지 생성 Cortex 가 아닙니다. Qwen Image·FLUX 같은 이미지 Cortex 의 API URL 을 넣으세요.",
            "cortex_inferring", "이 Cortex 가 이미 다른 이미지를 만드는 중입니다. 잠시 뒤 다시 시도하세요.",
            "cortex_init_fail", "모델을 올리지 못했습니다. FlameBox PC 의 VRAM 이 충분한지, 다른 큰 모델이 올라가 있지 않은지 확인하세요.",
            "internal_error", "생성에 실패했습니다. VRAM 부족일 수 있습니다 — 같은 PC 에 올라간 다른 모델(Cortex)을 내리고 다시 시도하세요.");

    static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();

    public static void main(String[] args) throws Exception {
        if (BASE.isEmpty() || KEY.isEmpty() || BASE.contains("YOUR_") || BASE.contains("api-xxxx")) {
            System.err.println("파일 위쪽의 API_URL, SECRET_KEY 를 내 값으로 바꾸거나 환경변수 FLAMEAI_API_URL, FLAMEAI_SECRET_KEY 를 설정하세요");
            System.exit(1);
        }
        int width = 1024, height = 1024;
        long seed = -1;
        String negative = null, output = null;
        StringBuilder prompt = new StringBuilder();
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--size" -> { String[] wh = args[++i].toLowerCase().split("x"); width = Integer.parseInt(wh[0]); height = Integer.parseInt(wh[1]); }
                case "--seed" -> seed = Long.parseLong(args[++i]);
                case "--negative" -> negative = args[++i];
                case "-o", "--output" -> output = args[++i];
                default -> prompt.append(prompt.isEmpty() ? "" : " ").append(args[i]);
            }
        }
        if (prompt.isEmpty()) {
            Charset cs = System.console() != null ? System.console().charset() : Charset.defaultCharset();
            System.out.print("무엇을 그릴까요? > ");
            String line = new BufferedReader(new InputStreamReader(System.in, cs)).readLine();
            if (line == null || line.isBlank()) return;
            prompt.append(line.trim());
        }
        System.out.println("프롬프트: " + prompt + "   (" + width + "x" + height + ")");
        long t0 = System.currentTimeMillis();
        try {
            Map<String, String> result = generate(prompt.toString(), negative, width, height, seed);
            String file = result.get("file");
            Path out = Path.of(output != null ? output : file.substring(file.lastIndexOf('/') + 1));
            download(file, out);
            delete(file);   // the result is saved locally — remove it from the Cortex file storage
            System.out.printf("저장: %s   (seed %s, %.0f초)%n", out.toAbsolutePath(), result.get("seed"), (System.currentTimeMillis() - t0) / 1000.0);
        } catch (HttpTimeoutException e) {
            System.err.println("\n[오류] 시간 초과 — 모델 로드와 생성은 수 분 걸릴 수 있습니다. 잠시 뒤 다시 시도하세요.");
        } catch (IllegalStateException e) {
            System.err.println("\n[오류] " + e.getMessage());
        }
    }

    static Map<String, String> generate(String prompt, String negative, int width, int height, long seed) throws Exception {
        String body = """
            {"prompt": %s, %s"width": %d, "height": %d, "seed": %d, "stream": true}
            """.formatted(quote(prompt), negative == null ? "" : "\"negative_prompt\": " + quote(negative) + ", ", width, height, seed);
        HttpRequest req = request("/imageGenerate").header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body)).build();
        HttpResponse<java.util.stream.Stream<String>> res = HTTP.send(req, HttpResponse.BodyHandlers.ofLines());
        Iterator<String> lines = res.body().iterator();

        String event = "", file = null, usedSeed = null;
        StringBuilder other = new StringBuilder();
        while (lines.hasNext()) {
            String line = lines.next();
            if (line.startsWith("event:")) { event = line.substring(6).trim(); continue; }
            if (!line.startsWith("data:")) { other.append(line); continue; }
            String data = line.substring(5);
            switch (event) {
                case "cortex.init_start" -> System.out.println("모델을 메모리에 올리는 중... (처음 한 번은 오래 걸릴 수 있습니다)");
                case "generation.queued" -> System.out.println("다른 생성이 끝나기를 기다리는 중...");
                case "generation.progress" -> System.out.print("\r생성 중 " + bar(number(data, "step"), number(data, "steps")));
                case "generation.result" -> {
                    file = match(data, "\"files\"\\s*:\\s*\\[\\s*\"([^\"]+)\"");
                    usedSeed = match(data, "\"seed\"\\s*:\\s*(-?\\d+)");
                }
                case "generation.error", "cortex.init_failed" -> throw new IllegalStateException(explain(data));
                default -> { }
            }
        }
        System.out.println();
        if (file == null) throw new IllegalStateException(res.statusCode() >= 400 ? explain(other.toString()) : "결과가 없습니다: " + other);
        return Map.of("file", file, "seed", usedSeed == null ? "?" : usedSeed);
    }

    static void download(String file, Path out) throws Exception {
        HttpResponse<byte[]> res = HTTP.send(request("/" + file).GET().build(), HttpResponse.BodyHandlers.ofByteArray());
        if (res.statusCode() != 200) throw new IllegalStateException("결과 파일을 받지 못했습니다: HTTP " + res.statusCode());
        Files.write(out, res.body());
    }

    static void delete(String file) {
        try { HTTP.send(request("/" + file).DELETE().build(), HttpResponse.BodyHandlers.discarding()); } catch (Exception ignored) { }
    }

    static HttpRequest.Builder request(String path) {
        return HttpRequest.newBuilder(URI.create(BASE + path))
                .header("Authorization", "Bearer " + KEY)
                .header("X-API-Version", "1")
                .timeout(Duration.ofMinutes(15));   // model load + generation can take minutes
    }

    static String explain(String json) {
        String code = match(json, "\"code\"\\s*:\\s*\"([^\"]+)\"");
        String message = match(json, "\"message\"\\s*:\\s*\"([^\"]*)\"");
        return code == null ? json : ERRORS.getOrDefault(code, code) + (message == null ? "" : "  (" + code + ": " + message + ")");
    }

    static String setting(String constant, String envName) {
        boolean placeholder = constant.contains("YOUR_") || constant.contains("api-xxxx");
        String value = placeholder ? System.getenv(envName) : constant;
        return value == null ? "" : value.trim();
    }

    static String bar(int step, int steps) {
        int done = steps == 0 ? 0 : step * 20 / steps;
        return "[" + "#".repeat(done) + "-".repeat(20 - done) + "] " + step + "/" + steps;
    }

    static int number(String json, String key) {
        String v = match(json, "\"" + key + "\"\\s*:\\s*(\\d+)");
        return v == null ? 0 : Integer.parseInt(v);
    }

    static String match(String text, String regex) {
        Matcher m = Pattern.compile(regex).matcher(text);
        return m.find() ? m.group(1) : null;
    }

    // JSON strings without a library (use Jackson or Gson in real projects)
    static String quote(String s) {
        StringBuilder sb = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> { if (c < 0x20) sb.append(String.format("\\u%04x", (int) c)); else sb.append(c); }
            }
        }
        return sb.append('"').toString();
    }
}
