# flux3-python — API URL 하나로 이미지 만들기 (Python · FLUX 3 Image Klein)

이미지 생성 Cortex 의 **API URL 하나**와 Secret Key 만 있으면, 내 PC 의 FlameBox 에서 돌아가는 FLUX 3 로 그림을 만들어 PNG 로 저장합니다.
Python 파일 하나(`python/flux3_image.py`), 표준 라이브러리만 씁니다.

Make an image from one API URL: a single Python file (standard library only) that calls an image Cortex (FLUX 3 Image Klein) on your own FlameBox.
Blog post: https://flameai.im/blog/flux3-python

```
https://api-3.flameai.im/Nx7bQ2mZ/cortex/7f3c9a12-4e6b-4d8f-9a21-6b5e8c1f2d3a/imageGenerate     ← 이 주소 하나 (예시 값)
```

- 이 주소로 `POST` 하면 그림이 만들어지고,
- 주소에서 `/imageGenerate` 를 뺀 `…/cortex/{Cortex ID}` 뒤에 결과 파일 이름을 붙이면 그 파일을 받고 지울 수 있습니다.

```
$ python flux3_image.py -o cabin.png "A small wooden cabin by a calm lake at sunrise, mist over the water, pine forest, warm golden light, photorealistic, wide shot"
모델을 올리는 중... (처음 한 번은 오래 걸릴 수 있습니다)
그리는 중 20/20
저장: cabin.png  (1024x1024, seed 1381978895, 50초)
```

![cabin](images/cabin.jpg)

(실제 실행 결과. 처음 한 번은 모델을 올리는 시간이 더해집니다 — 시험 장비에서 첫 장 50초(1024×1024), 모델이 올라간 뒤 1024×576 은 13초.)

## 1. 준비

1. **FlameBox 설치·계정 연결** — [Windows 편](https://flameai.im/blog/flamebox-install-windows) · [Linux 편](https://flameai.im/blog/flamebox-install-linux)
2. **FLUX 3 Cortex 만들기** — 콘솔 Cortex 만들기의 **이미지** 탭에서 FLUX 3 Image Klein 으로 만듭니다(제작사 기준 VRAM 8GB GPU 에서도 실행 가능).
3. **Python 3.9 이상** — 설치할 라이브러리는 없습니다.

## 2. 설정 — 값 2개

- **API URL** — 마이페이지 › **Cortex** 목록에서 FLUX 3 Cortex 카드의 주소 옆 **복사** (`…/imageGenerate` 로 끝남)
- **Secret Key** — 마이페이지 › **설정** › My API

환경변수로 넣으면 파일에 키가 남지 않습니다(상수가 자리 표시 값이면 환경변수를 읽음).

**Windows (PowerShell)**
```powershell
$env:FLAMEAI_API_URL    = "https://api-3.flameai.im/Nx7bQ2mZ/cortex/7f3c9a12-4e6b-4d8f-9a21-6b5e8c1f2d3a/imageGenerate"
$env:FLAMEAI_SECRET_KEY = "0123456789ABCDEFGH"
```

**macOS · Linux**
```bash
export FLAMEAI_API_URL="https://api-3.flameai.im/Nx7bQ2mZ/cortex/7f3c9a12-4e6b-4d8f-9a21-6b5e8c1f2d3a/imageGenerate"
export FLAMEAI_SECRET_KEY="0123456789ABCDEFGH"
```

또는 `flux3_image.py` 위쪽 상수 2개(`API_URL`, `SECRET_KEY`)를 바꿉니다.

> **실제 Secret Key 를 넣은 파일은 공유하거나 저장소에 올리지 마세요.**

## 3. 실행

| 하고 싶은 것 | 명령 |
|---|---|
| 그리기 | `python flux3_image.py "그릴 내용 (영어로 자세히)"` |
| 크기 (32 의 배수) | `python flux3_image.py --size 1024x576 "…"` |
| 같은 그림 다시 | `python flux3_image.py --seed 42 "…"` |
| 저장 이름 | `python flux3_image.py -o bike.png "…"` |

## 4. 코드 구성

| 부분 | 하는 일 |
|---|---|
| `API_URL` → `CORTEX` | 주소에서 `/imageGenerate` 를 뗀 `…/cortex/{id}` — 결과 파일도 이 주소 아래에 있음 |
| `call()` | `Authorization: Bearer {Secret Key}` 를 붙여 호출, FlameAI 오류는 읽기 쉬운 문장으로 |
| `generate()` | `imageGenerate` 를 `stream: true` 로 불러 진행률(`generation.progress`)을 보여 주고 결과(`generation.result`)를 받음 |
| `save()` | `files/gen-….png` 를 내려받고, FlameBox 에 남은 파일을 지움 |

## 5. 알아 둘 점

- **영어 프롬프트** — FLUX 3 는 영어로 구도·조명·색감·스타일까지 자세히 쓸 때 결과가 좋습니다. 짧은 한국어 요청을 자세한 영어로 바꿔 주는
  FLUX 3 Prompt Upsampler 도 함께 제공됩니다([공지](https://flameai.im/notices/notice-image-flux3-klein)).
- **크기** — 가로·세로 32 의 배수. 클수록 오래 걸리고 메모리를 많이 씁니다.
- **메모리** — 같은 PC 에 큰 대화 모델이 함께 올라가 있으면 실패할 수 있습니다(`internal_error`). 쓰지 않는 Cortex 를 내리고 다시 하세요.
- **라이선스** — FLUX Kommunity License: 연 매출 500만 달러 미만의 개인·기업은 상업적 이용 무료(자세한 조건은 원문 확인).

## 6. 오류

| 메시지 | 할 일 |
|---|---|
| `bearer_invalid` | API URL·Secret Key 를 다시 복사 |
| `cortexbox_offline` | FlameBox PC 를 켜고 FlameBox 실행 |
| `cortex_init_fail` / `internal_error` | VRAM 부족일 수 있음 — 같은 PC 의 다른 Cortex 를 내리고 다시 |
| `bad_request` | 크기가 32 의 배수인지 확인 |
