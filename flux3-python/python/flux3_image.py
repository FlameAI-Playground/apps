"""
FlameAI Flux3 Image — make an image from one API URL (Python 3.9+, standard library only).

    python flux3_image.py "A red vintage bicycle leaning against a blue door, morning light, photorealistic"
    python flux3_image.py --size 1024x768 --seed 42 -o bike.png "a red bicycle ..."

All you need is the API URL of an image Cortex (FLUX 3 Image Klein) and your Secret Key.
Put them in the two constants below, or set the environment variables FLAMEAI_API_URL / FLAMEAI_SECRET_KEY.
Do not share or commit this file with your real Secret Key in it.
"""
import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request

# ── Settings — copy from the FlameAI console ─────────────────────────────────
API_URL = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/imageGenerate"  # Cortex list › API URL
SECRET_KEY = "YOUR_SECRET_KEY"                                                          # Settings › My API › Secret key


def setting(constant, env_name):
    placeholder = "YOUR_" in constant or "api-xxxx" in constant
    return (os.environ.get(env_name, "") if placeholder else constant).strip()


URL = re.sub(r"^POST\s+", "", setting(API_URL, "FLAMEAI_API_URL"))   # "POST https://…" as copied is fine
CORTEX = re.sub(r"(/cortex/[^/]+).*$", r"\1", URL)                    # https://…/cortex/{id} — files live here too
KEY = setting(SECRET_KEY, "FLAMEAI_SECRET_KEY")


def call(method, url, body=None):
    """One HTTP call with the Secret Key. Raises SystemExit with a readable message on a FlameAI error."""
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {KEY}", "X-API-Version": "1", "Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=900)   # loading the model + drawing can take minutes
    except urllib.error.HTTPError as e:
        err = json.loads(e.read() or b"{}").get("error", {})
        raise SystemExit(f"[오류] {err.get('code', e.code)}: {err.get('message', '')}")


# ── 1. Ask the Cortex to draw (stream: progress events, then the result) ─────
def generate(prompt, width, height, seed):
    body = json.dumps({"prompt": prompt, "width": width, "height": height, "seed": seed, "stream": True}).encode()
    event = ""
    with call("POST", URL, body) as res:
        for raw in res:                                   # Server-Sent Events, one line at a time
            line = raw.decode("utf-8").strip()
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:])
                if event == "cortex.init_start":
                    print("모델을 올리는 중... (처음 한 번은 오래 걸릴 수 있습니다)")
                elif event == "generation.progress":
                    print(f"\r그리는 중 {data['step']}/{data['steps']}", end="", flush=True)
                elif event == "generation.result":
                    print()
                    return data                           # {"files": ["files/gen-….png"], "seed": …, …}
                elif event in ("cortex.init_failed", "generation.error"):
                    err = data.get("error", data)
                    raise SystemExit(f"\n[오류] {err.get('code')}: {err.get('message')}")
    raise SystemExit("[오류] 결과 없이 끝났습니다.")


# ── 2. Download the PNG, then delete it from the FlameBox ────────────────────
def save(file, out):
    with call("GET", f"{CORTEX}/{file}") as res:
        with open(out, "wb") as f:
            f.write(res.read())
    call("DELETE", f"{CORTEX}/{file}").close()            # the result stays on my PC only


# ── 3. Command line ──────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="FLUX 3 이미지 생성 (영어 프롬프트 권장)")
    ap.add_argument("prompt", help="그릴 내용 — 영어로 자세히")
    ap.add_argument("-o", "--output", help="저장할 파일 이름 (기본: gen-….png)")
    ap.add_argument("--size", default="1024x1024", help="가로x세로, 32의 배수 (기본 1024x1024)")
    ap.add_argument("--seed", type=int, default=-1, help="같은 그림을 다시 얻을 때 (기본 -1 = 무작위)")
    a = ap.parse_args()
    if not URL or not KEY:
        raise SystemExit("파일 위쪽의 API_URL, SECRET_KEY 를 내 값으로 바꾸거나 환경변수 FLAMEAI_API_URL, FLAMEAI_SECRET_KEY 를 설정하세요")
    width, height = (int(v) for v in a.size.lower().split("x"))

    t0 = time.time()
    result = generate(a.prompt, width, height, a.seed)
    file = result["files"][0]
    out = a.output or file.split("/")[-1]
    save(file, out)
    print(f"저장: {out}  ({result['width']}x{result['height']}, seed {result['seed']}, {time.time() - t0:.0f}초)")


if __name__ == "__main__":
    main()
