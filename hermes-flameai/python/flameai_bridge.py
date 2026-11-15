"""
FlameAI Bridge — use your FlameAI Cortex from any OpenAI-compatible agent (Hermes Agent, etc.).
Python 3.9+, standard library only. One file.

    python flameai_bridge.py            -> http://127.0.0.1:8765/v1   (Ctrl+C to stop)

Then point the agent at it, e.g. Hermes Agent:
    hermes setup model  ->  Custom endpoint  ->  URL http://127.0.0.1:8765/v1 , API key: (empty) ,
    API mode: Chat Completions , model: flameai , context length: 65536

What it does
  GET  /v1/models            -> your Cortex as one model
  POST /v1/chat/completions  -> FlameAI  POST {cortex}/messages   (stream or not)
    - tools / tool results are passed through (FlameBox accepts the OpenAI shapes)
    - the model's tool call text (tool_use.raw) is turned into OpenAI "tool_calls"
    - FlameAI remembers the conversation: when the agent re-sends the whole history, only the new
      messages are sent; when the history changed, the Cortex context is rebuilt (cortex_reset)

Settings: two constants below, or the environment variables FLAMEAI_API_URL and FLAMEAI_SECRET_KEY.
The Cortex should have a large context (Hermes Agent needs 64K or more).
Do not share or commit this file with your real Secret Key in it.
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ── Settings — copy from the FlameAI console ─────────────────────────────────
API_URL = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/messages"   # Cortex list › API URL
SECRET_KEY = "YOUR_SECRET_KEY"                                                    # Settings › My API › Secret key
PORT = 8765
CONVERSATION_ID = "hermes-bridge"   # the bridge holds the Cortex with this id


def setting(constant, env_name):
    placeholder = "YOUR_" in constant or "api-xxxx" in constant
    return (os.environ.get(env_name, "") if placeholder else constant).strip()


CORTEX = re.sub(r"(/cortex/[^/]+).*$", r"\1", setting(API_URL, "FLAMEAI_API_URL"))   # …/cortex/{id}
KEY = setting(SECRET_KEY, "FLAMEAI_SECRET_KEY")
MODEL = "flameai"
LOCK = threading.Lock()   # one Cortex = one request at a time


# ── FlameAI calls ────────────────────────────────────────────────────────────
class FlameError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def call(method, path, body=None, timeout=1800):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(CORTEX + path, data=data, method=method, headers={
        "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        err = json.loads(e.read() or b"{}").get("error", {})
        raise FlameError(e.code, err.get("code", "error"), err.get("message", str(e)))


def status():
    try:
        with call("GET", "/status", timeout=30) as res:
            data = json.loads(res.read())
            return data.get("data", data)
    except (FlameError, OSError, ValueError):
        return {}


def flame_stream(body):
    """POST /messages with stream on; yields (event, data) pairs."""
    body["options"]["stream"] = True
    with call("POST", "/messages", body) as res:
        event = ""
        for raw in res:
            line = raw.decode("utf-8").strip()
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                text = line[5:].strip()
                if text == "[DONE]":
                    return
                yield event, json.loads(text)


# ── tool_use.raw -> (name, arguments) ────────────────────────────────────────
def parse_raw(raw):
    text = re.sub(r"</?tool_call>|<\|tool_call>|<tool_call\|>", "", raw or "").strip()
    m = re.search(r"<function=([\w.-]+)>(.*?)(?:</function>|$)", text, re.S)            # Qwen 3.5 / 3.8
    if m:
        return m.group(1), dict(re.findall(r"<parameter=([\w.-]+)>\s*(.*?)\s*</parameter>", m.group(2), re.S))
    m = re.search(r"to=functions\.([\w.-]+).*?(\{.*\})", text, re.S)                     # GPT-OSS
    if m:
        return m.group(1), json.loads(m.group(2))
    m = re.search(r"call:([\w.-]+)\s*(\{.*\})", text, re.S)                              # Gemma 4
    if m:
        body = m.group(2).replace('<|"|>', '"')
        parts = re.split(r'("(?:[^"\\]|\\.)*")', body)
        body = "".join(p if i % 2 else re.sub(r"([{,]\s*)([\w.-]+)\s*:", r'\1"\2":', p) for i, p in enumerate(parts))
        return m.group(1), json.loads(body)
    data = json.loads(text)                                                              # Qwen 3 (JSON)
    fn = data.get("function") if isinstance(data.get("function"), dict) else data
    args = fn.get("arguments", fn.get("input", {}))
    return fn["name"], json.loads(args) if isinstance(args, str) else args


def fix_types(name, args, tools):
    """Qwen XML gives every value as text — turn "3" into 3 etc. using the tool's JSON schema."""
    schema = next((t.get("function", t).get("parameters", {}) for t in tools or []
                   if t.get("function", t).get("name") == name), {})
    props = schema.get("properties", {})
    for k, v in list(args.items()):
        kind = props.get(k, {}).get("type")
        if isinstance(v, str) and kind in ("integer", "number", "boolean", "object", "array"):
            try:
                args[k] = json.loads(v)
            except ValueError:
                pass
    return args


