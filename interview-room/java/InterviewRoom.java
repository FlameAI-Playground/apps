import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * FlameAI Interview Room — practice a remote (video call) job interview with an AI interviewer (Java 21+, no libraries).
 *
 *   cd interview-room/java
 *   java InterviewRoom.java          -> open http://localhost:8790
 *
 * You speak (browser speech recognition) or type; the interviewer answers in text, like subtitles.
 * When the interview ends, the whole conversation is sent to the same Cortex again as an "evaluator" for a score sheet.
 *
 * Put your own values in the two constants below.
 * Do not share or commit this file with your real Secret Key in it.
 */
public class InterviewRoom {

    // ── Settings — copy from the FlameAI console ─────────────────────────────
    static final String API_URL    = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/messages"; // Cortex list › API URL (text LLM)
    static final String SECRET_KEY = "YOUR_SECRET_KEY";                                                     // Settings › My API › Secret key
    static final int PORT = 8790;

    // ── The two interview rooms (change freely) ──────────────────────────────
    record Room(String id, String name, String title, String style, String image) {}
    static final Map<String, Room> ROOMS = Map.of(
            "1", new Room("1", "한서연", "인사팀장",
                    "차분하고 친절하지만 날카로운 면접관입니다. 지원자가 편하게 말하도록 돕되, 답이 모호하면 구체적인 경험과 숫자를 꼭 되묻습니다.",
                    "interviewer_f.png"),
            "2", new Room("2", "강태호", "개발본부장",
                    "엄격한 압박 면접관입니다. 답의 허점이나 앞뒤가 맞지 않는 부분을 짚어 반문하고, \"그래서 결과는요?\"처럼 결론을 요구합니다. 무례하거나 모욕적인 말은 하지 않습니다.",
                    "interviewer_m.png"));

    static final String INTERVIEWER_PROMPT = """
            당신은 회사 '플레임테크'의 {name} {title}입니다. 지금 원격 화상 면접에서 '{job}' 직무 지원자를 면접하고 있습니다.
            성격: {style}

            규칙:
            - 실제 면접관처럼 한국어 존댓말로 말합니다. 한 번에 질문은 하나, 2~3문장 이내로 짧게 말합니다.
            - 말할 내용만 씁니다. Markdown, 이모지, 괄호나 별표로 쓴 행동 묘사는 쓰지 않습니다.
            - 지원자의 대답을 대신 쓰거나 모범 답안을 알려 주지 않습니다. 당신이 AI 라는 말은 하지 않습니다.
            - 대답이 짧거나 모호하면 꼬리 질문을 한 번 합니다. 그다음에는 다음 질문으로 넘어갑니다.
            - 진행 순서: 인사와 1분 자기소개 요청 → 지원 동기 → 직무 경험 → 어려운 문제를 해결한 사례 → 협업과 갈등 경험 → 마지막으로 하고 싶은 말.
            - 마지막 말을 들은 뒤 짧게 마무리 인사를 하고, 맨 끝에 [면접종료] 를 붙입니다. 그 전에는 [면접종료] 를 쓰지 않습니다.
            """;

    static final String EVALUATOR_PROMPT = """
            당신은 채용 면접 코치입니다. 아래 면접 기록을 읽고 지원자를 평가합니다. 후하게 주지 말고, 기록에 있는 말만 근거로 씁니다.
            괄호 안의 답변 시간도 참고합니다(너무 짧거나 긴 답).
            Markdown 없이 아래 형식 그대로 씁니다.

            총평: (한 문장)
            논리성: N/5
            구체성: N/5
            직무 이해: N/5
            전달력: N/5
            잘한 점:
            - ...
            - ...
            고칠 점:
            - (어느 질문에서 무엇을) ...
            - ...
            다시 연습할 질문: (질문 하나) — 더 좋은 답의 방향 한 줄
            """;

    // Constants left as placeholders -> read environment variables FLAMEAI_API_URL / FLAMEAI_SECRET_KEY instead
    static final String URL = setting(API_URL, "FLAMEAI_API_URL").replaceFirst("^POST\\s+", "");
    static final String KEY = setting(SECRET_KEY, "FLAMEAI_SECRET_KEY");

