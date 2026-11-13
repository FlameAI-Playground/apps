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
 * FlameAI Drawing Helper — describe a picture in your own words; an LLM Cortex turns it into a detailed
 * English prompt, and an image Cortex (Qwen Image, FLUX …) draws it (Java 21+, no libraries).
 *
 *   java DrawingHelper.java
 *   그릴 것을 말해 주세요> 비 오는 밤 골목에서 우산 쓴 고양이
 *   고칠 점 (Enter = 그리기)> 좀 더 따뜻한 분위기로        <- same conversation: the LLM remembers the prompt
 *   고칠 점 (Enter = 그리기)>                              <- draws and saves drawing-1.png
 *
 *   options: --size 1024x768  --seed 42
 *
 * Use two Cortexes of the same account: a chat (LLM) Cortex and an image Cortex. Image models need a lot of
 * GPU memory — if both Cortexes are on one PC with little VRAM, image generation can fail.
 *
 * Put your own values in the three constants below, or set the environment variables
 * FLAMEAI_CHAT_URL / FLAMEAI_IMAGE_URL / FLAMEAI_SECRET_KEY. Do not share or commit this file with your real key.
 */
public class DrawingHelper {

    // ── Settings — copy from the FlameAI console ─────────────────────────────
    static final String CHAT_URL   = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CHAT_CORTEX_ID/messages";       // Cortex list › API URL (LLM)
    static final String IMAGE_URL  = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_IMAGE_CORTEX_ID/imageGenerate"; // Cortex list › API URL (image)
    static final String SECRET_KEY = "YOUR_SECRET_KEY";                                                                // Settings › My API › Secret key

    // ── How the LLM rewrites your words (change freely) ──────────────────────
    static final String SYSTEM_PROMPT = """
            You turn a short picture description (any language) into one detailed English prompt for a text-to-image model. \
            Keep the user's subject and intent. Add concrete details: setting, style, lighting, colors, composition, camera. \
            Do not add text or letters to the picture unless asked. When the user asks for a change, rewrite the whole prompt with the change. \
            Reply with the prompt only: one paragraph, at most 70 words, no quotes, no explanation.""";
    static final String CONVERSATION_ID = "drawing-helper";

    // Constants left as placeholders -> environment variables
    static final String CHAT  = setting(CHAT_URL, "FLAMEAI_CHAT_URL").replaceFirst("^POST\\s+", "");
    static final String IMAGE = setting(IMAGE_URL, "FLAMEAI_IMAGE_URL").replaceFirst("^POST\\s+", "").replaceFirst("(/cortex/[^/]+).*$", "$1");
    static final String KEY   = setting(SECRET_KEY, "FLAMEAI_SECRET_KEY");

    static final Map<String, String> ERRORS = Map.of(
            "bearer_invalid", "API URL 또는 Secret Key 가 틀렸습니다. Cortex 목록·설정 화면에서 다시 복사하세요.",
            "cortexbox_offline", "FlameBox 가 꺼져 있습니다. PC/서버에서 FlameBox 를 켜 주세요.",
            "cortex_not_found", "API URL 의 Cortex 가 없거나 삭제되었습니다.",
            "cortex_occupied", "다른 대화가 대화 Cortex 를 쓰고 있습니다. /new 로 새 그림을 시작하면 이 프로그램으로 가져옵니다.",
            "unsupported_cortex_type", "Cortex 종류가 맞지 않습니다. CHAT_URL 에는 대화(LLM) Cortex, IMAGE_URL 에는 이미지 Cortex 를 넣으세요.",
            "cortex_inferring", "이미지 Cortex 가 다른 그림을 만드는 중입니다. 잠시 뒤 다시 시도하세요.",
            "cortex_init_fail", "모델을 올리지 못했습니다. FlameBox PC 의 VRAM 이 충분한지 확인하세요.",
            "internal_error", "생성에 실패했습니다. VRAM 부족일 수 있습니다 — 같은 PC 에 올라간 다른 모델(Cortex)을 내리고 다시 시도하세요.");

    static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();

