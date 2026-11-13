"""
FlameAI Turtle-Neck Monitor (derived from focus-coach, 2026-11-13)

Watches you through the webcam while you work or study, and warns or cheers you on.
  - Gemma 4 E4B (a vision LLM Cortex on your FlameBox) reads 4 frames at a time: seat, eyes, head, gaze, expression
  - OpenCV measures the face size to catch a "turtle neck" (head pushed toward the screen)

    pip install "opencv-python>=4.8,<5"
    python turtle_neck_monitor.py    then open http://localhost:8080

Put your own values in the two constants below, or set the environment variables
FLAMEAI_API_URL / FLAMEAI_SECRET_KEY. Do not share or commit this file with your real Secret Key in it.
Frames are sent only to your own Cortex and deleted right after each check; nothing is saved to disk.
"""
import base64
import json
import os
import random
import re
import statistics
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

# ── Settings — copy from the FlameAI console ─────────────────────────────────
API_URL = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/messages"  # Cortex list › API URL (Gemma 4 E4B)
SECRET_KEY = "YOUR_SECRET_KEY"                                                     # Settings › My API › Secret key
PORT = 8080
AI_IMAGE_SIZE = (384, 288)   # frames are shrunk to this size (JPEG) before going to the LLM — smaller = fewer tokens, faster

# ── Coaching rules (change freely) ───────────────────────────────────────────
AWAY_LIMIT = 60       # seconds away from the desk before a warning
REST_LIMIT = 180      # seconds of resting (phone, looking away) before a warning
SLEEP_LIMIT = 20      # seconds of sleeping (eyes closed, head on the desk) before a warning
TURTLE_RATIO = 1.4    # face this much wider than your reference posture = turtle neck
REPEAT_AFTER = 60     # do not repeat the same warning within this many seconds
CHEER_EVERY = 600     # cheer you on every 10 minutes of work

MESSAGES = {
    "away":   "자리를 비운 지 오래됐어요. 돌아와서 이어 가요!",
    "rest":   "쉬는 시간이 길어지고 있어요. 다시 집중해 볼까요?",
    "sleep":  "졸고 있어요! 잠깐 일어나서 스트레칭해요.",
    "turtle": "자세가 어그러졌어요. 바로 잡아주세요.",
    "sad":    "당신의 미래를 위해 웃어봐요.",
    "back":   "돌아왔네요! 할 수 있어요, 힘내요!",
    "done":   "수고 했어요. 쉬었다 다시 해요.",
}
CHEERS = ["잘하고 있어요! 할 수 있어요, 힘내요!", "집중력 최고예요. 이대로 가 봐요!",
          "벌써 이만큼 했어요. 조금만 더 힘내요!", "꾸준함이 실력이에요. 응원해요!"]

# The LLM only describes what it sees; this program makes the decisions.
SYSTEM_PROMPT = """You look at webcam frames of a person at a desk (camera on top of the monitor). Each message has 4 frames taken 0.5 seconds apart.
Describe only what you see, as one JSON object, no other text:
{"person": true or false, "eyes": "open" or "closed" or "unknown", "head": "upright" or "down" or "on_desk", "looking_at": "screen" or "phone" or "away" or "unknown", "expression": "neutral" or "smiling" or "focused" or "sad" or "tired"}
- person: false if nobody is in the frames.
- head: "down" = head bent down. "on_desk" = head lying on the desk or on the arms."""
CONVERSATION_ID = "turtle-neck-monitor"


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


def shrink(jpg):
    """Resize one JPEG frame to AI_IMAGE_SIZE for the LLM (OpenCV keeps measuring the full-size frame)."""
    img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
    small = cv2.resize(img, AI_IMAGE_SIZE, interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()


def look(jpegs):
    """Upload 4 frames, ask the LLM what it sees, delete the frames.
    Returns (description dict, usage dict, trace dict — what was sent/received, for the page's panels)."""
    t0 = time.time()
    small = [shrink(jpg) for jpg in jpegs]
    files = [api("POST", "files", jpg, "image/jpeg")["file"] for jpg in small]
    t1 = time.time()
    try:
        content = [{"type": "image", "source": {"type": "file", "file": f}} for f in files]
        content.append({"type": "text", "text": "4 new frames. Reply with the JSON only."})
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}]
        # every check starts fresh (cortex_reset): old frames and answers do not pile up,
        # so the answer stays short and the speed stays the same
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
             "image": {"size": "%dx%d" % AI_IMAGE_SIZE, "kb": round(sum(map(len, small)) / 1024, 1)},
             "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens", "thinking_tokens", "ctx_used", "ctx_size", "prefill_ms", "elapsed_ms")},
             "timing": {"upload": round(t1 - t0, 2), "messages": round(t2 - t1, 2), "delete": round(time.time() - t2, 2)}}
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return (json.loads(m.group(0)) if m else {}), usage, trace
    except json.JSONDecodeError:
        return {}, usage, trace


