# photo-generator — Java로 만드는 AI 이미지 생성기 (Qwen Image)

> **⚠ 반드시 VRAM(그래픽 메모리)이 충분한 FlameBox 에서 실행하세요.**
> Qwen Image 2.1 은 모델 파일만 약 14GB 입니다(이미지 모델 7.6GB + 문장을 이해하는 Qwen3-VL 8B 4.8GB + 기타).
> 같은 PC 에 큰 대화 모델(예: 12B 이상)이 올라가 있으면 생성이 `internal_error` 로 실패할 수 있습니다 —
> 그때는 콘솔에서 다른 Cortex 를 내리고 다시 실행하세요.

문장을 넣으면 내 PC의 FlameBox 에서 돌아가는 이미지 모델(Cortex)이 그림을 그려 PNG 로 저장하는 콘솔 프로그램입니다.
**Java 21 이상**, 라이브러리 없이 파일 하나(`PhotoGenerator.java`)로 동작합니다. 한국어 프롬프트도 됩니다(영어가 더 정확).

A text-to-image console app in a single Java file (Java 21+, no libraries) using an image Cortex such as Qwen Image.
Blog post: https://flameai.im/blog/photo-generator

```
$ java PhotoGenerator.java -o train.png "해질녘 눈 덮인 산 아래를 달리는 작은 빨간 기차, 사진처럼 사실적으로"
프롬프트: 해질녘 눈 덮인 산 아래를 달리는 작은 빨간 기차, 사진처럼 사실적으로   (1024x1024)
생성 중 [####################] 26/26
저장: C:\work\train.png   (seed 598236550, 102초)
```

(Qwen Image 2.1 Cortex 로 실제 실행. 시간은 FlameBox PC 의 GPU 에 따라 다릅니다 — 시험 장비에서 1024×1024 약 1분 40초, 1024×768 약 70초, 768×768 약 50초. 처음 한 번은 모델 로드 시간이 더해집니다.)

---

## 1. 준비

1. **FlameBox 설치·계정 연결** — [Windows 편](https://flameai.im/blog/flamebox-install-windows) · [Linux 편](https://flameai.im/blog/flamebox-install-linux)
2. **이미지 생성 Cortex 만들기** — 콘솔 Cortex 만들기에서 **이미지** 탭의 모델(예: Qwen Image 2.1)로 만듭니다. VRAM 이 넉넉한 FlameBox 를 고르세요.
3. **JDK 21 이상** — `java -version` 으로 확인하세요.

## 2. 받기와 설정

```bash
git clone https://github.com/FlameAI-Playground/apps
cd apps/photo-generator/java
```

`PhotoGenerator.java` 위쪽의 상수 2개를 내 값으로 바꿉니다.

```java
static final String API_URL    = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/imageGenerate"; // Cortex 목록의 API URL
static final String SECRET_KEY = "YOUR_SECRET_KEY";                                                          // 설정 › My API › Secret key
```

- **API URL** — 마이페이지 › **Cortex** 목록에서 이미지 Cortex 카드의 주소 옆 **복사**. 끝의 action(`/imageGenerate` 등)은 프로그램이 알아서 처리합니다.
- **Secret Key** — 마이페이지 › **설정** › My API.

상수 대신 **환경변수** `FLAMEAI_API_URL`, `FLAMEAI_SECRET_KEY` 로 넣어도 됩니다(상수가 자리 표시 값 그대로일 때 읽음).

> **실제 Secret Key 를 넣은 파일은 공유하거나 저장소에 올리지 마세요.**

## 3. 실행

| 하고 싶은 것 | 명령 |
|---|---|
| 그리기 | `java PhotoGenerator.java "그릴 내용"` |
| 크기 바꾸기 (32 의 배수) | `java PhotoGenerator.java --size 1024x768 "…"` |
| 같은 그림 다시 (seed 고정) | `java PhotoGenerator.java --seed 42 "…"` |
| 피하고 싶은 것 | `java PhotoGenerator.java --negative "blurry, text" "…"` |
| 저장 파일 이름 | `java PhotoGenerator.java -o cabin.png "…"` |
| 프롬프트를 물어보게 | `java PhotoGenerator.java` |

결과는 현재 폴더에 PNG 로 저장되고, 저장 뒤 Cortex 의 파일 저장소에서는 지웁니다. 실행이 끝나면 seed 와 걸린 시간을 보여 줍니다.

## 4. 코드 설명 — 생성 요청 → 진행률 이벤트 → 파일 받기

```java
// 1) 생성 요청 — stream:true 로 진행률을 이벤트로 받는다
POST {Cortex}/imageGenerate   {"prompt": "...", "width": 1024, "height": 1024, "seed": -1, "stream": true}

// 2) 이벤트를 한 줄씩 읽는다
event: cortex.init_start      → 모델을 올리는 중(처음 한 번)
event: generation.progress    → {"step": 10, "steps": 26}  진행 막대
event: generation.result      → {"files": ["files/gen-….png"], "seed": …}
event: generation.error       → {"code": "...", "message": "..."}

// 3) 결과 받기와 정리
GET    {Cortex}/files/gen-….png   → PNG 저장
DELETE {Cortex}/files/gen-….png   → 서버 쪽 결과 지우기
```

| 짚을 점 | 이유 |
|---|---|
| `stream: true` | 한 장에 1~4분 걸립니다. 진행률이 없으면 멈춘 것처럼 보입니다 |
| 크기는 32 의 배수 | Qwen Image 2.1 규칙. 크게 할수록 오래 걸리고 VRAM 을 더 씁니다 |
| `seed` | `-1` 이면 무작위. 결과의 seed 를 다시 주면 같은 그림이 나옵니다 |
| 타임아웃 넉넉히(15분) | 모델 로드 + 생성 |
| JSON | 예제를 파일 하나로 두려고 정규식으로 처리했습니다. 실제 프로젝트에서는 Jackson·Gson 을 쓰세요 |

## 5. 오류가 날 때

| 메시지 | 확인할 것 |
|---|---|
| 생성에 실패했습니다 (`internal_error`) | **VRAM 부족**일 가능성이 큽니다. 같은 FlameBox 에 올라간 다른 Cortex(특히 큰 대화 모델)를 콘솔에서 내리고 다시 |
| 모델을 올리지 못했습니다 (`cortex_init_fail`) | VRAM·디스크가 충분한지, 모델이 다 받아졌는지 |
| 이미지 생성 Cortex 가 아닙니다 (`unsupported_cortex_type`) | 대화형 Cortex 의 URL 을 넣었습니다. 이미지 Cortex 의 API URL 로 |
| 다른 이미지를 만드는 중입니다 (`cortex_inferring`) | 한 PC 에서 이미지 생성은 한 번에 하나 — 잠시 뒤 다시 |
| API URL 또는 Secret Key 가 틀렸습니다 (`bearer_invalid`) | Cortex 목록·설정 › My API 에서 다시 복사 |

## 6. Python 버전

같은 기능의 Python 소스가 [`python/photo_generator.py`](python/photo_generator.py) 에 있습니다 (Python 3.9+, 표준 라이브러리만).

---

MIT License · [FlameAI](https://flameai.im) · [API 문서](https://flameai.im/doc)