    public static void main(String[] args) throws Exception {
        if (CHAT.isEmpty() || IMAGE.isEmpty() || KEY.isEmpty()) {
            System.err.println("파일 위쪽의 CHAT_URL, IMAGE_URL, SECRET_KEY 를 내 값으로 바꾸거나 환경변수 FLAMEAI_CHAT_URL, FLAMEAI_IMAGE_URL, FLAMEAI_SECRET_KEY 를 설정하세요");
            System.exit(1);
        }
        int width = 1024, height = 768;
        long seed = -1;
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--size" -> { String[] wh = args[++i].toLowerCase().split("x"); width = Integer.parseInt(wh[0]); height = Integer.parseInt(wh[1]); }
                case "--seed" -> seed = Long.parseLong(args[++i]);
                default -> { System.err.println("알 수 없는 옵션: " + args[i]); System.exit(1); }
            }
        }
        Charset cs = System.console() != null ? System.console().charset() : Charset.defaultCharset();
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, cs));
        System.out.println("FlameAI 그림 도우미  (/new: 새 그림, /exit: 종료)");

        String prompt = null;   // the English prompt the LLM wrote last
        int count = 0;
        while (true) {
            System.out.print(prompt == null ? "\n그릴 것을 말해 주세요> " : "\n고칠 점 (Enter = 그리기)> ");
            String line = in.readLine();
            if (line == null || line.trim().equals("/exit")) break;
            line = line.trim();
            try {
                if (line.equals("/new")) {
                    prompt = null;
                } else if (line.isEmpty()) {
                    if (prompt == null) break;
                    Path out = Path.of("drawing-" + (++count) + ".png");
                    draw(prompt, width, height, seed, out);
                } else {
                    prompt = refine(line, prompt == null);   // first line: new conversation, after that: a change request
                    System.out.println("[영어 프롬프트]\n" + prompt);
                }
            } catch (HttpTimeoutException e) {
                System.err.println("\n[오류] 시간 초과 — 모델을 올리는 중일 수 있습니다. 잠시 뒤 다시 시도하세요.");
            } catch (IllegalStateException e) {
                System.err.println("\n[오류] " + e.getMessage());
            }
        }
    }

    // ── Step 1: the LLM Cortex rewrites the description as an English image prompt ──
    static String refine(String words, boolean newPicture) throws Exception {
        // a new picture starts with the rules (system) and cortex_reset; a change request sends only the new message
        String system = newPicture ? "{\"role\": \"system\", \"content\": " + quote(SYSTEM_PROMPT) + "}," : "";
        String body = """
            {"conversationId": %s,
             "options": {"stream": false, "think": false, "cortex_reset": %s},
             "messages": [%s {"role": "user", "content": %s}]}
            """.formatted(quote(CONVERSATION_ID), newPicture, system, quote(words));
        HttpRequest req = request(CHAT).header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body)).build();
        String json = HTTP.send(req, HttpResponse.BodyHandlers.ofString()).body();
        if (json.contains("\"error\"")) throw new IllegalStateException(explain(json));
        Matcher m = Pattern.compile("\"text\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"").matcher(json);
        StringBuilder text = new StringBuilder();
        while (m.find()) text.append(unquote(m.group(1)));   // only "text" blocks — "thinking" blocks are skipped
        if (text.isEmpty()) throw new IllegalStateException("대화 Cortex 가 빈 답을 보냈습니다: " + json);
        return text.toString().trim();
    }

    // ── Step 2: the image Cortex draws the prompt (streaming progress) and we save the PNG ──
    static void draw(String prompt, int width, int height, long seed, Path out) throws Exception {
        long t0 = System.currentTimeMillis();
        String body = """
            {"prompt": %s, "width": %d, "height": %d, "seed": %d, "stream": true}
            """.formatted(quote(prompt), width, height, seed);
        HttpRequest req = request(IMAGE + "/imageGenerate").header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body)).build();
        HttpResponse<java.util.stream.Stream<String>> res = HTTP.send(req, HttpResponse.BodyHandlers.ofLines());
        Iterator<String> lines = res.body().iterator();
        String event = "", file = null, usedSeed = "?";
        StringBuilder other = new StringBuilder();
        while (lines.hasNext()) {
            String line = lines.next();
            if (line.startsWith("event:")) { event = line.substring(6).trim(); continue; }
            if (!line.startsWith("data:")) { other.append(line); continue; }
            String data = line.substring(5);
            switch (event) {
                case "cortex.init_start" -> System.out.println("이미지 모델을 올리는 중... (처음 한 번은 오래 걸릴 수 있습니다)");
                case "generation.queued" -> System.out.println("다른 생성이 끝나기를 기다리는 중...");
                case "generation.progress" -> System.out.print("\r그리는 중 " + match(data, "\"step\"\\s*:\\s*(\\d+)") + "/" + match(data, "\"steps\"\\s*:\\s*(\\d+)"));
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
        HttpResponse<byte[]> png = HTTP.send(request(IMAGE + "/" + file).GET().build(), HttpResponse.BodyHandlers.ofByteArray());
        if (png.statusCode() != 200) throw new IllegalStateException("결과 파일을 받지 못했습니다: HTTP " + png.statusCode());
        Files.write(out, png.body());
        HTTP.send(request(IMAGE + "/" + file).DELETE().build(), HttpResponse.BodyHandlers.discarding());   // clean up the FlameBox copy
        System.out.printf("저장: %s  (%dx%d, seed %s, %.0f초)%n", out, width, height, usedSeed, (System.currentTimeMillis() - t0) / 1000.0);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────
    static HttpRequest.Builder request(String url) {
        return HttpRequest.newBuilder(URI.create(url))
                .header("Authorization", "Bearer " + KEY)
                .header("X-API-Version", "1")
                .timeout(Duration.ofMinutes(15));   // model load + generation can take minutes
    }

    static String setting(String constant, String envName) {
        boolean placeholder = constant.contains("YOUR_") || constant.contains("api-xxxx");
        String value = placeholder ? System.getenv(envName) : constant;
        return value == null ? "" : value.trim();
    }

    static String explain(String json) {
        String code = match(json, "\"code\"\\s*:\\s*\"([^\"]+)\"");
        String message = match(json, "\"message\"\\s*:\\s*\"([^\"]*)\"");
        return code == null ? json : ERRORS.getOrDefault(code, code) + (message == null ? "" : "  (" + code + ": " + message + ")");
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

    static String unquote(String s) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c != '\\' || i + 1 >= s.length()) { out.append(c); continue; }
            char n = s.charAt(++i);
            switch (n) {
                case 'n' -> out.append('\n');
                case 't' -> out.append('\t');
                case 'r' -> out.append('\r');
                case 'u' -> { out.append((char) Integer.parseInt(s.substring(i + 1, i + 5), 16)); i += 4; }
                default -> out.append(n);
            }
        }
        return out.toString();
    }
}
