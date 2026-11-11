#!/usr/bin/env python3
"""FlameAI English Translator — Korean <-> English console translator.

  python translate.py "안녕하세요"            # Korean  -> English
  python translate.py "Good morning"         # English -> Korean
  python translate.py --to ja "안녕하세요"    # any language: ja, zh, es, fr, de, vi ...
  python translate.py < note.txt             # translate a whole file
  python translate.py                        # interactive mode (empty line or Ctrl+C to quit)

Put your own values in the three constants below (FlameAI console > Settings / Cortex list).
Do not share or commit this file with your real Secret Key in it.
Python 3.9+, standard library only. The main version of this example is ../java/Translator.java.
"""
import argparse
import json
import re
import socket
import sys
import urllib.error
import urllib.request

# ── Settings — copy from the FlameAI console ─────────────────────────────
API_BASE = "https://api-xxxx.flameai.im/AbCd1234"  # Settings › My API › API base url
SECRET_KEY = "YOUR_SECRET_KEY"                     # Settings › My API › Secret key
CORTEX_ID = "YOUR_CORTEX_ID"                       # Cortex list ⋮ › Copy Cortex ID
CONVERSATION_ID = "english-translator"

LANGS = {"ko": "Korean", "en": "English", "ja": "Japanese", "zh": "Simplified Chinese",
         "es": "Spanish", "fr": "French", "de": "German", "vi": "Vietnamese"}
HANGUL = re.compile(r"[가-힣]")

SYSTEM_PROMPT = (
    "You are a professional translator. Translate the user's text into {lang}. "
    "Output only the translation - no explanations, no quotes, no notes. "
    "Keep line breaks, numbers, code and proper nouns as they are."
)

# FlameAI error codes -> what the user should do
ERRORS = {
    "bearer_not_found": "Secret Key 가 비어 있습니다. SECRET_KEY 를 확인하세요.",
    "bearer_invalid": "API 주소, Secret Key 또는 Cortex ID 가 틀렸습니다. 콘솔에서 다시 복사하세요.",
    "cortexbox_offline": "FlameBox 가 꺼져 있습니다. PC/서버에서 FlameBox 를 켜 주세요.",
    "cortex_not_found": "Cortex ID 가 틀렸거나 삭제된 Cortex 입니다. CORTEX_ID 를 확인하세요.",
    "cortex_occupied": "다른 대화가 이 Cortex 를 쓰고 있습니다. 잠시 뒤 다시 시도하세요.",
}


class TranslateError(Exception):
    pass


def load_config(conversation):
    if "YOUR_" in SECRET_KEY + CORTEX_ID or "api-xxxx" in API_BASE:
        sys.exit("파일 위쪽의 API_BASE, SECRET_KEY, CORTEX_ID 를 내 값으로 바꾸세요 / set the constants at the top")
    return {"base": API_BASE.rstrip("/"), "key": SECRET_KEY, "cortex": CORTEX_ID, "conversation": conversation}


def target_language(text, to):
    """--to 가 없으면 한글이 있으면 영어로, 없으면 한국어로."""
    if to:
        return LANGS.get(to.lower(), to)
    return "English" if HANGUL.search(text) else "Korean"


def translate(text, target, cfg):
    body = {
        "conversationId": cfg["conversation"],
        # stream: 한 번에 받기 / think: 생각 과정 끄기(빠름) / cortex_reset: 매번 새로 시작(앞 문장이 섞이지 않게)
        "options": {"stream": False, "think": False, "cortex_reset": True},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.format(lang=target)},
            {"role": "user", "content": text},
        ],
    }
    req = urllib.request.Request(
        f"{cfg['base']}/cortex/{cfg['cortex']}/messages",
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json",
                 "X-API-Version": "1"})
    try:
        with urllib.request.urlopen(req, timeout=300) as res:  # 첫 요청은 모델을 올리느라 오래 걸릴 수 있다
            data = json.load(res)
    except urllib.error.HTTPError as e:
        try:
            data = json.loads(e.read() or b"{}")
        except ValueError:
            raise TranslateError(f"HTTP {e.code}")
    except (urllib.error.URLError, socket.timeout) as e:
        raise TranslateError(f"연결 실패 / connection failed: {e}")

    if "error" in data:
        err = data["error"]
        raise TranslateError(ERRORS.get(err.get("code"), f"{err.get('code')}: {err.get('message')}"))
    blocks = data.get("message", {}).get("content", [])
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()


def main():
    for stream in (sys.stdout, sys.stderr):  # Windows 콘솔에서 한글이 깨지지 않게
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="FlameAI translator (Korean <-> English)")
    ap.add_argument("text", nargs="*", help="번역할 문장 / text to translate")
    ap.add_argument("--to", help="대상 언어 / target language: ko, en, ja, zh, es, fr, de, vi ...")
    ap.add_argument("--conversation", default=CONVERSATION_ID, help="conversationId (기본 english-translator)")
    args = ap.parse_args()
    cfg = load_config(args.conversation)

    if args.text or not sys.stdin.isatty():  # 인자 또는 파일(stdin) — 한 번 번역하고 끝
        text = " ".join(args.text) if args.text else sys.stdin.read()
        try:
            print(translate(text, target_language(text, args.to), cfg))
        except TranslateError as e:
            sys.exit(f"[오류] {e}")
        return

    print("FlameAI translator — 한국어 <-> English  (빈 줄 또는 Ctrl+C: 종료 / empty line to quit)")
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            break
        try:
            print(translate(text, target_language(text, args.to), cfg))
        except TranslateError as e:
            print(f"[오류] {e}")


if __name__ == "__main__":
    main()
