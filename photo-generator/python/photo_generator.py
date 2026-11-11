#!/usr/bin/env python3
"""FlameAI Photo Generator — text-to-image console app with an image Cortex such as Qwen Image.

  python photo_generator.py "A red vintage bicycle leaning against a blue door, photorealistic"
  python photo_generator.py --size 1024x768 --seed 42 -o bike.png "a red bicycle"

Image models need a lot of GPU memory (VRAM). Run it on a FlameBox with enough VRAM,
and do not keep a large chat model loaded on the same machine at the same time.

Put your own values in the two constants below, or set FLAMEAI_API_URL / FLAMEAI_SECRET_KEY.
Python 3.9+, standard library only. The main version of this example is ../java/PhotoGenerator.java.
"""
import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request

# ── Settings — copy from the FlameAI console ─────────────────────────────
API_URL = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/imageGenerate"  # Cortex list › API URL
SECRET_KEY = "YOUR_SECRET_KEY"                                                         # Settings › My API › Secret key

ERRORS = {
    "bearer_invalid": "API URL 또는 Secret Key 가 틀렸습니다. Cortex 목록·설정 화면에서 다시 복사하세요.",
    "cortexbox_offline": "FlameBox 가 꺼져 있습니다. PC/서버에서 FlameBox 를 켜 주세요.",
    "cortex_not_found": "API URL 의 Cortex 가 없거나 삭제되었습니다.",
    "unsupported_cortex_type": "이미지 생성 Cortex 가 아닙니다. Qwen Image·FLUX 같은 이미지 Cortex 의 API URL 을 넣으세요.",
    "cortex_inferring": "이 Cortex 가 이미 다른 이미지를 만드는 중입니다. 잠시 뒤 다시 시도하세요.",
    "cortex_init_fail": "모델을 올리지 못했습니다. FlameBox PC 의 VRAM 이 충분한지, 다른 큰 모델이 올라가 있지 않은지 확인하세요.",
    "internal_error": "생성에 실패했습니다. VRAM 부족일 수 있습니다 — 같은 PC 에 올라간 다른 모델(Cortex)을 내리고 다시 시도하세요.",
}


def setting(constant, env_name):
    """상수가 자리 표시 값이면 환경변수(FLAMEAI_API_URL / FLAMEAI_SECRET_KEY)에서 읽는다."""
    if "YOUR_" in constant or "api-xxxx" in constant:
        return os.environ.get(env_name, "").strip()
    return constant.strip()


BASE = re.sub(r"(/cortex/[^/]+).*$", r"\1", re.sub(r"^POST\s+", "", setting(API_URL, "FLAMEAI_API_URL")))
KEY = setting(SECRET_KEY, "FLAMEAI_SECRET_KEY")


def request(path, method="GET", body=None):
    headers = {"Authorization": f"Bearer {KEY}", "X-API-Version": "1"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode("utf-8"),
                                  method=method, headers=headers)


def explain(err):
    code = err.get("code")
    return ERRORS.get(code, code or "알 수 없는 오류") + f"  ({code}: {err.get('message')})"


def generate(prompt, negative, width, height, seed):
    body = {"prompt": prompt, "width": width, "height": height, "seed": seed, "stream": True}
    if negative:
        body["negative_prompt"] = negative
    try:
        res = urllib.request.urlopen(request("/imageGenerate", "POST", body), timeout=900)  # 모델 로드 + 생성은 수 분
    except urllib.error.HTTPError as e:
        raise RuntimeError(explain(json.loads(e.read() or b"{}").get("error", {})))
    event, result = "", None
    with res:
        for raw in res:
            line = raw.decode("utf-8").rstrip("\r\n")
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:])
                if event == "cortex.init_start":
                    print("모델을 메모리에 올리는 중... (처음 한 번은 오래 걸릴 수 있습니다)")
                elif event == "generation.queued":
                    print("다른 생성이 끝나기를 기다리는 중...")
                elif event == "generation.progress":
                    step, steps = data.get("step", 0), data.get("steps", 0) or 1
                    done = step * 20 // steps
                    print(f"\r생성 중 [{'#' * done}{'-' * (20 - done)}] {step}/{steps}", end="", flush=True)
                elif event == "generation.result":
                    result = data
                elif event in ("generation.error", "cortex.init_failed"):
                    raise RuntimeError(explain(data.get("error", data)))
    print()
    if not result or not result.get("files"):
        raise RuntimeError("결과가 없습니다")
    return result


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if not BASE or not KEY or "api-xxxx" in BASE or "YOUR_" in BASE:
        sys.exit("파일 위쪽의 API_URL, SECRET_KEY 를 내 값으로 바꾸거나 환경변수 FLAMEAI_API_URL, FLAMEAI_SECRET_KEY 를 설정하세요")
    ap = argparse.ArgumentParser(description="FlameAI photo generator")
    ap.add_argument("prompt", nargs="*")
    ap.add_argument("--size", default="1024x1024", help="WxH, 32 의 배수 (Qwen Image)")
    ap.add_argument("--seed", type=int, default=-1)
    ap.add_argument("--negative")
    ap.add_argument("-o", "--output")
    a = ap.parse_args()
    prompt = " ".join(a.prompt) or input("무엇을 그릴까요? > ").strip()
    if not prompt:
        return
    width, height = (int(v) for v in a.size.lower().split("x"))
    print(f"프롬프트: {prompt}   ({width}x{height})")
    t0 = time.time()
    try:
        result = generate(prompt, a.negative, width, height, a.seed)
        file = result["files"][0]
        out = a.output or file.rsplit("/", 1)[-1]
        with urllib.request.urlopen(request("/" + file), timeout=120) as r, open(out, "wb") as f:
            f.write(r.read())
        try:  # 내려받았으니 Cortex 파일 저장소에서는 지운다
            urllib.request.urlopen(request("/" + file, "DELETE"), timeout=30).close()
        except Exception:
            pass
        print(f"저장: {os.path.abspath(out)}   (seed {result.get('seed')}, {time.time() - t0:.0f}초)")
    except (urllib.error.URLError, socket.timeout) as e:
        sys.exit(f"[오류] 연결 실패 또는 시간 초과 — 모델 로드와 생성은 수 분 걸릴 수 있습니다: {e}")
    except RuntimeError as e:
        sys.exit(f"[오류] {e}")


if __name__ == "__main__":
    main()
