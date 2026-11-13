# turtle-neck-monitor — 웹캠 자세(거북목)·집중 코치 (Python · Gemma 4 E4B · OpenCV) — 실험판

[`focus-coach`](../focus-coach) 에서 갈라져 나온 실험판입니다. focus-coach 가 상태(자리·상태·표정)만 보여 주는 것과 달리,
이 버전은 **OpenCV 로 얼굴 크기를 재서 거북목을 잡고**, 딴짓·졸음·자리 비움이 길어지면 **경고**, 집중하면 **응원**(화면·소리·음성)합니다.

An experimental fork of focus-coach: adds turtle-neck detection with OpenCV (face size vs. your reference posture),
warnings when you rest/sleep/leave too long, cheers, and voice alerts.

> 아직 다듬는 중이라 블로그 글은 없습니다. 판단 기준(경고 시간·거북목 배율)은 소스 위쪽 상수에서 바꿉니다.

## 실행

```bash
pip install -r requirements.txt          # opencv-python 4.x (5.0 에는 얼굴 검출기 Haar 가 없음)
# 환경변수 FLAMEAI_API_URL (Gemma 4 E4B Cortex 의 API URL), FLAMEAI_SECRET_KEY 를 넣거나 소스 위쪽 상수를 바꾼 뒤
python python/turtle_neck_monitor.py     # → http://localhost:8080
```

시작할 때 몇 초 동안 바르게 앉아 있으면 그 자세를 기준으로 잡고, 얼굴이 기준보다 1.4배 이상 커지면(화면에 다가가면) 거북목으로 봅니다.
정면 캠으로 재는 어림값이라 의자·캠 위치가 바뀌면 다시 시작하세요. 본인만 쓰세요 — 다른 사람을 동의 없이 찍거나 감정을 판정하면 안 됩니다.

> 실제 Secret Key 를 넣은 파일은 공유하거나 저장소에 올리지 마세요.
