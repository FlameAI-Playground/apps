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

/**
 * FlameAI Chatbot — an LLM console chatbot that remembers the conversation (Java 21+, no libraries).
 *
 *   java Chatbot.java
 *   > 안녕! 내 이름은 민수야.
 *   > 내 이름이 뭐라고 했지?        <- only the new message is sent; the Cortex remembers the rest
 *   > /reset                        <- start a new conversation
 *
 * Put your own values in the two constants below.
 * Do not share or commit this file with your real Secret Key in it.
 */
public class Chatbot {

    // ── Settings — copy from the FlameAI console ─────────────────────────────
    static final String API_URL    = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/messages"; // Cortex list › API URL
    static final String SECRET_KEY = "YOUR_SECRET_KEY";                                                     // Settings › My API › Secret key

    // ── Chatbot personality (change freely) ──────────────────────────────────
    static final String SYSTEM_PROMPT = "You are a friendly assistant. Answer briefly in the user's language, in plain text without Markdown.";
    static final String CONVERSATION_ID = "simple-chatbot";

    // Constants left as placeholders -> read environment variables FLAMEAI_API_URL / FLAMEAI_SECRET_KEY instead
    static final String URL = setting(API_URL, "FLAMEAI_API_URL").replaceFirst("^POST\\s+", "");  // "POST https://…" as copied is fine
    static final String KEY = setting(SECRET_KEY, "FLAMEAI_SECRET_KEY");

    static String setting(String constant, String envName) {
        boolean placeholder = constant.contains("YOUR_") || constant.contains("api-xxxx");
        String value = placeholder ? System.getenv(envName) : constant;
        return value == null ? "" : value.trim();
    }

    static final Map<String, String> ERRORS = Map.of(
            "bearer_not_found", "Secret Key 가 비어 있습니다. SECRET_KEY 를 확인하세요.",
            "bearer_invalid", "API URL 또는 Secret Key 가 틀렸습니다. Cortex 목록·설정 화면에서 다시 복사하세요.",
            "cortexbox_offline", "FlameBox 가 꺼져 있습니다. PC/서버에서 FlameBox 를 켜 주세요.",
            "cortex_not_found", "API URL 의 Cortex 가 없거나 삭제되었습니다. Cortex 목록에서 다시 복사하세요.",
            "cortex_occupied", "다른 대화가 이 Cortex 를 쓰고 있습니다. /reset 으로 새 대화를 시작하면 이 대화로 가져옵니다.");

    static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();
    static boolean newConversation = true;

    public static void main(String[] args) throws Exception {
        if (URL.isEmpty() || KEY.isEmpty()) {
            System.err.println("파일 위쪽의 API_URL, SECRET_KEY 를 내 값으로 바꾸거나 환경변수 FLAMEAI_API_URL, FLAMEAI_SECRET_KEY 를 설정하세요");
            System.err.println("Set the constants at the top, or the environment variables FLAMEAI_API_URL and FLAMEAI_SECRET_KEY.");
            System.exit(1);
        }
        Charset cs = Charset.forName(System.getProperty("stdin.encoding", Charset.defaultCharset().name()));
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, cs));
        System.out.println("FlameAI chatbot  (/reset: 새 대화, /exit 또는 빈 줄: 종료, /help)");
        System.out.println("첫 응답은 모델을 메모리에 올리느라 조금 걸릴 수 있습니다.");
        while (true) {
            System.out.print("> ");
            String line = in.readLine();
            if (line == null || line.isBlank() || line.trim().equals("/exit")) break;
            switch (line.trim()) {
                case "/reset" -> { newConversation = true; System.out.println("(새 대화를 시작합니다)"); }
                case "/help" -> System.out.println("/reset 새 대화 · /exit 종료 — 그 밖의 입력은 AI 에게 보냅니다");
                default -> System.out.println(chat(line.trim()));
            }
        }
    }

    static String chat(String userMessage) {
        try {
            String json = send(userMessage);
            Matcher error = Pattern.compile("\"error\"\\s*:\\s*\\{.*?\"code\"\\s*:\\s*\"([^\"]+)\"", Pattern.DOTALL).matcher(json);
            if (error.find()) return "[오류] " + ERRORS.getOrDefault(error.group(1), error.group(1));
            newConversation = false;   // from now on only new messages are sent — the Cortex remembers the rest
            Matcher m = Pattern.compile("\"text\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"").matcher(json);
            StringBuilder answer = new StringBuilder();
            while (m.find()) answer.append(unquote(m.group(1)));
            return answer.toString().trim();
        } catch (HttpTimeoutException e) {
            return "[오류] 시간 초과 — 모델을 올리는 중일 수 있습니다. 잠시 뒤 다시 보내 주세요.";
        } catch (Exception e) {
            return "[오류] " + e.getMessage();
        }
    }

    static String send(String userMessage) throws Exception {
        // a new conversation starts with the rules (system) and cortex_reset; after that, only the new message
        String system = newConversation ? "{\"role\": \"system\", \"content\": " + quote(SYSTEM_PROMPT) + "}," : "";
        String body = """
            {"conversationId": %s,
             "options": {"stream": false, "think": false, "cortex_reset": %s},
             "messages": [%s {"role": "user", "content": %s}]}
            """.formatted(quote(CONVERSATION_ID), newConversation, system, quote(userMessage));
        HttpRequest request = HttpRequest.newBuilder(URI.create(URL))
                .header("Authorization", "Bearer " + KEY)
                .header("Content-Type", "application/json")
                .header("X-API-Version", "1")
                .timeout(Duration.ofMinutes(5))   // the first call may load the model
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        return HTTP.send(request, HttpResponse.BodyHandlers.ofString()).body();
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
