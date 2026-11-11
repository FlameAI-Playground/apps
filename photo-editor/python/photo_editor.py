#!/usr/bin/env python3
"""FlameAI Photo Editor — edit photos with an image Cortex such as Qwen Image 2.1.

  python photo_editor.py cabin.png "Make it a snowy winter night. Keep the same cabin and lake."
  python photo_editor.py cat.png cabin.png "Put the cat from the first image on the porch of the cabin in the second image."
  options: -o out.png, --size 1024x768, --seed 42, --negative "blurry"

Image models need a lot of GPU memory (VRAM). Run it on a FlameBox with enough VRAM,
and do not keep a large chat model loaded on the same machine at the same time. Editing takes several minutes.

Put your own values in the two constants below, or set FLAMEAI_API_URL / FLAMEAI_SECRET_KEY.
Python 3.9+, standard library only. The main version of this example is ../java/PhotoEditor.java.
"""
import argparse
import json
import os
import re
import socket
import struct
import sys
import time
import urllib.error
import urllib.request

# ── Settings — copy from the FlameAI console ─────────────────────────────
API_URL = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/imageGenerate"  # Cortex list › API URL
SECRET_KEY = "YOUR_SECRET_KEY"                                                         # Settings › My API › Secret key
MAX_PHOTOS = 4

ERRORS = {
    "bearer_invalid": "API URL 또는 Secret Key 가 틀렸습니다. Cortex 목록·설정 화면에서 다시 복사하세요.",
    "cortexbox_offline": "FlameBox 가 꺼져 있습니다. PC/서버에서 FlameBox 를 켜 주세요.",
    "cortex_not_found": "API URL 의 Cortex 가 없거나 삭제되었습니다.",
    "unsupported_cortex_type": "이미지 생성 Cortex 가 아닙니다. Qwen Image 같은 이미지 Cortex 의 API URL 을 넣으세요.",
    "bad_request": "요청이 맞지 않습니다 — 이 Cortex 가 참조 사진을 받는지, 사진 형식(PNG/JPEG/WebP)·장수·크기(32 의 배수)를 확인하세요.",
    "file_not_found": "올린 사진을 찾지 못했습니다. 다시 실행해 주세요.",
    "cortex_inferring": "이 Cortex 가 이미 다른 이미지를 만드는 중입니다. 잠시 뒤 다시 시도하세요.",
    "cortex_init_fail": "모델을 올리지 못했습니다. FlameBox PC 의 VRAM 이 충분한지, 다른 큰 모델이 올라가 있지 않은지 확인하세요.",
    "internal_error": "편집에 실패했습니다. VRAM 부족일 수 있습니다 — 같은 PC 에 올라간 다른 모델(Cortex)을 내리고 다시 시도하세요.",
}


def setting(constant, env_name):
    """상수가 자리 표시 값이면 환경변수(FLAMEAI_API_URL / FLAMEAI_SECRET_KEY)에서 읽는다."""
    if "YOUR_" in constant or "api-xxxx" in constant:
        return os.environ.get(env_name, "").strip()
    return constant.strip()


BASE = re.sub(r"(/cortex/[^/]+).*$", r"\1", re.sub(r"^POST\s+", "", setting(API_URL, "FLAMEAI_API_URL")))
KEY = setting(SECRET_KEY, "FLAMEAI_SECRET_KEY")


def request(path, method="GET", data=None, ctype=None):
    headers = {"Authorization": f"Bearer {KEY}", "X-API-Version": "1"}
    if ctype:
        headers["Content-Type"] = ctype
    return urllib.request.Request(BASE + path, data=data, method=method, headers=headers)


def explain(err):
    code = err.get("code")
    return ERRORS.get(code, code or "알 수 없는 오류") + f"  ({code}: {err.get('message')})"