# ── conversation memory (stateless agent <-> stateful Cortex) ────────────────
class Memory:
    sent = []          # the history the Cortex holds (OpenAI shape), incl. the last answer
    last_id = None     # FlameAI message id of the last answer
    raws = {}          # tool_call id -> original raw text (sent back as-is when rebuilding)


def plain(m):
    """A message without the fields that change between requests (for comparing histories)."""
    keep = {k: m.get(k) for k in ("role", "content", "tool_call_id") if m.get(k) not in (None, "", [])}
    if isinstance(keep.get("content"), str):   # agents often trim the answer before sending it back
        keep["content"] = keep["content"].strip()
        if not keep["content"]:
            del keep["content"]
    if m.get("tool_calls"):
        keep["tool_calls"] = [{"id": c.get("id"), "name": c["function"]["name"]} for c in m["tool_calls"]]
    return json.dumps(keep, ensure_ascii=False, sort_keys=True)


def to_flame(m, tool_names):
    """One OpenAI message -> FlameAI message."""
    role, content = m.get("role"), m.get("content")
    if isinstance(content, list):   # [{type:text,text}, …] -> text (images are not passed in this version)
        content = "".join(p.get("text", "") for p in content if p.get("type") == "text")
    if role == "assistant" and m.get("tool_calls"):
        blocks = [{"type": "text", "text": content}] if content else []
        for c in m["tool_calls"]:
            if c["id"] in Memory.raws:
                blocks.append({"type": "tool_use", "id": c["id"], "raw": Memory.raws[c["id"]]})
            else:
                args = c["function"].get("arguments") or "{}"
                blocks.append({"type": "tool_use", "id": c["id"], "name": c["function"]["name"],
                               "input": json.loads(args) if isinstance(args, str) else args})
        return {"role": "assistant", "content": blocks}
    if role == "tool":
        return {"role": "tool", "tool_call_id": m.get("tool_call_id"),
                "name": m.get("name") or tool_names.get(m.get("tool_call_id"), ""), "content": content or ""}
    return {"role": role if role in ("system", "developer", "user", "assistant") else "user", "content": content or ""}


def plan(messages):
    """Return (messages to send, reset?) — only the new part if the Cortex still holds the earlier part."""
    st = status()
    holder = st.get("conversationId")
    if holder and holder != CONVERSATION_ID:   # someone else is using this Cortex — do not take it away
        raise FlameError(409, "cortex_occupied", f"Cortex is in use by another conversation ({holder})")
    n = len(Memory.sent)
    same = (n and len(messages) > n and [plain(m) for m in messages[:n]] == Memory.sent
            and st.get("loaded") and holder == CONVERSATION_ID and st.get("last_response_id") == Memory.last_id)
    return (messages[n:], False) if same else (messages, True)


