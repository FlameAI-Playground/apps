#!/usr/bin/env python3
"""FlameAI Chatbot — an LLM console chatbot that remembers the conversation.

  python chatbot.py
  > 안녕! 내 이름은 민수야.
  > 내 이름이 뭐라고 했지?      <- only the new message is sent; the Cortex remembers the rest
  > /reset                      <- start a new conversation

Put your own values in the two constants below (FlameAI console > Cortex list / Settings).
Do not share or commit this file with your real Secret Key in it.
Python 3.9+, standard library only. The main version of this example is ../java/Chatbot.java.
"""
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.request

# ── Settings — copy from the FlameAI console ─────────────────────────────
API_URL = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/messages"  # Cortex list › API URL
SECRET_KEY = "YOUR_SECRET_KEY"                                                    # Settings › My API › Secret key

# ── Chatbot personality (change freely) ──────────────────────────────────
SYSTEM_PROMPT = "You are a friendly assistant. Answer briefly in the user's language, in plain text without Markdown."
CONVERSATION_ID = "simple-chatbot"

ERRORS = {
    "bearer_not_found": "Secret Key 가 비어 있습니다. SECRET_KEY 를 확인하세요.",
    "bearer_invalid": "API URL 또는 Secret Key 가 틀렸습니다. Cortex 목록·설정 화면에서 다시 복사하세요.",
    "cortexbox_offline": "FlameBox 가 꺼져 있습니다. PC/서버에서 FlameBox 를 켜 주세요.",
    "cortex_not_found": "API URL 의 Cortex 가 없거나 삭제되었습니다. Cortex 목록에서 다시 복사하세요.",
    "cortex_occupied": "다른 대화가 이 Cortex 를 쓰고 있습니다. /reset 으로 새 대화를 시작하면 이 대화로 가져옵니다.",
}


def setting(constant, env_name):
    """상수가 자리 표시 값이면 환경변수(FLAMEAI_API_URL / FLAMEAI_SECRET_KEY)에서 읽는다."""
    if "YOUR_" in constant or "api-xxxx" in constant:
        return os.environ.get(env_name, "").strip()
    return constant.strip()


URL = re.sub(r"^POST\s+", "", setting(API_URL, "FLAMEAI_API_URL"))  # "POST …" 째로 복사해도 된다
KEY = setting(SECRET_KEY, "FLAMEAI_SECRET_KEY")
new_conversation = True


def send(user_message):
    # 새 대화는 규칙(system)과 cortex_reset 으로 시작하고, 그다음부터는 새 메시지만 보낸다
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] if new_conversation else []
    messages.append({"role": "user", "content": user_message})
    body = {"conversationId": CONVERSATION_ID,
            "options": {"stream": False, "think": False, "cortex_reset": new_conversation},
            "messages": messages}
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "X-API-Version": "1"})
    try:
        with urllib.request.urlopen(req, timeout=300) as res:  # 첫 요청은 모델을 올리느라 오래 걸릴 수 있다
            return json.load(res)
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def chat(user_message):
    global new_conversation
    try:
        data = send(user_message)
    except (urllib.error.URLError, socket.timeout) as e:
        return f"[오류] 연결 실패 또는 시간 초과 — 모델을 올리는 중일 수 있습니다: {e}"
    if "error" in data:
        code = data["error"].get("code")
        return "[오류] " + ERRORS.get(code, f"{code}: {data['error'].get('message')}")
    new_conversation = False  # 이제부터는 새 메시지만 — Cortex 가 앞 대화를 기억한다
    blocks = data.get("message", {}).get("content", [])
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


def main():
    global new_conversation
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if not URL or not KEY:
        sys.exit("파일 위쪽의 API_URL, SECRET_KEY 를 내 값으로 바꾸거나 환경변수 FLAMEAI_API_URL, FLAMEAI_SECRET_KEY 를 설정하세요 / "
                 "set the constants at the top or the environment variables FLAMEAI_API_URL, FLAMEAI_SECRET_KEY")
    print("FlameAI chatbot  (/reset: 새 대화, /exit 또는 빈 줄: 종료)")
    print("첫 응답은 모델을 메모리에 올리느라 조금 걸릴 수 있습니다.")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line or line == "/exit":
            break
        if line == "/reset":
            new_conversation = True
            print("(새 대화를 시작합니다)")
            continue
        print(chat(line))


if __name__ == "__main__":
    main()