def image_size(path):
    """PNG·JPEG 의 가로·세로를 표준 라이브러리만으로 읽는다(못 읽으면 None)."""
    with open(path, "rb") as f:
        head = f.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
        if head[:2] == b"\xff\xd8":
            f.seek(2)
            while True:
                marker = f.read(2)
                if len(marker) < 2 or marker[0] != 0xFF:
                    return None
                length = struct.unpack(">H", f.read(2))[0]
                if marker[1] in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">xHH", f.read(5))
                    return w, h
                f.seek(length - 2, 1)
    return None


def size_for(path):
    """첫 사진의 비율을 따르고, 긴 쪽 1024, 32 의 배수 (Qwen Image 2.1 규칙)."""
    wh = image_size(path)
    if not wh:
        return 1024, 1024
    w, h = wh
    if w >= h:
        return 1024, round(1024 * h / w / 32) * 32
    return round(1024 * w / h / 32) * 32, 1024


def upload(path):
    ext = path.lower().rsplit(".", 1)[-1]
    ctype = {"png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        data = f.read()
    try:
        with urllib.request.urlopen(request("/files", "POST", data, ctype), timeout=120) as r:
            return json.load(r)["file"]
    except urllib.error.HTTPError as e:
        raise RuntimeError("사진을 올리지 못했습니다: " + explain(json.loads(e.read() or b"{}").get("error", {})))


def edit(prompt, negative, refs, size, seed):
    body = {"prompt": prompt, "ref_images": refs, "width": size[0], "height": size[1], "seed": seed, "stream": True}
    if negative:
        body["negative_prompt"] = negative
    try:
        res = urllib.request.urlopen(request("/imageGenerate", "POST", json.dumps(body).encode("utf-8"), "application/json"),
                                     timeout=1200)  # 참조 사진이 있으면 수 분
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
                    print(f"\r편집 중 [{'#' * done}{'-' * (20 - done)}] {step}/{steps}", end="", flush=True)
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
    ap = argparse.ArgumentParser(description="FlameAI photo editor")
    ap.add_argument("items", nargs="+", help="사진 파일(최대 4장) 다음에 편집 지시")
    ap.add_argument("--size")
    ap.add_argument("--seed", type=int, default=-1)
    ap.add_argument("--negative")
    ap.add_argument("-o", "--output")
    a = ap.parse_args()
    photos = []
    for item in a.items:  # 앞쪽의 파일들은 사진, 나머지는 편집 지시
        if not os.path.isfile(item):
            break
        photos.append(item)
    prompt = " ".join(a.items[len(photos):])
    if not photos or not prompt:
        sys.exit('사용법: python photo_editor.py 사진.png [사진2.png …] "편집 지시"')
    if len(photos) > MAX_PHOTOS:
        sys.exit(f"사진은 최대 {MAX_PHOTOS}장입니다.")
    size = tuple(int(v) for v in a.size.lower().split("x")) if a.size else size_for(photos[0])

    server_files = []  # 실패해도 마지막에 정리
    t0 = time.time()
    try:
        for p in photos:
            f = upload(p)
            server_files.append(f)
            print(f"올림: {os.path.basename(p)} → {f}")
        print(f"편집: {prompt}   ({size[0]}x{size[1]})")
        result = edit(prompt, a.negative, list(server_files), size, a.seed)
        file = result["files"][0]
        server_files.append(file)
        out = a.output or "edited-" + file.rsplit("/", 1)[-1]
        with urllib.request.urlopen(request("/" + file), timeout=120) as r, open(out, "wb") as fh:
            fh.write(r.read())
        print(f"저장: {os.path.abspath(out)}   (seed {result.get('seed')}, {time.time() - t0:.0f}초)")
    except (urllib.error.URLError, socket.timeout) as e:
        sys.exit(f"[오류] 연결 실패 또는 시간 초과 — 편집은 수 분 걸릴 수 있습니다: {e}")
    except RuntimeError as e:
        sys.exit(f"[오류] {e}")
    finally:
        for f in server_files:  # 올린 사진과 결과는 FlameBox 에 남으므로 지운다
            try:
                urllib.request.urlopen(request("/" + f, "DELETE"), timeout=30).close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
