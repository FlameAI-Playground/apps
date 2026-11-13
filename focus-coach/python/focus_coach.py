"""
FlameAI Focus Coach — "카메라와 Gemma4 AI를 연동해 보자"

Watches you through the webcam and shows what state you are in:
  자리 (seat) · 상태 (working / resting / sleeping) · 표정 (expression)
Gemma 4 E4B — a vision LLM Cortex on your own FlameBox — looks at 4 frames at a time and answers in JSON.

    python focus_coach.py            then open http://localhost:8080
    (Python 3.9+, standard library only)

Put your own values in the two constants below, or set the environment variables
FLAMEAI_API_URL / FLAMEAI_SECRET_KEY. Do not share or commit this file with your real Secret Key in it.
Frames are sent only to your own Cortex and deleted right after each check; nothing is saved to disk.
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ── Settings — copy from the FlameAI console ─────────────────────────────────
API_URL = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/messages"  # Cortex list › API URL (Gemma 4 E4B)
SECRET_KEY = "YOUR_SECRET_KEY"                                                     # Settings › My API › Secret key
PORT = 8080

# The LLM only describes what it sees (JSON); this program turns it into a state.
SYSTEM_PROMPT = """You look at webcam frames of a person at a desk (camera on top of the monitor). Each message has 4 frames taken 0.5 seconds apart.
Describe only what you see, as one JSON object, no other text:
{"person": true or false, "eyes": "open" or "closed" or "unknown", "head": "upright" or "down" or "on_desk", "looking_at": "screen" or "phone" or "away" or "unknown", "expression": "neutral" or "smiling" or "focused" or "sad" or "tired"}
- person: false if nobody is in the frames.
- head: "down" = head bent down. "on_desk" = head lying on the desk or on the arms."""
CONVERSATION_ID = "focus-coach"


def setting(constant, env_name):
    placeholder = "YOUR_" in constant or "api-xxxx" in constant
    return (os.environ.get(env_name, "") if placeholder else constant).strip()


URL = re.sub(r"^POST\s+", "", setting(API_URL, "FLAMEAI_API_URL"))
BASE = re.sub(r"(/cortex/[^/]+).*$", r"\1", URL)          # …/cortex/{id}  (the action is added per call)
KEY = setting(SECRET_KEY, "FLAMEAI_SECRET_KEY")

ERRORS = {
    "bearer_invalid": "API URL 또는 Secret Key 가 틀렸습니다. Cortex 목록·설정 화면에서 다시 복사하세요.",
    "cortexbox_offline": "FlameBox 가 꺼져 있습니다. PC/서버에서 FlameBox 를 켜 주세요.",
    "cortex_not_found": "API URL 의 Cortex 가 없거나 삭제되었습니다.",
    "cortex_occupied": "다른 대화가 이 Cortex 를 쓰고 있습니다. 잠시 뒤 다시 시작하세요.",
    "bad_request": "요청이 거절되었습니다. 이미지를 받는 Cortex(Gemma 4 E4B 등)인지 확인하세요.",
}


class CoachError(Exception):
    pass


# ── FlameAI calls ────────────────────────────────────────────────────────────
def api(method, path, body=None, content_type="application/json"):
    req = urllib.request.Request(f"{BASE}/{path}", data=body, method=method, headers={
        "Authorization": f"Bearer {KEY}", "X-API-Version": "1", "Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=300) as res:   # the first call may load the model
            data = json.loads(res.read())
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read() or b"{}")
        except ValueError:   # not a FlameAI JSON error (e.g. a gateway error page)
            raise CoachError(f"FlameAI 응답 오류 (HTTP {e.code}) — 잠시 뒤 다시 시도합니다.")
    except urllib.error.URLError as e:
        raise CoachError(f"FlameAI 에 연결하지 못했습니다: {e.reason}")
    if "error" in data:
        code = data["error"].get("code", "")
        raise CoachError(ERRORS.get(code, code) + f"  ({code}: {data['error'].get('message', '')})")
    return data


def look(jpegs):
    """Upload 4 frames, ask the LLM what it sees, delete the frames.
    Returns (description dict, trace dict — what was sent/received, for the page's panels)."""
    t0 = time.time()
    files = [api("POST", "files", jpg, "image/jpeg")["file"] for jpg in jpegs]
    t1 = time.time()
    try:
        content = [{"type": "image", "source": {"type": "file", "file": f}} for f in files]
        content.append({"type": "text", "text": "4 new frames. Reply with the JSON only."})
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}]
        # every check starts fresh (cortex_reset): old frames and answers do not pile up
        options = {"stream": False, "think": False, "cortex_reset": True, "max_tokens": 80,
                   "apply_sampling": True, "temperature": 0}
        request = {"conversationId": CONVERSATION_ID, "options": options, "messages": messages}
        res = api("POST", "messages", json.dumps(request).encode())
        t2 = time.time()
    finally:
        for f in files:
            try:
                api("DELETE", f)
            except CoachError:
                pass
    text = "".join(b.get("text", "") for b in res["message"]["content"] if b.get("type") == "text")
    usage = res["message"].get("usage", {})
    trace = {"request": request, "response": text,
             "image": {"count": len(jpegs), "kb": round(sum(map(len, jpegs)) / 1024, 1)},
             "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens", "thinking_tokens", "prefill_ms", "elapsed_ms")},
             "timing": {"upload": round(t1 - t0, 2), "messages": round(t2 - t1, 2), "delete": round(time.time() - t2, 2)}}
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return (json.loads(m.group(0)) if m else {}), trace
    except json.JSONDecodeError:
        return {}, trace


