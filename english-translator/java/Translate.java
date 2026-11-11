import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * FlameAI English Translator — Korean <-> English (Java 8+, no libraries).
 *
 *   javac -encoding UTF-8 Translate.java
 *   java Translate "Good morning"
 *   java Translate --to ja < note.txt      (UTF-8 file or pipe)
 *
 * On Windows, Java may break Korean text given as a command-line argument —
 * use standard input (a UTF-8 file or pipe) for Korean text.
 *
 * Environment variables: FLAMEAI_API_BASE, FLAMEAI_SECRET_KEY, FLAMEAI_CORTEX_ID
 * Same behaviour as ../python/translate.py (see README).
 */
public class Translate {

    static final String SYSTEM_PROMPT =
        "You are a professional translator. Translate the user's text into %s. "
        + "Output only the translation - no explanations, no quotes, no notes. "
        + "Keep line breaks, numbers, code and proper nouns as they are.";

    public static void main(String[] args) throws Exception {
        String base = env("FLAMEAI_API_BASE").replaceAll("/+$", "");
        String key = env("FLAMEAI_SECRET_KEY");
        String cortex = env("FLAMEAI_CORTEX_ID");

        String to = null;
        StringBuilder text = new StringBuilder();
        for (int i = 0; i < args.length; i++) {
            if (args[i].equals("--to") && i + 1 < args.length) { to = args[++i]; continue; }
            text.append(text.length() > 0 ? " " : "").append(args[i]);
        }
        if (text.length() == 0) {  // no text argument -> read standard input as UTF-8 (file, pipe)
            text.append(read(System.in));
        }
        if (text.toString().trim().isEmpty()) {
            System.err.println("usage: java Translate [--to ja] \"text\"   or   java Translate < note.txt");
            System.exit(1);
        }
        String target = to != null ? language(to) : (text.toString().matches("(?s).*[\\uac00-\\ud7a3].*") ? "English" : "Korean");

        String body = "{\"conversationId\":\"english-translator\","
            + "\"options\":{\"stream\":false,\"think\":false,\"cortex_reset\":true},"
            + "\"messages\":[{\"role\":\"system\",\"content\":" + quote(String.format(SYSTEM_PROMPT, target)) + "},"
            + "{\"role\":\"user\",\"content\":" + quote(text.toString()) + "}]}";

        HttpURLConnection con = (HttpURLConnection) new URL(base + "/cortex/" + cortex + "/messages").openConnection();
        con.setRequestMethod("POST");
        con.setDoOutput(true);
        con.setConnectTimeout(10_000);
        con.setReadTimeout(300_000);  // the first call may load the model
        con.setRequestProperty("Authorization", "Bearer " + key);
        con.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        con.setRequestProperty("X-API-Version", "1");
        try (OutputStream out = con.getOutputStream()) {
            out.write(body.getBytes(StandardCharsets.UTF_8));
        }
        int status = con.getResponseCode();
        String json = read(status < 400 ? con.getInputStream() : con.getErrorStream());

        Matcher err = Pattern.compile("\"error\"\\s*:\\s*\\{.*?\"code\"\\s*:\\s*\"([^\"]+)\"", Pattern.DOTALL).matcher(json);
        if (err.find()) {
            System.err.println("[error] " + err.group(1) + " (HTTP " + status + ")");
            System.exit(1);
        }
        // answer text = "text" fields of the text blocks in message.content
        Matcher m = Pattern.compile("\"text\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"").matcher(json);
        StringBuilder answer = new StringBuilder();
        while (m.find()) answer.append(unquote(m.group(1)));
        System.out.println(answer.toString().trim());
    }

    static String env(String name) {
        String v = System.getenv(name);
        if (v == null || v.trim().isEmpty()) {
            System.err.println("Set environment variable " + name);
            System.exit(1);
        }
        return v.trim();
    }

    static String language(String code) {
        switch (code.toLowerCase()) {
            case "ko": return "Korean";
            case "en": return "English";
            case "ja": return "Japanese";
            case "zh": return "Simplified Chinese";
            case "es": return "Spanish";
            case "fr": return "French";
            case "de": return "German";
            case "vi": return "Vietnamese";
            default: return code;
        }
    }

    static String read(InputStream in) throws Exception {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] b = new byte[8192];
        for (int n; (n = in.read(b)) > 0; ) buf.write(b, 0, n);
        return new String(buf.toByteArray(), StandardCharsets.UTF_8);
    }

    static String quote(String s) {
        StringBuilder sb = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int) c)); else sb.append(c);
            }
        }
        return sb.append('"').toString();
    }

    static String unquote(String s) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c != '\\' || i + 1 >= s.length()) { sb.append(c); continue; }
            char n = s.charAt(++i);
            switch (n) {
                case 'n': sb.append('\n'); break;
                case 't': sb.append('\t'); break;
                case 'r': sb.append('\r'); break;
                case 'b': sb.append('\b'); break;
                case 'f': sb.append('\f'); break;
                case 'u': sb.append((char) Integer.parseInt(s.substring(i + 1, i + 5), 16)); i += 4; break;
                default: sb.append(n);
            }
        }
        return sb.toString();
    }
}