# ── OpenCV: face width / frame width (median of the 4 frames) ────────────────
FACES = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def face_width(jpegs):
    ratios = []
    for jpg in jpegs:
        img = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_GRAYSCALE)
        found = FACES.detectMultiScale(img, 1.1, 5, minSize=(40, 40))
        if len(found):
            ratios.append(max(w for (x, y, w, h) in found) / img.shape[1])
    return statistics.median(ratios) if ratios else None


# ── The coach: turns what it sees into states, warnings and cheers ───────────
class Coach:
    def __init__(self):
        self.lock = threading.Lock()
        self.start()

    def start(self):
        self.started = time.time()
        self.state, self.since, self.last = None, time.time(), time.time()
        self.reference, self.calibration = None, []
        self.turtle_hits = self.sad_hits = 0
        self.warned = False
        self.last_warn = {}
        self.work_seconds, self.next_cheer = 0.0, CHEER_EVERY
        self.counts = {k: 0 for k in ("away", "rest", "sleep", "turtle", "sad")}

    def analyze(self, jpegs):
        seen, usage, trace = look(jpegs)
        face = face_width(jpegs)
        now = time.time()

        if not seen.get("person", face is not None):
            state = "away"
        elif seen.get("eyes") == "closed" or (seen.get("head") == "on_desk" and seen.get("eyes") != "open"):
            state = "sleeping"
        elif seen.get("looking_at") in ("phone", "away"):
            state = "resting"
        else:
            state = "working"
        was_working = self.state == "working"
        if state != self.state:
            self.state, self.since = state, now
        duration = now - self.since
        events = []

        if state == "working":
            if was_working:
                self.work_seconds += now - self.last
            if self.warned:
                events.append(("cheer", MESSAGES["back"]))
                self.warned = False
            if self.reference is None and face:          # the first few checks set your normal posture
                self.calibration.append(face)
                if len(self.calibration) >= 3:
                    self.reference = statistics.median(self.calibration)
            ratio = face / self.reference if face and self.reference else None
            self.turtle_hits = self.turtle_hits + 1 if ratio and ratio >= TURTLE_RATIO else 0
            self.sad_hits = self.sad_hits + 1 if seen.get("expression") == "sad" else 0
            if self.turtle_hits >= 2:
                events += self.warn("turtle", now)
            if self.sad_hits >= 2:
                events += self.warn("sad", now)
            if self.work_seconds >= self.next_cheer:
                events.append(("cheer", random.choice(CHEERS)))
                self.next_cheer += CHEER_EVERY
        else:
            kind, limit = {"away": ("away", AWAY_LIMIT), "resting": ("rest", REST_LIMIT),
                           "sleeping": ("sleep", SLEEP_LIMIT)}[state]
            if duration >= limit:
                events += self.warn(kind, now)
                self.warned = True
        self.last = now
        return {"state": state, "seconds": int(duration), "seen": seen,
                "faceRatio": round(face / self.reference, 2) if face and self.reference else None,
                "calibrated": self.reference is not None,
                "events": [{"type": t, "message": m} for t, m in events], "summary": self.summary(), "trace": trace}

    def warn(self, kind, now):
        if now - self.last_warn.get(kind, 0) < REPEAT_AFTER:
            return []
        self.last_warn[kind] = now
        self.counts[kind] += 1
        return [("warn", MESSAGES[kind])]

    def summary(self):
        return {"workMinutes": round(self.work_seconds / 60, 1),
                "totalMinutes": round((time.time() - self.started) / 60, 1), "warnings": self.counts}