# ── /v1/chat/completions ─────────────────────────────────────────────────────
def chat(req, emit):
    """Runs one request. emit(kind, value) gets 'text' / 'reasoning' deltas; returns the final OpenAI message."""
    messages, tools = req.get("messages", []), req.get("tools") or []
    tool_names = {c["id"]: c["function"]["name"] for m in messages for c in (m.get("tool_calls") or [])}
    part, reset = plan(messages)
    options = {"cortex_reset": reset, "think": 1}
    sampling = {k: req[k] for k in ("temperature", "top_p", "seed") if req.get(k) is not None}
    if req.get("max_tokens") or req.get("max_completion_tokens"):
        sampling["max_tokens"] = req.get("max_tokens") or req.get("max_completion_tokens")
    if sampling:
        options.update(sampling, apply_sampling=True)
    body = {"conversationId": CONVERSATION_ID, "options": options, "messages": [to_flame(m, tool_names) for m in part]}
    if tools:
        body["tools"] = tools
    t0 = time.time()
    message = None
    for event, data in flame_stream(body):
        if event == "message.delta" and data.get("type") in ("text", "thinking"):
            emit("text" if data["type"] == "text" else "reasoning", data.get("delta", ""))
        elif event == "message.completed":
            message = data["message"]
        elif event in ("cortex.init_failed", "message.error"):
            err = data.get("error", data)
            raise FlameError(500, err.get("code", event), err.get("message", ""))
    if message is None:
        raise FlameError(502, "stream_incomplete", "FlameAI stream ended without an answer")

    text = "".join(b.get("text", "") for b in message["content"] if b["type"] == "text")
    reasoning = "".join(b.get("thinking", "") for b in message["content"] if b["type"] == "thinking")
    calls = []
    for b in message["content"]:
        if b["type"] != "tool_use" or b.get("partial"):
            continue
        try:
            name, args = parse_raw(b.get("raw")) if b.get("raw") else (b["name"], b.get("input", {}))
        except (ValueError, KeyError, TypeError):
            text += b.get("raw", "")   # unreadable call: show it as text instead of losing it
            continue
        Memory.raws[b["id"]] = b.get("raw")
        calls.append({"id": b["id"], "type": "function",
                      "function": {"name": name, "arguments": json.dumps(fix_types(name, args, tools), ensure_ascii=False)}})
    answer = {"role": "assistant", "content": text or None}
    if calls:
        answer["tool_calls"] = calls
    if reasoning:
        answer["reasoning_content"] = reasoning
    Memory.sent = [plain(m) for m in messages] + [plain(answer)]
    Memory.last_id = message.get("id")
    usage = message.get("usage", {})
    stop = usage.get("stop_reason", "eot")
    finish = "tool_calls" if calls else ("length" if stop in ("n_predict", "hardcap") else "stop")
    print(f"  {'reset' if reset else 'add'} {len(part)} msg -> {len(text)} chars, {len(calls)} tool call(s), "
          f"in {usage.get('input_tokens')} / out {usage.get('output_tokens')} tokens, {time.time() - t0:.1f}s")
    return answer, finish, {"prompt_tokens": usage.get("input_tokens", 0), "completion_tokens": usage.get("output_tokens", 0),
                            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def send_json(self, status_code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self.send_json(200, {"object": "list", "data": [{"id": MODEL, "object": "model", "created": 0, "owned_by": "flameai"}]})
        else:
            self.send_json(404, {"error": {"message": "not found", "type": "invalid_request_error"}})

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self.send_json(404, {"error": {"message": "not found", "type": "invalid_request_error"}})
        req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        cid, created = "chatcmpl-" + uuid.uuid4().hex[:24], int(time.time())
        print(f"{time.strftime('%H:%M:%S')} {len(req.get('messages', []))} messages, {len(req.get('tools') or [])} tools"
              f"{', stream' if req.get('stream') else ''}")
        with LOCK:
            if not req.get("stream"):
                try:
                    answer, finish, usage = chat(req, lambda *_: None)
                except FlameError as e:
                    print(f"  error {e.code}: {e.message}")
                    return self.send_json(e.status, {"error": {"message": e.message, "type": "api_error", "code": e.code}})
                return self.send_json(200, {"id": cid, "object": "chat.completion", "created": created, "model": MODEL,
                                            "choices": [{"index": 0, "message": answer, "finish_reason": finish}], "usage": usage})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

            def chunk(delta, finish=None, usage=None):
                obj = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": MODEL,
                       "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                if usage:
                    obj["usage"] = usage
                self.wfile.write(f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()

            chunk({"role": "assistant", "content": ""})
            try:
                answer, finish, usage = chat(req, lambda kind, s: chunk({"content": s} if kind == "text" else {"reasoning_content": s}))
                for i, c in enumerate(answer.get("tool_calls", [])):
                    chunk({"tool_calls": [{"index": i, **c}]})
                chunk({}, finish, usage)
            except FlameError as e:
                print(f"  error {e.code}: {e.message}")
                self.wfile.write(f"data: {json.dumps({'error': {'message': e.message, 'code': e.code}})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()


def main():
    if not CORTEX or not KEY:
        raise SystemExit("API_URL, SECRET_KEY 상수나 환경변수 FLAMEAI_API_URL, FLAMEAI_SECRET_KEY 를 설정하세요")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"FlameAI Bridge: http://127.0.0.1:{PORT}/v1  (model: {MODEL})  — Ctrl+C 로 종료")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if status().get("conversationId") == CONVERSATION_ID:   # only if the Cortex is still ours
            try:   # empty the Cortex context and let others use it
                call("POST", "/reset", {}, timeout=30).close()
                call("POST", "/switch-conversation", {"conversationId": ""}, timeout=30).close()
                print("Cortex 를 비우고 놓아 주었습니다.")
            except (FlameError, OSError):
                pass


if __name__ == "__main__":
    main()