def state_of(seen):
    """What the LLM saw -> one state."""
    if not seen.get("person", True):
        return "away"
    if seen.get("eyes") == "closed" or (seen.get("head") == "on_desk" and seen.get("eyes") != "open"):
        return "sleeping"
    if seen.get("looking_at") in ("phone", "away"):
        return "resting"
    return "working"


# ── Local web server: the page + one API ─────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] != "/":
            return self.send_json({"error": "not found"}, 404)
        body = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/analyze":
            return self.send_json({"error": "not found"}, 404)
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            jpegs = [base64.b64decode(f) for f in data.get("frames", [])][:4]
            seen, trace = look(jpegs)
            state = state_of(seen)
            print(f"{time.strftime('%H:%M:%S')} {state:8s} {seen} ({trace['timing']['messages']:.1f}s)")
            self.send_json({"state": state, "seen": seen, "trace": trace})
        except CoachError as e:
            self.send_json({"error": str(e)}, 502)
        except Exception as e:   # keep the server alive; the page retries
            self.send_json({"error": f"처리 중 오류: {e}"}, 500)

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):   # keep the console quiet
        pass


PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>카메라와 Gemma4 AI</title>
<style>
 *{box-sizing:border-box}
 body{margin:0;font-family:'Pretendard','Malgun Gothic',sans-serif;background:#f8f6f2;color:#2b2925}
 header{position:relative;text-align:center;padding:.9rem 1rem .2rem} h1{font-size:1.45rem;margin:0} .sub{color:#8a857c;margin:.2rem 0 0;font-size:.92rem}
 .toggles{position:absolute;top:.9rem;right:1rem;display:flex;gap:.4rem}
 .toggles button{font-size:.82rem;padding:.3rem .8rem;border-radius:999px;border:2px solid #ebe5dc;background:#fff;color:#5c5852;font-weight:700;cursor:pointer}
 .toggles button.off{background:#f0ebe3;color:#b3ada3}
 main{display:grid;grid-template-columns:minmax(300px,1fr) minmax(520px,680px) minmax(300px,1fr);gap:16px;padding:14px 16px 18px;height:calc(100vh - 74px)}
 main.no-left{grid-template-columns:minmax(520px,680px) minmax(300px,1fr)} main.no-right{grid-template-columns:minmax(300px,1fr) minmax(520px,680px)}
 main.no-left.no-right{grid-template-columns:minmax(520px,760px);justify-content:center}
 main.no-left #left, main.no-right #right{display:none}
 .panel{background:#fff;border:2px solid #ebe5dc;border-radius:18px;display:flex;flex-direction:column;min-height:0;overflow:hidden}
 .panel h2{font-size:1rem;margin:0;padding:.75rem 1rem;border-bottom:1px solid #f0ebe3;display:flex;justify-content:space-between;align-items:center}
 .panel h2 small{font-weight:400;color:#8a857c;font-size:.8rem}
 .scroll{overflow:auto;padding:.8rem 1rem;flex:1;min-height:0}
 .sec{font-size:.8rem;font-weight:700;color:#e64a32;letter-spacing:.04em;margin:.2rem 0 .4rem}
 .thumbs{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;margin-bottom:.5rem} .thumbs img{width:100%;border-radius:6px;display:block;transform:scaleX(-1)}
 pre.code{background:#f6f8fa;border:1px solid #e1ddd5;border-radius:10px;padding:.6rem .7rem;font:12.5px/1.5 Consolas,monospace;white-space:pre-wrap;word-break:break-word;margin:0 0 .7rem;color:#1f2328}
 .k{color:#0550ae}.s{color:#0a3069}.n{color:#cf222e}
 .meta{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 .7rem} .meta span{background:#f8f6f2;border:1px solid #ebe5dc;border-radius:999px;padding:.12rem .55rem;font-size:.78rem;color:#5c5852}
 .note{color:#8a857c;font-size:.8rem;margin:0 0 .6rem}
 .aib{display:inline-flex;align-items:center;gap:.35rem;padding:.15rem .65rem;border-radius:999px;font:700 .76rem Consolas,monospace;margin-left:.5rem;vertical-align:middle}
 .aib.idle{background:#f0ebe3;color:#8a857c} .aib.cap{background:#e8f1fb;color:#1f5fa8} .aib.busy{background:#fdeee9;color:#c0392b}
 .aib.busy::before{content:"";width:.5rem;height:.5rem;border-radius:50%;background:#e64a32;animation:blink .8s infinite}
 @keyframes blink{50%{opacity:.2}}
 .empty{color:#b3ada3;text-align:center;margin-top:2rem;font-size:.9rem}
 .center{display:flex;flex-direction:column;align-items:center;overflow:auto}
 .stage{position:relative;max-width:100%} video{height:calc(100vh - 330px);min-height:240px;max-width:100%;border-radius:16px;transform:scaleX(-1);background:#222;display:block;aspect-ratio:4/3;object-fit:cover}
 .badge{position:absolute;top:12px;left:12px;padding:.35rem .8rem;border-radius:999px;background:#0009;color:#fff;font-weight:700}
 .timer{font:800 3rem Consolas,monospace;margin:.5rem 0 .1rem}
 .ctrl{display:flex;gap:.5rem;justify-content:center;align-items:center;flex-wrap:wrap}
 input[type=number]{width:4.5rem;font-size:1rem;padding:.3rem;text-align:center}
 .ctrl button{font-size:1rem;padding:.5rem 1.4rem;border-radius:10px;border:0;cursor:pointer;font-weight:700}
 #start{background:#e64a32;color:#fff} #stop{background:#5c5852;color:#fff} .ctrl button:disabled{opacity:.4;cursor:default}
 .status{display:flex;align-items:center;justify-content:center;flex-wrap:wrap;margin:.7rem 0;background:#fff;border:2px solid #ebe5dc;border-radius:999px;padding:.45rem 1.2rem;font-size:1.1rem}
 .status b{margin-left:.35rem} .status .bar{color:#d8d2c7;margin:0 .9rem}
 #msg{min-height:1.4rem;color:#8a857c;font-size:.92rem;text-align:center} #msg.err{color:#c0392b;font-weight:700}
 #log{list-style:none;margin:0;padding:.4rem .6rem;overflow:auto;flex:1;min-height:0}
 #log li{border:1px solid #f0ebe3;border-radius:12px;padding:.5rem .7rem;margin-bottom:.4rem;cursor:pointer;font-size:.86rem}
 #log li:hover{border-color:#f6cfc5;background:#fffaf8} #log li.sys{cursor:default;background:#faf8f4;color:#8a857c}
 #log .row{display:flex;justify-content:space-between;gap:.5rem} #log .no{color:#8a857c;font-family:Consolas,monospace} #log .st{font-weight:700}
 .modal{position:fixed;inset:0;background:#0007;display:none;align-items:center;justify-content:center;padding:20px;z-index:9}
 .modal.open{display:flex}
 .box{background:#fff;border-radius:18px;max-width:1100px;width:100%;max-height:92vh;display:flex;flex-direction:column;overflow:hidden}
 .box h3{margin:0;padding:.8rem 1.1rem;border-bottom:1px solid #f0ebe3;display:flex;justify-content:space-between;align-items:center}
 .box h3 button{background:#f0ebe3;border:0;border-radius:10px;padding:.3rem .8rem;font-size:.9rem;cursor:pointer}
 .cols{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:1rem 1.1rem;overflow:auto}
 .big{grid-template-columns:repeat(2,1fr)}
 @media (max-width:1200px){main,main.no-left,main.no-right,main.no-left.no-right{grid-template-columns:1fr;height:auto} video{height:auto;width:100%}.panel{max-height:70vh}.cols{grid-template-columns:1fr}.toggles{position:static;justify-content:center;margin-top:.5rem}}
</style></head><body>
<header><h1>카메라와 Gemma4 AI</h1><p class="sub">내 PC의 FlameBox(Gemma 4 E4B)가 캠을 보고 지금 상태를 알려 줘요</p>
 <div class="toggles"><button id="tLeft">요청·응답 숨기기</button><button id="tRight">기록 숨기기</button></div></header>
<main id="main">
 <section class="panel" id="left"><h2><span>AI 요청 · 응답<span class="aib idle" id="aiBadge">IDLE</span></span><small id="lastInfo">마지막 1건</small></h2>
  <div class="scroll" id="last"><p class="empty">시작하면 AI에게 보낸 요청과<br>받은 응답이 여기에 나와요</p></div></section>
 <section class="center">
  <div class="stage"><video id="cam" autoplay muted playsinline></video><div class="badge" id="badge">대기</div></div>
  <div class="timer" id="timer">60:00</div>
  <div class="ctrl"><input type="number" id="minutes" min="1" max="600" value="60"> 분
   <button id="start">시작</button><button id="stop" disabled>중지</button></div>
  <div class="status">자리 :<b id="seat">-</b><span class="bar">|</span>상태 :<b id="state">-</b><span class="bar">|</span>표정 :<b id="face">-</b></div>
  <div id="msg">시작을 누르면 4장씩 찍어 AI에게 물어봅니다.</div>
 </section>
 <section class="panel" id="right"><h2>요청 · 응답 기록 <small id="count">0건</small></h2><ul id="log"></ul></section>
</main>
<div class="modal" id="modal"><div class="box"><h3><span id="mTitle"></span><button id="mClose">닫기 ✕</button></h3><div class="cols" id="mBody"></div></div></div>
<script>
const $ = id => document.getElementById(id);
const STATES = {working: "일 또는 공부중", resting: "쉬는 중", sleeping: "자는 중", away: "-"};
const FACES = {neutral: "보통", smiling: "웃음", focused: "집중", sad: "우울", tired: "피곤"};
const SIZE = [384, 288];                // frames go to the AI at this size (JPEG) — smaller = fewer tokens
let running = false, endAt = 0, tick = null, seq = 0, entries = 0;
const canvas = document.createElement("canvas"); canvas.width = SIZE[0]; canvas.height = SIZE[1];

navigator.mediaDevices.getUserMedia({video: {width: 640, height: 480}})
  .then(s => $("cam").srcObject = s)
  .catch(e => show("카메라를 열 수 없습니다: " + e.message, true));

const sleep = ms => new Promise(r => setTimeout(r, ms));
function grab() {                       // one webcam frame -> base64 JPEG
  canvas.getContext("2d").drawImage($("cam"), 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.8).split(",")[1];
}
function show(text, err) { $("msg").className = err ? "err" : ""; $("msg").textContent = text; }
function mmss(ms) { const s = Math.max(0, Math.ceil(ms / 1000)); return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); }
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
function pretty(obj) {                  // JSON with simple colors
  return esc(JSON.stringify(obj, null, 2))
    .replace(/(&quot;[^&]*?&quot;)(\s*:)/g, '<span class="k">$1</span>$2')
    .replace(/:\s(&quot;.*?&quot;)/g, ': <span class="s">$1</span>')
    .replace(/:\s(true|false|null|-?\d+\.?\d*)/g, ': <span class="n">$1</span>');
}
function asJson(text) { try { return JSON.parse(text.match(/\{[\s\S]*\}/)[0]); } catch (e) { return null; } }
function forShow(req) {                 // replace file names with [사진 n] for reading
  let n = 0;
  return {...req, messages: req.messages.map(m => typeof m.content === "string" ? m : {...m,
    content: m.content.map(b => b.type === "image" ? `[사진 ${++n}] ${b.source.file}` : b.text)})};
}

// ── left-panel badge: IDLE / 촬영 중 / 요청 중 ──
let busyTimer = null;
function setAi(kind, text) {
  clearInterval(busyTimer);
  const b = $("aiBadge"); b.className = "aib " + kind;
  if (kind === "busy") {
    const t0 = performance.now();
    const draw = () => b.textContent = `요청 중 ${((performance.now() - t0) / 1000).toFixed(1)}초`;
    draw(); busyTimer = setInterval(draw, 100);
  } else b.textContent = text || "IDLE";
}

// ── hide / show the side panels ──
function toggle(side) {
  const off = $("main").classList.toggle("no-" + side);
  const btn = $(side === "left" ? "tLeft" : "tRight");
  btn.classList.toggle("off", off);
  btn.textContent = (side === "left" ? "요청·응답 " : "기록 ") + (off ? "보이기" : "숨기기");
  try { localStorage.setItem("hide-" + side, off ? "1" : ""); } catch (e) {}
}
$("tLeft").onclick = () => toggle("left");
$("tRight").onclick = () => toggle("right");
try { if (localStorage.getItem("hide-left")) toggle("left"); if (localStorage.getItem("hide-right")) toggle("right"); } catch (e) {}

// ── left panel: the last request and response ──
function renderLast(e) {
  const t = e.result.trace, sys = t.request.messages.find(m => m.role === "system");
  const user = t.request.messages.find(m => m.role === "user").content.filter(b => b.type === "text").map(b => b.text).join("\n");
  const parsed = asJson(t.response), u = t.usage;
  $("lastInfo").textContent = `#${e.no} · ${e.time}`;
  $("last").innerHTML = `
    <div class="sec">요청 (REQUEST)</div>
    <div class="meta"><span>사진 4장 · 0.5초 간격</span><span>${SIZE[0]}x${SIZE[1]} JPEG · ${t.image.kb} KB</span><span>매번 새로 시작 (cortex_reset)</span></div>
    <div class="thumbs">${e.frames.map(f => `<img src="data:image/jpeg;base64,${f}">`).join("")}</div>
    <p class="note">system</p><pre class="code">${esc(sys.content)}</pre>
    <p class="note">user</p><pre class="code">${esc(user)}</pre>
    <div class="sec">응답 (RESPONSE)</div>
    <div class="meta"><span>입력 ${u.input_tokens ?? "-"} 토큰</span><span>출력 ${u.output_tokens ?? "-"} 토큰</span>
      <span>생각 ${u.thinking_tokens ?? "-"} 토큰</span><span>AI 응답 ${t.timing.messages}초</span><span>전체 ${e.secs}초</span></div>
    <pre class="code">${parsed ? pretty(parsed) : esc(t.response)}</pre>`;
}

// ── right panel: log of every request/response ──
function addLog(e) {
  const li = document.createElement("li");
  if (e.sys) { li.className = "sys"; li.textContent = `${e.time}  ${e.sys}`; }
  else {
    const r = e.result, s = r.seen || {};
    li.innerHTML = `<div class="row"><span><span class="no">#${e.no}</span> ${e.time}</span><span class="st">${stateText(r)}</span><span>${e.secs}초</span></div>
      <div class="note" style="margin:.15rem 0 0">눈 ${esc(s.eyes ?? "-")} · 고개 ${esc(s.head ?? "-")} · 시선 ${esc(s.looking_at ?? "-")} · 표정 ${esc(s.expression ?? "-")}</div>`;
    li.onclick = () => openDetail(e);
    entries++;
  }
  $("log").prepend(li);
  while ($("log").children.length > 200) $("log").lastChild.remove();
  $("count").textContent = entries + "건";
}
const seatText = r => r.state === "away" ? "자리 비움" : "앉아 있음";
const stateText = r => r.state === "away" ? "자리 비움" : "앉아 있음 · " + STATES[r.state];

// ── popup: one request/response in detail ──
function openDetail(e) {
  const r = e.result, t = r.trace, parsed = asJson(t.response);
  $("mTitle").textContent = `#${e.no} · ${e.time} · ${stateText(r)}`;
  $("mBody").innerHTML = `
   <div><div class="sec">요청 — 보낸 사진 4장</div><div class="thumbs big">${e.frames.map(f => `<img src="data:image/jpeg;base64,${f}">`).join("")}</div>
     <div class="sec">요청 본문 (POST …/messages)</div><pre class="code">${pretty(forShow(t.request))}</pre></div>
   <div><div class="sec">응답 원문</div><pre class="code">${esc(t.response)}</pre>
     ${parsed ? `<div class="sec">읽은 JSON</div><pre class="code">${pretty(parsed)}</pre>` : `<p class="note">JSON 을 읽지 못했습니다</p>`}
     <div class="sec">토큰 · 시간</div><pre class="code">${pretty({...t.usage, image: t.image, timing_sec: t.timing, total_sec: e.secs})}</pre>
     <div class="sec">프로그램 판단</div><pre class="code">${pretty({seat: seatText(r), state: r.state, expression: (r.seen || {}).expression})}</pre></div>`;
  $("modal").classList.add("open");
}
$("mClose").onclick = () => $("modal").classList.remove("open");
$("modal").onclick = ev => { if (ev.target.id === "modal") $("modal").classList.remove("open"); };
document.addEventListener("keydown", ev => { if (ev.key === "Escape") $("modal").classList.remove("open"); });

// ── start / stop ──
function start() {
  running = true; endAt = Date.now() + Number($("minutes").value || 60) * 60000;
  $("start").disabled = true; $("stop").disabled = false; $("minutes").disabled = true;
  show("지켜보는 중이에요."); addLog({sys: "시작 — " + $("minutes").value + "분", time: new Date().toLocaleTimeString()});
  tick = setInterval(() => { $("timer").textContent = mmss(endAt - Date.now()); if (Date.now() >= endAt) stop(); }, 250);
  watch();
}
function stop() {
  if (!running) return;
  running = false; clearInterval(tick); setAi("idle");
  $("start").disabled = false; $("stop").disabled = true; $("minutes").disabled = false; $("badge").textContent = "대기";
  show("멈췄어요."); addLog({sys: "중지", time: new Date().toLocaleTimeString()});
}
async function watch() {               // 4 frames 0.5 s apart -> ask the AI -> repeat
  while (running) {
    const frames = [];
    for (let i = 0; i < 4; i++) { setAi("cap", `촬영 중 ${i + 1}/4`); frames.push(grab()); if (i < 3) await sleep(500); }
    if (!running) break;
    const t0 = performance.now();
    setAi("busy");
    let r;
    try {
      const res = await fetch("/api/analyze", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({frames})});
      r = await res.json();
    } catch (e) { r = {error: e.message}; }
    setAi("idle");
    if (!running) break;
    if (r.error) { show(r.error, true); await sleep(3000); continue; }
    const e = {no: ++seq, time: new Date().toLocaleTimeString(), frames, result: r, secs: ((performance.now() - t0) / 1000).toFixed(1)};
    renderLast(e); addLog(e); show("지켜보는 중이에요.");
    const s = r.seen || {};
    $("badge").textContent = r.state === "away" ? "자리 비움" : STATES[r.state];
    $("seat").textContent = seatText(r);
    $("state").textContent = STATES[r.state];
    $("face").textContent = r.state === "away" ? "-" : (FACES[s.expression] || s.expression || "-");
  }
}
$("start").onclick = start;
$("stop").onclick = stop;
const q = new URLSearchParams(location.search);          // e.g. http://localhost:8080/?minutes=25&start=1
if (q.get("minutes")) { $("minutes").value = q.get("minutes"); }
$("timer").textContent = mmss(Number($("minutes").value) * 60000);
if (q.get("start") === "1") $("cam").addEventListener("playing", () => start(), {once: true});
</script></body></html>"""


def main():
    if not URL or not KEY:
        raise SystemExit("파일 위쪽의 API_URL, SECRET_KEY 를 내 값으로 바꾸거나 환경변수 FLAMEAI_API_URL, FLAMEAI_SECRET_KEY 를 설정하세요")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)   # this PC only
    print(f"카메라와 Gemma4 AI — 브라우저에서 http://localhost:{PORT} 를 여세요 (종료: Ctrl+C)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