coach = Coach()


# ── Local web server: the page + 3 small APIs ────────────────────────────────
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
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            with coach.lock:
                if self.path == "/api/start":
                    coach.start()
                    return self.send_json({"ok": True})
                if self.path == "/api/stop":
                    return self.send_json({"message": MESSAGES["done"], "summary": coach.summary()})
                if self.path == "/api/analyze":
                    jpegs = [base64.b64decode(f) for f in data.get("frames", [])][:4]
                    t0 = time.time()
                    result = coach.analyze(jpegs)
                    print(f"{time.strftime('%H:%M:%S')} {result['state']:8s} {result['seen']} "
                          f"face={result['faceRatio']} {[e['message'] for e in result['events']]} ({time.time() - t0:.1f}s)")
                    return self.send_json(result)
            self.send_json({"error": "not found"}, 404)
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
<title>AI 내가 너를 관리해 주겠어</title>
<style>
 *{box-sizing:border-box}
 body{margin:0;font-family:'Pretendard','Malgun Gothic',sans-serif;background:#f8f6f2;color:#2b2925}
 header{text-align:center;padding:.9rem 1rem .2rem} h1{font-size:1.45rem;margin:0} .sub{color:#8a857c;margin:.2rem 0 0;font-size:.92rem}
 main{display:grid;grid-template-columns:minmax(300px,1fr) minmax(520px,680px) minmax(300px,1fr);gap:16px;padding:14px 16px 18px;height:calc(100vh - 74px)}
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
 button{font-size:1rem;padding:.5rem 1.4rem;border-radius:10px;border:0;cursor:pointer;font-weight:700}
 #start{background:#e64a32;color:#fff} #stop{background:#5c5852;color:#fff} button:disabled{opacity:.4;cursor:default}
 .chips{display:flex;gap:.5rem;justify-content:center;flex-wrap:wrap;margin:.6rem 0}
 .chip{background:#fff;border:2px solid #ebe5dc;border-radius:999px;padding:.3rem .9rem}
 #msg{width:100%;min-height:2.4rem;margin:.3rem 0;padding:.7rem 1rem;border-radius:12px;font-size:1.15rem;font-weight:700;text-align:center}
 .warn{background:#fdeee9;border:2px solid #f6cfc5;color:#c0392b} .cheer{background:#eaf7ee;border:2px solid #bfe5c9;color:#1e7b3c} .info{background:#fff;border:2px solid #ebe5dc}
 #log{list-style:none;margin:0;padding:.4rem .6rem;overflow:auto;flex:1;min-height:0}
 #log li{border:1px solid #f0ebe3;border-radius:12px;padding:.5rem .7rem;margin-bottom:.4rem;cursor:pointer;font-size:.86rem}
 #log li:hover{border-color:#f6cfc5;background:#fffaf8} #log li.sys{cursor:default;background:#faf8f4;color:#8a857c}
 #log .row{display:flex;justify-content:space-between;gap:.5rem} #log .no{color:#8a857c;font-family:Consolas,monospace}
 #log .st{font-weight:700} #log .ev{margin-top:.25rem;font-size:.8rem} #log .ev.w{color:#c0392b} #log .ev.c{color:#1e7b3c}
 .modal{position:fixed;inset:0;background:#0007;display:none;align-items:center;justify-content:center;padding:20px;z-index:9}
 .modal.open{display:flex}
 .box{background:#fff;border-radius:18px;max-width:1100px;width:100%;max-height:92vh;display:flex;flex-direction:column;overflow:hidden}
 .box h3{margin:0;padding:.8rem 1.1rem;border-bottom:1px solid #f0ebe3;display:flex;justify-content:space-between;align-items:center}
 .box h3 button{background:#f0ebe3;padding:.3rem .8rem;font-size:.9rem}
 .cols{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:1rem 1.1rem;overflow:auto}
 .big{grid-template-columns:repeat(2,1fr)}
 @media (max-width:1200px){main{grid-template-columns:1fr;height:auto} video{height:auto;width:100%}.panel{max-height:70vh}.cols{grid-template-columns:1fr}}
</style></head><body>
<header><h1>AI 내가 너를 관리해 주겠어</h1><p class="sub">내 PC의 FlameBox(Gemma 4 E4B)가 캠을 보며 집중을 도와요</p></header>
<main>
 <section class="panel"><h2><span>AI 요청 · 응답<span class="aib idle" id="aiBadge">IDLE</span></span><small id="lastInfo">마지막 1건</small></h2>
  <div class="scroll" id="last"><p class="empty">시작하면 AI에게 보낸 요청과<br>받은 응답이 여기에 나와요</p></div></section>
 <section class="center">
  <div class="stage"><video id="cam" autoplay muted playsinline></video><div class="badge" id="badge">대기</div></div>
  <div class="timer" id="timer">60:00</div>
  <div class="ctrl"><input type="number" id="minutes" min="1" max="600" value="60"> 분
   <button id="start">시작</button><button id="stop" disabled>중지</button>
   <label><input type="checkbox" id="voice" checked> 소리로 알려 주기</label></div>
  <div class="chips"><span class="chip" id="seat">자리: -</span><span class="chip" id="state">상태: -</span>
   <span class="chip" id="posture">자세: -</span><span class="chip" id="face">표정: -</span></div>
  <div id="msg" class="info">시작을 누르면 처음 몇 초 동안 바른 자세를 기준으로 잽니다. 바르게 앉아 주세요.</div>
 </section>
 <section class="panel"><h2>요청 · 응답 기록 <small id="count">0건</small></h2><ul id="log"></ul></section>
</main>
<div class="modal" id="modal"><div class="box"><h3><span id="mTitle"></span><button id="mClose">닫기 ✕</button></h3><div class="cols" id="mBody"></div></div></div>
<script>
const $ = id => document.getElementById(id);
const NAMES = {working: "업무중", resting: "쉬고 있음", sleeping: "자고 있음", away: "자리 비움"};
const FACES = {neutral: "보통", smiling: "웃음", focused: "집중", sad: "우울", tired: "피곤"};
const entries = [];                     // every request/response, for the log and the popup
let running = false, endAt = 0, tick = null, calibrated = false, seq = 0;
const canvas = document.createElement("canvas"); canvas.width = 640; canvas.height = 480;

navigator.mediaDevices.getUserMedia({video: {width: 640, height: 480}})
  .then(s => $("cam").srcObject = s)
  .catch(e => show("info", "카메라를 열 수 없습니다: " + e.message));

const sleep = ms => new Promise(r => setTimeout(r, ms));
let busyTimer = null;
// capture runs on its own: one frame every 0.5 s, keeping the latest 4 — requests never wait for a fresh shoot
let buf = [], fresh = 0, capTimer = null, lastSend = 0;
function startCapture() {
  buf = []; fresh = 0; lastSend = 0;
  const shot = () => { buf.push(grab()); if (buf.length > 4) buf.shift(); fresh++; };
  shot(); capTimer = setInterval(shot, 500);
}
function stopCapture() { clearInterval(capTimer); capTimer = null; }
function setAi(kind, text) {            // left-panel badge: IDLE / 촬영 중 / 요청 중
  clearInterval(busyTimer);
  const b = $("aiBadge"); b.className = "aib " + kind;
  if (kind === "busy") {
    const t0 = performance.now();
    const draw = () => b.textContent = `요청 중 ${((performance.now() - t0) / 1000).toFixed(1)}초`;
    draw(); busyTimer = setInterval(draw, 100);
  } else b.textContent = text || "IDLE";
}
function grab() {                       // one webcam frame -> base64 JPEG
  canvas.getContext("2d").drawImage($("cam"), 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.8).split(",")[1];
}
async function post(path, body) {
  const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body || {})});
  return r.json();
}
function show(type, text) { $("msg").className = type; $("msg").textContent = text; }
function say(text) {
  if (!$("voice").checked || !window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text); u.lang = "ko-KR"; speechSynthesis.speak(u);
}
function beep() {
  try { const a = new AudioContext(), o = a.createOscillator(); o.frequency.value = 880; o.connect(a.destination); o.start(); o.stop(a.currentTime + 0.25); } catch (e) {}
}
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

// ── left panel: the last request and response ──
function renderLast(e) {
  const t = e.result.trace, sys = t.request.messages.find(m => m.role === "system");
  const user = t.request.messages.find(m => m.role === "user").content.filter(b => b.type === "text").map(b => b.text).join("\n");
  const parsed = asJson(t.response), u = t.usage;
  $("lastInfo").textContent = `#${e.no} · ${e.time}`;
  $("last").innerHTML = `
    <div class="sec">요청 (REQUEST)</div>
    <div class="meta"><span>매번 새로 시작 (cortex_reset)</span><span>최근 사진 4장 · 0.5초 간격</span><span>AI 전송 ${t.image.size} JPEG · ${t.image.kb} KB</span></div>
    <div class="thumbs">${e.frames.map(f => `<img src="data:image/jpeg;base64,${f}">`).join("")}</div>
    <p class="note">system</p><pre class="code">${esc(sys.content)}</pre>
    <p class="note">user</p><pre class="code">${esc(user)}</pre>
    <div class="sec">응답 (RESPONSE)</div>
    <div class="meta"><span>입력 ${u.input_tokens ?? "-"} 토큰</span><span>출력 ${u.output_tokens ?? "-"} 토큰</span>
      <span>생각 ${u.thinking_tokens ?? "-"} 토큰</span><span>AI 응답 ${t.timing.messages}초</span><span>전체 ${e.secs}초</span>${e.gap ? `<span>간격 ${e.gap}초</span>` : ""}</div>
    <pre class="code">${parsed ? pretty(parsed) : esc(t.response)}</pre>`;
}

// ── right panel: log of every request/response ──
function addLog(e) {
  const li = document.createElement("li");
  if (e.sys) { li.className = "sys"; li.textContent = `${e.time}  ${e.sys}`; }
  else {
    const r = e.result, s = r.seen || {};
    li.innerHTML = `<div class="row"><span><span class="no">#${e.no}</span> ${e.time}</span><span class="st">${NAMES[r.state]}</span><span>응답 ${e.secs}초${e.gap ? " · 간격 " + e.gap + "초" : ""}</span></div>
      <div class="note" style="margin:.15rem 0 0">눈 ${esc(s.eyes ?? "-")} · 시선 ${esc(s.looking_at ?? "-")} · 표정 ${esc(s.expression ?? "-")}${r.faceRatio ? " · 얼굴 ×" + r.faceRatio : ""}</div>
      ${r.events.map(v => `<div class="ev ${v.type === "warn" ? "w" : "c"}">${v.type === "warn" ? "⚠" : "💪"} ${esc(v.message)}</div>`).join("")}`;
    li.onclick = () => openDetail(e);
  }
  $("log").prepend(li);
  while ($("log").children.length > 200) $("log").lastChild.remove();
  $("count").textContent = entries.length + "건";
}

// ── popup: one request/response in detail ──
function openDetail(e) {
  const r = e.result, t = r.trace, parsed = asJson(t.response);
  $("mTitle").textContent = `#${e.no} · ${e.time} · ${NAMES[r.state]}`;
  $("mBody").innerHTML = `
   <div><div class="sec">요청 — 보낸 사진 4장</div><div class="thumbs big">${e.frames.map(f => `<img src="data:image/jpeg;base64,${f}">`).join("")}</div>
     <div class="sec">요청 본문 (POST …/messages)</div><pre class="code">${pretty(forShow(t.request))}</pre></div>
   <div><div class="sec">응답 원문</div><pre class="code">${esc(t.response)}</pre>
     ${parsed ? `<div class="sec">읽은 JSON</div><pre class="code">${pretty(parsed)}</pre>` : `<p class="note">JSON 을 읽지 못했습니다</p>`}
     <div class="sec">토큰 · 시간</div><pre class="code">${pretty({...t.usage, image: t.image, timing_sec: t.timing, total_sec: e.secs, interval_sec: e.gap})}</pre>
     <div class="sec">프로그램 판단</div><pre class="code">${pretty({state: r.state, seconds_in_state: r.seconds, faceRatio: r.faceRatio, calibrated: r.calibrated, events: r.events.map(v => v.message)})}</pre></div>`;
  $("modal").classList.add("open");
}
$("mClose").onclick = () => $("modal").classList.remove("open");
$("modal").onclick = ev => { if (ev.target.id === "modal") $("modal").classList.remove("open"); };
document.addEventListener("keydown", ev => { if (ev.key === "Escape") $("modal").classList.remove("open"); });

async function start() {
  await post("/api/start");
  running = true; calibrated = false; endAt = Date.now() + Number($("minutes").value || 60) * 60000;
  $("start").disabled = true; $("stop").disabled = false; $("minutes").disabled = true;
  show("info", "바른 자세로 앉아 주세요. 기준 자세를 재는 중이에요."); addLog({sys: "시작 — " + $("minutes").value + "분", time: new Date().toLocaleTimeString()});
  tick = setInterval(() => { $("timer").textContent = mmss(endAt - Date.now()); if (Date.now() >= endAt) finish(true); }, 250);
  startCapture(); watch();
}
async function finish(done) {
  if (!running) return;
  running = false; clearInterval(tick); stopCapture(); setAi("idle");
  $("start").disabled = false; $("stop").disabled = true; $("minutes").disabled = false; $("badge").textContent = "대기";
  const r = await post("/api/stop"), w = r.summary.warnings;
  const text = (done ? r.message : "중지했어요.") + ` 집중 ${r.summary.workMinutes}분 / 전체 ${r.summary.totalMinutes}분`;
  show("cheer", text); say(done ? r.message : "중지했어요.");
  addLog({sys: text + ` (경고: 자리 ${w.away}, 휴식 ${w.rest}, 졸음 ${w.sleep}, 거북목 ${w.turtle}, 표정 ${w.sad})`, time: new Date().toLocaleTimeString()});
}
async function watch() {               // send the latest 4 frames as soon as the previous answer is back
  while (running) {
    while (running && fresh < 4) { setAi("cap", `촬영 중 ${fresh}/4`); await sleep(100); }   // 4 new frames since the last request
    if (!running) break;
    const frames = buf.slice(); fresh = 0;
    const t0 = performance.now(), gap = lastSend ? ((t0 - lastSend) / 1000).toFixed(1) : null;
    lastSend = t0;
    setAi("busy");
    let r;
    try { r = await post("/api/analyze", {frames}); } catch (e) { r = {error: e.message}; }
    setAi("idle");
    if (!running) break;
    if (r.error) { show("warn", r.error); await sleep(3000); continue; }
    const e = {no: ++seq, time: new Date().toLocaleTimeString(), frames, result: r, gap, secs: ((performance.now() - t0) / 1000).toFixed(1)};
    entries.push(e); if (entries.length > 200) entries.shift();
    renderLast(e); addLog(e);
    const s = r.seen || {};
    $("badge").textContent = NAMES[r.state] + (r.state === "working" ? "" : ` ${r.seconds}초`);
    $("seat").textContent = "자리: " + (r.state === "away" ? "비움" : "앉아 있음");
    $("state").textContent = "상태: " + NAMES[r.state];
    $("posture").textContent = "자세: " + (!r.calibrated ? "기준 재는 중" : r.faceRatio ? `기준의 ${r.faceRatio}배` : "-");
    $("face").textContent = "표정: " + (FACES[s.expression] || "-");
    if (r.calibrated && !calibrated) { calibrated = true; show("info", "기준 자세를 저장했어요. 이제 지켜볼게요. 힘내요!"); }
    for (const v of r.events) { show(v.type, v.message); say(v.message); if (v.type === "warn") beep(); }
  }
}
$("start").onclick = start;
$("stop").onclick = () => finish(false);
const q = new URLSearchParams(location.search);          // e.g. http://localhost:8080/?minutes=25&start=1
if (q.get("minutes")) { $("minutes").value = q.get("minutes"); }
$("timer").textContent = mmss(Number($("minutes").value) * 60000);
if (q.get("start") === "1") $("cam").addEventListener("playing", () => start(), {once: true});
</script></body></html>"""


def main():
    if not URL or not KEY:
        raise SystemExit("파일 위쪽의 API_URL, SECRET_KEY 를 내 값으로 바꾸거나 환경변수 FLAMEAI_API_URL, FLAMEAI_SECRET_KEY 를 설정하세요")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)   # this PC only
    print(f"AI 내가 너를 관리해 주겠어 — 브라우저에서 http://localhost:{PORT} 를 여세요 (종료: Ctrl+C)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
