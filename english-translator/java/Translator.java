import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.Charset;
import java.time.Duration;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * FlameAI AI Translator — LLM-based Korean <-> English console translator (Java 21+, no libraries).
 *
 *   java Translator.java "안녕하세요"              Korean  -> English
 *   java Translator.java "Good morning"           English -> Korean
 *   java Translator.java --to ja "안녕하세요"      any language: ja, zh, es, fr, de, vi ...
 *   java Translator.java < note.txt               translate a whole file
 *   java Translator.java                          interactive mode (empty line to quit)
 *
 * Put your own values in the three constants below.
 * Do not share or commit this file with your real Secret Key in it.
 */
public class Translator {

    // ── Settings — copy from the FlameAI console ─────────────────────────────
    static final String API_BASE   = "https://api-xxxx.flameai.im/AbCd1234"; // Settings › My API › API base url
    static final String SECRET_KEY = "YOUR_SECRET_KEY";                      // Settings › My API › Secret key
    static final String CORTEX_ID  = "YOUR_CORTEX_ID";                       // Cortex list ⋮ › Copy Cortex ID
    static final String CONVERSATION_ID = "english-translator";

    static final Map<String, String> LANGS = Map.of(
            "ko", "Korean", "en", "English", "ja", "Japanese", "zh", "Simplified Chinese",
            "es", "Spanish", "fr", "French", "de", "German", "vi", "Vietnamese");

    static final Map<String, String> ERRORS = Map.of(
            "bearer_not_found", "Secret Key 가 비어 있습니다. SECRET_KEY 를 확인하세요.",
            "bearer_invalid", "API 주소, Secret Key 또는 Cortex ID 가 틀렸습니다. 콘솔에서 다시 복사하세요.",
            "cortexbox_offline", "FlameBox 가 꺼져 있습니다. PC/서버에서 FlameBox 를 켜 주세요.",
            "cortex_not_found", "Cortex ID 가 틀렸거나 삭제된 Cortex 입니다.",
            "cortex_occupied", "다른 대화가 이 Cortex 를 쓰고 있습니다. 잠시 뒤 다시 시도하세요.");

    static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();

    public static void main(String[] args) throws Exception {
        if ((SECRET_KEY + CORTEX_ID).contains("YOUR_") || API_BASE.contains("api-xxxx")) {
            System.err.println("파일 위쪽의 API_BASE, SECRET_KEY, CORTEX_ID 를 내 값으로 바꾸세요 / set the constants at the top");
            System.exit(1);
        }
        String to = null;
        StringBuilder text = new StringBuilder();
        for (int i = 0; i < args.length; i++) {
            if (args[i].equals("--to") && i + 1 < args.length) { to = args[++i]; continue; }
            text.append(text.isEmpty() ? "" : " ").append(args[i]);
        }
        Charset in = Charset.forName(System.getProperty("stdin.encoding", Charset.defaultCharset().name()));
        BufferedReader reader = new BufferedReader(new InputStreamReader(System.in, in));

        if (!text.isEmpty() || System.console() == null) {        // argument or file/pipe: translate once
            String input = !text.isEmpty() ? text.toString() : reader.lines().collect(Collectors.joining("\n"));
            System.out.println(run(input, to));
            return;
        }
        System.out.println("FlameAI translator — 한국어 <-> English  (빈 줄: 종료 / empty line to quit)");
        while (true) {
            System.out.print("> ");
            String line = reader.readLine();
            if (line == null || line.isBlank()) break;
            System.out.println(run(line.trim(), to));
        }
    }

    static String run(String text, String to) {
        try {
            return translate(text, to != null ? LANGS.getOrDefault(to.toLowerCase(), to) : targetLanguage(text));
        } catch (HttpTimeoutException e) {
            return "[오류] 시간 초과 — 첫 요청은 모델을 올리느라 오래 걸릴 수 있습니다. 잠시 뒤 다시 시도하세요.";
        } catch (Exception e) {
            return "[오류] " + e.getMessage();
        }
    }

    /** 한글이 있으면 영어로, 없으면 한국어로. */
    static String targetLanguage(String text) {
        return text.matches("(?s).*[가-힣].*") ? "English" : "Korean";
    }

    static String translate(String text, String target) throws Exception {
        String rule = "You are a professional translator. Translate the user's text into " + target + ". "
                + "Output only the translation - no explanations, no quotes, no notes. "
                + "Keep line breaks, numbers, code and proper nouns as they are.";
        String body = """
            {"conversationId": %s,
             "options": {"stream": false, "think": false, "cortex_reset": true},
             "messages": [
               {"role": "system", "content": %s},
               {"role": "user", "content": %s}]}
            """.formatted(quote(CONVERSATION_ID), quote(rule), quote(text));

        HttpRequest request = HttpRequest.newBuilder(URI.create(API_BASE.replaceAll("/+$", "") + "/cortex/" + CORTEX_ID + "/messages"))
                .header("Authorization", "Bearer " + SECRET_KEY)
                .header("Content-Type", "application/json")
                .header("X-API-Version", "1")
                .timeout(Duration.ofMinutes(5))   // the first call may load the model
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        String json = HTTP.send(request, HttpResponse.BodyHandlers.ofString()).body();

        Matcher error = Pattern.compile("\"error\"\\s*:\\s*\\{.*?\"code\"\\s*:\\s*\"([^\"]+)\"", Pattern.DOTALL).matcher(json);
        if (error.find()) return "[오류] " + ERRORS.getOrDefault(error.group(1), error.group(1));

        // answer = "text" fields of the text blocks in message.content
        Matcher m = Pattern.compile("\"text\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"").matcher(json);
        StringBuilder answer = new StringBuilder();
        while (m.find()) answer.append(unquote(m.group(1)));
        return answer.toString().trim();
    }

    // ── JSON strings without a library (use Jackson or Gson in real projects) ──
    static String quote(String s) {
        StringBuilder sb = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c)); else sb.append(c);
                }
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
                case 'b' -> out.append('\b');
                case 'f' -> out.append('\f');
                case 'u' -> { out.append((char) Integer.parseInt(s.substring(i + 1, i + 5), 16)); i += 4; }
                default -> out.append(n);
            }
        }
        return out.toString();
    }
}