    static String setting(String constant, String envName) {
        boolean placeholder = constant.contains("YOUR_") || constant.contains("api-xxxx");
        String value = placeholder ? System.getenv(envName) : constant;
        return value == null ? "" : value.trim();
    }

    static final Map<String, String> ERRORS = Map.of(
            "bearer_invalid", "API URL 또는 Secret Key 가 틀렸습니다. Cortex 목록·설정 화면에서 다시 복사하세요.",
            "cortexbox_offline", "FlameBox 가 꺼져 있습니다. PC/서버에서 FlameBox 를 켜 주세요.",
            "cortex_not_found", "API URL 의 Cortex 가 없거나 삭제되었습니다. Cortex 목록에서 다시 복사하세요.",
            "cortex_occupied", "다른 대화가 이 Cortex 를 쓰고 있습니다. 면접을 새로 시작하면 이 면접으로 가져옵니다.");

    static final HttpClient HTTP = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();
    static final String CONVERSATION_ID = "interview-room";
    static final Path IMAGES = Files.isDirectory(Path.of("images")) ? Path.of("images") : Path.of("..", "images");

    // ── One interview at a time (this PC only) ───────────────────────────────
    static Room room;
    static String job = "";
    static final List<String> transcript = new ArrayList<>();   // kept here: the evaluator needs the whole conversation

    public static void main(String[] args) throws Exception {
        if (URL.isEmpty() || KEY.isEmpty()) {
            System.err.println("파일 위쪽의 API_URL, SECRET_KEY 를 내 값으로 바꾸세요 (또는 환경변수 FLAMEAI_API_URL, FLAMEAI_SECRET_KEY).");
            System.exit(1);
        }
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", PORT), 0);   // this PC only
        server.createContext("/", InterviewRoom::handle);
        server.start();
        System.out.println("면접실이 열렸습니다 → http://localhost:" + PORT + "   (Ctrl+C 로 종료)");
    }

