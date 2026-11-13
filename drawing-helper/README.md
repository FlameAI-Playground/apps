# drawing-helper — 대충 써도 그려 주는 AI 그림 도우미 (Java · LLM + Qwen Image) — 준비 중

한국어로 대충 설명하면 대화 Cortex(LLM)가 자세한 영어 이미지 프롬프트로 다듬고, 이미지 Cortex(Qwen Image 2.1 등)가 그려 PNG 로 저장하는 콘솔 프로그램입니다.
"좀 더 따뜻하게" 처럼 고칠 점을 말하면 같은 대화로 이어서 다시 다듬습니다.

Describe a picture in your own words: an LLM Cortex rewrites it as a detailed English prompt, and an image Cortex draws it (Java 21+, no libraries).

> 블로그 글은 준비 중입니다.

## 실행

```bash
# 상수 3개 — CHAT_URL(대화 Cortex 의 API URL), IMAGE_URL(이미지 Cortex 의 API URL), SECRET_KEY
# 또는 환경변수 FLAMEAI_CHAT_URL, FLAMEAI_IMAGE_URL, FLAMEAI_SECRET_KEY
java java/DrawingHelper.java              # --size 1024x768  --seed 42
```

```
그릴 것을 말해 주세요> 비 오는 밤 골목에서 우산 쓴 고양이
[영어 프롬프트] …
고칠 점 (Enter = 그리기)> 좀 더 따뜻한 분위기로
고칠 점 (Enter = 그리기)>                 ← drawing-1.png 저장
```

이미지 모델은 VRAM 을 많이 씁니다. 대화 Cortex 와 이미지 Cortex 가 같은 PC 에 함께 올라가면 메모리가 모자랄 수 있어, 다른 PC 의 Cortex 를 쓰는 것을 권합니다.

> 실제 Secret Key 를 넣은 파일은 공유하거나 저장소에 올리지 마세요.
