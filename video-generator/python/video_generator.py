"""
FlameAI Video Generator — text-to-video with a video Cortex such as LTX 2.5 (Python 3.9+, standard library only).
Same program as java/VideoGenerator.java.

    python video_generator.py "A paper boat floating down a small stream in a sunny forest, cinematic"
    python video_generator.py --size 640x384 --frames 121 --fps 24 --seed 7 -o boat.webm "a paper boat ..."

The result is a webm file (video + sound). LTX rules: width/height multiples of 32, frames = 8n+1 (25, 49, 121 …).
Put your own values in the two constants below, or set FLAMEAI_API_URL / FLAMEAI_SECRET_KEY.
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
API_URL = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/videoGenerate"  # Cortex list › API URL
SECRET_KEY = "YOUR_SECRET_KEY"                                                          # Settings › My API › Secret key


def setting(constant, env_name):
    placeholder = "YOUR_" in constant or "api-xxxx" in constant
    return (os.environ.get(env_name, "") if placeholder else constant).strip()


URL = re.sub(r"^POST\s+", "", setting(API_URL, "FLAMEAI_API_URL"))
CORTEX = re.sub(r"(/cortex/[^/]+).*$", r"\1", URL)    # …/cortex/{id} — result files live here
KEY = setting(SECRET_KEY, "FLAMEAI_SECRET_KEY")


def call(method, url, body=None):
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {KEY}", "X-API-Version": "1", "Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=1800)   # a 5-second video can take many minutes
    except urllib.error.HTTPError as e:
        err = json.loads(e.read() or b"{}").get("error", {})
        raise SystemExit(f"[오류] {err.get('code', e.code)}: {err.get('message', '')}")


def generate(prompt, width, height, frames, fps, seed):
    body = json.dumps({"prompt": prompt, "width": width, "height": height, "frames": frames,
                       "fps": fps, "seed": seed, "stream": True}).encode()
    event = ""
    with call("POST", URL, body) as res:
        for raw in res:
            line = raw.decode("utf-8").strip()
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:])
                if event == "cortex.init_start":
                    print("모델을 메모리에 올리는 중...")
                elif event == "generation.progress":
                    done = data["step"] == data["steps"]
                    print(f"\r만드는 중 {data['step']}/{data['steps']}" + ("  영상으로 변환하는 중..." if done else ""), end="", flush=True)
                elif event == "generation.result":
                    print()
                    return data
                elif event in ("cortex.init_failed", "generation.error"):
                    err = data.get("error", data)
                    raise SystemExit(f"\n[오류] {err.get('code')}: {err.get('message')}")
    raise SystemExit("[오류] 결과 없이 끝났습니다.")


def main():
    ap = argparse.ArgumentParser(description="LTX 동영상 생성 (영어 프롬프트 권장)")
    ap.add_argument("prompt")
    ap.add_argument("-o", "--output")
    ap.add_argument("--size", default="640x384", help="가로x세로, 32의 배수")
    ap.add_argument("--frames", type=int, default=121, help="8n+1 (25≈1초, 49≈2초, 121≈5초 @24fps)")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--seed", type=int, default=-1)
    a = ap.parse_args()
    if not URL or not KEY:
        raise SystemExit("파일 위쪽의 API_URL, SECRET_KEY 를 내 값으로 바꾸거나 환경변수 FLAMEAI_API_URL, FLAMEAI_SECRET_KEY 를 설정하세요")
    width, height = (int(v) for v in a.size.lower().split("x"))
    print(f"{width}x{height}, {a.frames}프레임, {a.fps}fps (약 {a.frames / a.fps:.1f}초 영상)")
    t0 = time.time()
    result = generate(a.prompt, width, height, a.frames, a.fps, a.seed)
    file = result["files"][0]
    out = a.output or file.split("/")[-1]
    with call("GET", f"{CORTEX}/{file}") as res, open(out, "wb") as f:
        f.write(res.read())
    call("DELETE", f"{CORTEX}/{file}").close()
    print(f"저장: {out}   (seed {result['seed']}, 소리 {'있음' if result.get('has_audio') else '없음'}, {time.time() - t0:.0f}초)")


if __name__ == "__main__":
    main()