    static void handle(HttpExchange ex) throws IOException {
        String path = ex.getRequestURI().getPath();
        try {
            if (path.equals("/")) {
                reply(ex, 200, "text/html; charset=utf-8", PAGE.getBytes(StandardCharsets.UTF_8));
            } else if (path.startsWith("/img/") && path.matches("/img/[\\w.-]+\\.png")) {
                Path f = IMAGES.resolve(path.substring(5));
                if (Files.exists(f)) reply(ex, 200, "image/png", Files.readAllBytes(f));
                else reply(ex, 404, "text/plain", new byte[0]);
            } else if (path.equals("/api/rooms")) {
                StringBuilder sb = new StringBuilder("[");
                for (String id : List.of("1", "2")) {
                    Room r = ROOMS.get(id);
                    if (sb.length() > 1) sb.append(',');
                    sb.append("{\"id\":%s,\"name\":%s,\"title\":%s,\"image\":%s}".formatted(quote(r.id()), quote(r.name()), quote(r.title()), quote(r.image())));
                }
                json(ex, sb.append(']').toString());
            } else if (path.equals("/api/start")) {
                String body = new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
                json(ex, start(field(body, "room"), field(body, "job")));
            } else if (path.equals("/api/answer")) {
                String body = new String(ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
                json(ex, answer(field(body, "text"), field(body, "seconds")));
            } else if (path.equals("/api/evaluate")) {
                json(ex, evaluate());
            } else {
                reply(ex, 404, "text/plain", new byte[0]);
            }
        } catch (Exception e) {
            json(ex, "{\"error\":" + quote(String.valueOf(e.getMessage())) + "}");
        }
    }

    // ── Interview: start, answer, evaluate ───────────────────────────────────
    static synchronized String start(String roomId, String jobName) {
        room = ROOMS.getOrDefault(roomId, ROOMS.get("1"));
        job = jobName.isBlank() ? "백엔드 개발자" : jobName.trim();
        transcript.clear();
        String system = INTERVIEWER_PROMPT.replace("{name}", room.name()).replace("{title}", room.title())
                .replace("{job}", job).replace("{style}", room.style());
        // a new interview starts with the rules (system) and cortex_reset; after that, only the new answer is sent
        return turn(system, "(지원자가 화상 면접실에 입장했습니다. 면접을 시작해 주세요.)", true);
    }

    static synchronized String answer(String text, String seconds) {
        if (room == null) return "{\"error\":\"먼저 면접실에 입장하세요.\"}";
        transcript.add("지원자 (답변 " + (seconds.isBlank() ? "?" : seconds) + "초): " + text);
        return turn(null, text, false);
    }

    static String turn(String system, String userText, boolean reset) {
        String options = reset
                ? "{\"stream\": false, \"think\": false, \"cortex_reset\": true, \"apply_sampling\": true, \"temperature\": 0.7, \"max_tokens\": 400}"
                : "{\"stream\": false, \"think\": false}";
        Result r = call(system, userText, options);
        if (r.error != null) return "{\"error\":" + quote(r.error) + "}";
        boolean ended = r.text.contains("[면접종료]");
        String say = r.text.replace("[면접종료]", "").trim();
        transcript.add(room.name() + " " + room.title() + ": " + say);
        return "{\"say\":%s,\"ended\":%s}".formatted(quote(say), ended);
    }

    static synchronized String evaluate() throws IOException {
        if (transcript.isEmpty()) return "{\"error\":\"면접 기록이 없습니다.\"}";
        String record = "직무: " + job + "\n\n" + String.join("\n", transcript);
        // the evaluator is a separate, fresh conversation on the same Cortex — the interviewer never breaks character
        Result r = call(EVALUATOR_PROMPT, record,
                "{\"stream\": false, \"think\": false, \"cortex_reset\": true, \"apply_sampling\": true, \"temperature\": 0.2, \"max_tokens\": 1200}");
        if (r.error != null) return "{\"error\":" + quote(r.error) + "}";
        String file = "interview_" + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmm")) + ".txt";
        Files.writeString(Path.of(file), record + "\n\n──── 평가 ────\n" + r.text + "\n", StandardCharsets.UTF_8);
        return "{\"report\":%s,\"file\":%s}".formatted(quote(r.text), quote(file));
    }

    // ── FlameAI /messages call ───────────────────────────────────────────────
    record Result(String text, String error) {}

    static Result call(String system, String userText, String options) {
        String sys = system == null ? "" : "{\"role\": \"system\", \"content\": " + quote(system) + "},";
        String body = """
            {"conversationId": %s, "options": %s,
             "messages": [%s {"role": "user", "content": %s}]}
            """.formatted(quote(CONVERSATION_ID), options, sys, quote(userText));
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(URL))
                    .header("Authorization", "Bearer " + KEY)
                    .header("Content-Type", "application/json")
                    .header("X-API-Version", "1")
                    .timeout(Duration.ofMinutes(5))   // the first call may load the model
                    .POST(HttpRequest.BodyPublishers.ofString(body))
                    .build();
            String json = HTTP.send(request, HttpResponse.BodyHandlers.ofString()).body();
            Matcher error = Pattern.compile("\"error\"\\s*:\\s*\\{.*?\"code\"\\s*:\\s*\"([^\"]+)\"", Pattern.DOTALL).matcher(json);
            if (error.find()) return new Result(null, ERRORS.getOrDefault(error.group(1), error.group(1)));
            Matcher m = Pattern.compile("\"text\"\\s*:\\s*\"((?:\\\\.|[^\"\\\\])*)\"").matcher(json);
            StringBuilder text = new StringBuilder();
            while (m.find()) text.append(unquote(m.group(1)));
            return new Result(text.toString().trim(), null);
        } catch (java.net.http.HttpTimeoutException e) {
            return new Result(null, "시간 초과 — 모델을 올리는 중일 수 있습니다. 잠시 뒤 다시 보내 주세요.");
        } catch (Exception e) {
            return new Result(null, String.valueOf(e.getMessage()));
        }
    }

    // ── small HTTP / JSON helpers (use Jackson or Gson in real projects) ─────
    static void json(HttpExchange ex, String s) throws IOException {
        reply(ex, 200, "application/json; charset=utf-8", s.getBytes(StandardCharsets.UTF_8));
    }

    static void reply(HttpExchange ex, int status, String type, byte[] data) throws IOException {
        ex.getResponseHeaders().set("Content-Type", type);
        ex.sendResponseHeaders(status, data.length == 0 ? -1 : data.length);
        if (data.length > 0) ex.getResponseBody().write(data);
        ex.close();
    }

    static String field(String json, String name) {
        Matcher m = Pattern.compile("\"" + name + "\"\\s*:\\s*(?:\"((?:\\\\.|[^\"\\\\])*)\"|([\\d.]+))").matcher(json);
        if (!m.find()) return "";
        return m.group(1) != null ? unquote(m.group(1)) : m.group(2);
    }

    static String quote(String s) {
        StringBuilder sb = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                case '<' -> sb.append("\\u003c");   // safe to embed in HTML
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

    // ── Web page: lobby (two rooms) + video-call room ────────────────────────
    static final String PAGE = """
<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>원격 면접 연습 · FlameAI</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f3f1ec;color:#23211e;font-family:'Pretendard','Malgun Gothic',sans-serif;min-height:100vh}
button{font:inherit;cursor:pointer}
.hide{display:none!important}
/* lobby */
#lobby{max-width:980px;margin:0 auto;padding:48px 20px}
#lobby h1{font-size:34px;font-weight:800}
#lobby p.sub{color:#77716a;margin:8px 0 28px}
.job{display:flex;gap:10px;align-items:center;margin-bottom:24px}
.job input{flex:0 1 320px;padding:12px 14px;border:1px solid #d8d2c7;border-radius:10px;font:inherit;background:#fff}
.rooms{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}
.card{background:#fff;border:1px solid #e3ddd3;border-radius:18px;overflow:hidden;text-align:left;padding:0}
.card:hover{border-color:#e74830;box-shadow:0 6px 24px rgba(0,0,0,.08)}
.card .pic{aspect-ratio:16/9;background:#ddd center/cover}
.card .info{padding:16px 18px}
.card b{font-size:20px}.card span{display:block;color:#77716a;margin-top:4px}
.card .enter{display:inline-block;margin-top:12px;color:#e74830;font-weight:700}
/* room */
#room{height:100vh;display:flex;flex-direction:column;background:#1d1f23;color:#fff}
.bar{display:flex;align-items:center;gap:14px;padding:12px 20px;font-size:15px;color:#c9ccd2}
.bar b{color:#fff}.live{color:#ff6b57;font-weight:700}
.tiles{flex:1;display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:0 12px;min-height:0}
.tile{position:relative;border-radius:16px;overflow:hidden;background:#2b2e34 center/cover}
.tile video{width:100%;height:100%;object-fit:cover;transform:scaleX(-1)}
.tag{position:absolute;left:14px;top:12px;background:rgba(0,0,0,.45);padding:4px 10px;border-radius:8px;font-size:14px}
.tile.speaking{box-shadow:inset 0 0 0 3px #4cd28a}
.history{position:absolute;left:0;right:0;bottom:120px;max-height:40%;overflow:hidden;padding:0 18px;display:flex;flex-direction:column;justify-content:flex-end;gap:6px;font-size:14px}
.history div{background:rgba(0,0,0,.35);padding:6px 10px;border-radius:8px;opacity:.75;align-self:flex-start;max-width:90%}
.history div.me{align-self:flex-end;background:rgba(231,72,48,.35)}
.caption{position:absolute;left:0;right:0;bottom:0;min-height:110px;padding:16px 22px;background:linear-gradient(transparent,rgba(0,0,0,.82) 30%);font-size:20px;line-height:1.5}
.caption small{display:block;color:#9fe3bd;font-size:14px;margin-bottom:4px}
.mine{position:absolute;left:0;right:0;bottom:0;padding:14px 18px;background:linear-gradient(transparent,rgba(0,0,0,.75) 30%);font-size:17px;min-height:70px;color:#ffe2db}
.nocam{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#888}
.controls{display:flex;gap:10px;align-items:center;justify-content:center;padding:14px;flex-wrap:wrap}
.controls button{border:0;border-radius:999px;padding:12px 20px;background:#3a3e46;color:#fff}
.controls button.on{background:#e74830}
.controls input{width:min(460px,60vw);padding:12px 16px;border-radius:999px;border:0;background:#2b2e34;color:#fff;font:inherit}
#end{background:#b3261e}
#status{font-size:14px;color:#9aa0a8;min-width:140px;text-align:center}
/* report */
#report{position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;padding:20px}
#report .box{background:#fff;color:#23211e;border-radius:18px;max-width:720px;width:100%;max-height:90vh;overflow:auto;padding:28px}
#report h2{margin-bottom:14px}
#report pre{white-space:pre-wrap;font:16px/1.7 'Pretendard','Malgun Gothic',sans-serif}
#report .row{display:flex;gap:10px;margin-top:18px}
#report button{border:0;border-radius:10px;padding:10px 16px;background:#e74830;color:#fff}
@media (max-width:760px){.tiles{grid-template-columns:1fr}}
</style></head><body>

<section id="lobby">
  <h1>원격 면접 연습</h1>
  <p class="sub">면접실을 고르면 화상 면접이 시작됩니다. 말로 답하면 글자로 바뀌어 면접관에게 전달됩니다.</p>
  <div class="job"><label>지원 직무</label><input id="job" value="백엔드 개발자"></div>
  <div class="rooms" id="rooms"></div>
</section>

<section id="room" class="hide">
  <div class="bar"><b id="roomName"></b><span id="jobName"></span><span style="flex:1"></span><span id="clock">00:00</span><span class="live">● LIVE</span></div>
  <div class="tiles">
    <div class="tile" id="them"><span class="tag" id="themTag"></span>
      <div class="history" id="history"></div>
      <div class="caption"><small id="who"></small><span id="say">연결 중…</span></div></div>
    <div class="tile" id="me"><video id="cam" autoplay muted playsinline></video><div class="nocam hide" id="nocam">카메라 꺼짐</div>
      <span class="tag">나</span><div class="mine" id="mine"></div></div>
  </div>
  <div class="controls">
    <button id="mic">🎤 말하기</button>
    <input id="text" placeholder="말 대신 입력해도 됩니다 (Enter 로 보내기)">
    <button id="tts">🔈 읽어 주기 꺼짐</button>
    <span id="status"></span>
    <button id="end">면접 끝내기</button>
  </div>
</section>

<div id="report" class="hide"><div class="box"><h2>면접 평가</h2><pre id="reportText">평가하는 중…</pre>
  <div class="row"><button onclick="location.reload()">면접실 나가기</button></div></div></div>

<script>
const $ = id => document.getElementById(id);
let busy = false, ended = false, t0 = 0, answerStart = 0, speak = false, recog = null, listening = false, finalText = '';

fetch('/api/rooms').then(r => r.json()).then(rooms => {
  $('rooms').innerHTML = rooms.map(r => `<button class="card" onclick="enter('${r.id}')">
    <div class="pic" style="background-image:url(/img/${r.image})"></div>
    <div class="info"><b>면접실 ${r.id}</b><span>${r.name} ${r.title}</span><span class="enter">입장하기 →</span></div></button>`).join('');
  window.ROOMS = rooms;
});

async function post(url, body) {
  const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})});
  return r.json();
}

async function enter(id) {
  const r = ROOMS.find(x => x.id === id), job = $('job').value.trim() || '백엔드 개발자';
  $('lobby').classList.add('hide'); $('room').classList.remove('hide');
  $('roomName').textContent = `원격 면접실 ${id}`; $('jobName').textContent = `· ${job}`;
  $('them').style.backgroundImage = `url(/img/${r.image})`;
  $('themTag').textContent = $('who').textContent = `${r.name} ${r.title}`;
  t0 = Date.now(); setInterval(() => { const s = Math.floor((Date.now() - t0) / 1000);
    $('clock').textContent = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0'); }, 1000);
  navigator.mediaDevices?.getUserMedia({video: true}).then(s => $('cam').srcObject = s).catch(() => $('nocam').classList.remove('hide'));
  setupMic();
  await ask('/api/start', {room: id, job});
}

async function ask(url, body) {
  busy = true; $('status').textContent = '면접관이 생각하는 중…'; $('them').classList.add('speaking');
  const res = await post(url, body);
  busy = false; $('status').textContent = ''; $('them').classList.remove('speaking');
  if (res.error) { $('say').textContent = '[오류] ' + res.error; return; }
  await typeOut(res.say);
  if (speak) say(res.say);
  answerStart = Date.now();
  if (res.ended) { ended = true; $('status').textContent = '면접이 끝났습니다'; setTimeout(evaluate, 1500); }
}

function addHistory(text, me) {
  if (!text || text === '연결 중…') return;
  const d = document.createElement('div'); d.textContent = (me ? '나: ' : '') + text; if (me) d.className = 'me';
  $('history').appendChild(d); while ($('history').children.length > 4) $('history').firstChild.remove();
}

function typeOut(text) {
  return new Promise(done => { let i = 0; $('say').textContent = '';
    const t = setInterval(() => { $('say').textContent = text.slice(0, ++i); if (i >= text.length) { clearInterval(t); done(); } }, 35); });
}

function send(text) {
  text = text.trim(); if (!text || busy || ended) return;
  const sec = Math.round((Date.now() - answerStart) / 1000);
  addHistory($('say').textContent, false); $('say').textContent = '…';
  addHistory(text, true); $('mine').textContent = ''; $('text').value = '';
  ask('/api/answer', {text, seconds: sec});
}
$('text').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) send($('text').value); });

// speech -> text (Chrome / Edge). The browser's own speech service turns your voice into text.
function setupMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { $('mic').classList.add('hide'); $('text').placeholder = '이 브라우저는 음성 인식이 안 됩니다 — 입력해서 답하세요'; return; }
  recog = new SR(); recog.lang = 'ko-KR'; recog.continuous = true; recog.interimResults = true;
  recog.onresult = e => { let interim = ''; finalText = '';
    for (const r of e.results) { if (r.isFinal) finalText += r[0].transcript; else interim += r[0].transcript; }
    $('mine').textContent = finalText + interim; };
  recog.onend = () => { if (listening) recog.start(); };   // keeps listening through pauses
  $('mic').onclick = () => {
    if (!listening) { if (busy || ended) return; listening = true; finalText = ''; recog.start();
      $('mic').classList.add('on'); $('mic').textContent = '✔ 답변 완료'; $('me').classList.add('speaking'); }
    else { listening = false; recog.stop(); $('mic').classList.remove('on'); $('mic').textContent = '🎤 말하기'; $('me').classList.remove('speaking');
      setTimeout(() => send($('mine').textContent), 300); }
  };
}

$('tts').onclick = () => { speak = !speak; $('tts').classList.toggle('on', speak); $('tts').textContent = speak ? '🔊 읽어 주기 켜짐' : '🔈 읽어 주기 꺼짐'; };
function say(text) { const u = new SpeechSynthesisUtterance(text); u.lang = 'ko-KR'; speechSynthesis.cancel(); speechSynthesis.speak(u); }

$('end').onclick = () => { if (!busy && confirm('면접을 끝내고 평가를 받을까요?')) evaluate(); };
async function evaluate() {
  ended = true; if (listening) $('mic').click();
  $('report').classList.remove('hide');
  const res = await post('/api/evaluate');
  $('reportText').textContent = res.error ? '[오류] ' + res.error : res.report + '\\n\\n(기록 저장: ' + res.file + ')';
}
</script></body></html>
""";
}
