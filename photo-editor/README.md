# photo-editor — Java로 만드는 AI 사진 편집기 (Qwen Image 2.1)

> **⚠ 반드시 VRAM(그래픽 메모리)이 충분한 FlameBox 에서 실행하세요.**
> Qwen Image 2.1 은 모델 파일만 약 14GB 입니다(이미지 모델 7.6GB + 문장을 이해하는 Qwen3-VL 8B 4.8GB + 기타).
> 같은 PC 에 큰 대화 모델(예: 12B 이상)이 올라가 있으면 `internal_error` 로 실패할 수 있습니다 — 다른 Cortex 를 내리고 다시 실행하세요.
> 편집은 새로 그리기보다 오래 걸립니다(참조 사진 1장, 1024×768 에 약 3~4분).

사진과 편집 지시를 주면 내 PC의 FlameBox 에서 돌아가는 이미지 모델(Qwen Image 2.1)이 사진을 고쳐 PNG 로 저장하는 콘솔 프로그램입니다.
계절·시간 바꾸기, 그림 느낌 바꾸기, 두 장 합치기 같은 편집을 합니다. **Java 21 이상**, 라이브러리 없이 파일 하나(`PhotoEditor.java`).

Edit photos with an image Cortex (Qwen Image 2.1) from a single Java file (Java 21+, no libraries).
Blog post: https://flameai.im/blog/photo-editor

```
$ java PhotoEditor.java cabin.png "Make it a snowy winter night with snow falling. Keep the same wooden cabin, porch and lake. Warm light glowing in the windows."
```

| 편집 | 사진 | 지시 (영어 권장) |
|---|---|---|
| 계절·시간 바꾸기 | `cabin.png` | `Make it a snowy winter night with snow falling. Keep the same wooden cabin, porch and lake.` |
| 그림 느낌 바꾸기 | `bike.png` | `Turn this photo into a soft watercolor illustration on textured paper. Keep the same red bicycle, blue door and composition.` |
| 두 장 합치기 | `cat.png cabin.png` | `Put the orange cat from the first image on the wooden porch of the cabin in the second image. Keep the same cabin, lake and lighting from the second image.` |

(Qwen Image 2.1 Cortex 로 실제 실행한 편집입니다. 결과는 블로그 글에 비교 그림으로 있습니다.)

---

## 1. 준비

1. **FlameBox 설치·계정 연결** — [Windows 편](https://flameai.im/blog/flamebox-install-windows) · [Linux 편](https://flameai.im/blog/flamebox-install-linux)
2. **이미지 Cortex 만들기** — 콘솔 Cortex 만들기에서 **이미지** 탭의 Qwen Image 2.1 로. 참조 사진을 받는 모델이어야 합니다(Cortex 상태의 `capabilities.inputs` 에 `"role": "reference"`).
3. **JDK 21 이상** — `java -version` 으로 확인하세요.

## 2. 받기와 설정

```bash
git clone https://github.com/FlameAI-Playground/apps
cd apps/photo-editor/java
```

`PhotoEditor.java` 위쪽의 상수 2개를 내 값으로 바꿉니다(또는 환경변수 `FLAMEAI_API_URL`, `FLAMEAI_SECRET_KEY`).

```java
static final String API_URL    = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/imageGenerate"; // Cortex 목록의 API URL
static final String SECRET_KEY = "YOUR_SECRET_KEY";                                                          // 설정 › My API › Secret key
```

> **실제 Secret Key 를 넣은 파일은 공유하거나 저장소에 올리지 마세요.**

## 3. 실행

```bash
java PhotoEditor.java 사진.png [사진2.png …] "편집 지시"
```

| 옵션 | 뜻 |
|---|---|
| (기본) | 결과 크기는 첫 사진의 비율에 맞추고 긴 쪽 1024, 32 의 배수 |
| `--size 1024x768` | 크기를 직접 (32 의 배수). 작게 하면 훨씬 빠릅니다 (512×384 약 24초) |
| `--seed 42` | 같은 결과를 다시 얻을 때 |
| `--negative "blurry"` | 피하고 싶은 것 |
| `-o out.png` | 저장 파일 이름 (기본 `edited-gen-….png`) |

사진은 PNG·JPEG·WebP, 최대 4장. 올린 사진과 결과는 끝나면 Cortex 파일 저장소에서 지웁니다(실패해도).

## 4. 코드 설명

```text
1) 사진 올리기   POST {Cortex}/files  (Content-Type: image/png, 바이트 그대로)  → {"file": "files/upload-….png"}
2) 편집 요청     POST {Cortex}/imageGenerate
                 {"prompt": "...", "ref_images": ["files/upload-….png"], "width": 1024, "height": 768, "stream": true}
3) 진행률        event: generation.progress → generation.result {"files": ["files/gen-….png"], "seed": …}
4) 결과 받기     GET {Cortex}/files/gen-….png
5) 정리          DELETE {Cortex}/files/upload-….png, …/gen-….png
```

| 요령 | 이유 |
|---|---|
| `Change only …` / `Keep the same …` | 바꿀 것과 유지할 것을 함께 적으면 바뀌는 범위가 좁아집니다 |
| 여러 장은 순서로 역할 지정 | `the cat from the first image … the cabin in the second image` |
| 결과 크기를 원본 비율에 맞추기 | 비율이 다르면 그림이 늘어나거나 잘립니다 |
| 영어 지시 권장 | Qwen Image 는 한국어도 알아듣지만 세부 지시는 영어가 더 정확합니다 |
| 합치기는 "같은 대상"이 아닐 수 있음 | 시험에서 자는 새끼 고양이가 앉아 있는 비슷한 고양이로 바뀌었습니다. 생김새를 지키려면 특징을 구체적으로 적으세요 |

## 5. 걸리는 시간 (시험 장비, Qwen Image 2.1)

| 경우 | 크기 | 시간 |
|---|---|---|
| 참조 없이 생성 (photo-generator) | 1024×768 | 약 70초 |
| 참조 1장 편집 | 1024×768 | 약 3분 30초 ~ 3분 50초 |
| 참조 1장 편집 | 1024×1024 | 약 5분 20초 |
| 참조 2장 합치기 | 1024×768 | 약 6분 35초 |
| 참조 1장 편집 | 512×384 | 약 24초 |

속도는 FlameBox PC 의 GPU 에 따라 다릅니다.

## 6. 오류가 날 때

| 메시지 | 확인할 것 |
|---|---|
| 편집에 실패했습니다 (`internal_error`) | **VRAM 부족**일 가능성. 같은 FlameBox 의 다른 Cortex(특히 큰 대화 모델)를 내리고 다시 |
| 요청이 맞지 않습니다 (`bad_request`) | 참조 사진을 받는 Cortex 인지, 사진 형식·장수(4장)·크기(32 의 배수) |
| 이미지 생성 Cortex 가 아닙니다 (`unsupported_cortex_type`) | 이미지 Cortex 의 API URL 로 |
| 다른 이미지를 만드는 중입니다 (`cortex_inferring`) | 한 PC 에서 이미지 작업은 한 번에 하나 — 잠시 뒤 다시 |

## 7. Python 버전

같은 기능의 Python 소스가 [`python/photo_editor.py`](python/photo_editor.py) 에 있습니다 (Python 3.9+, 표준 라이브러리만).

---

MIT License · [FlameAI](https://flameai.im) · [API 문서](https://flameai.im/doc)
