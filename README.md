# FlameAI Playground — apps

FlameAI API 로 만드는 작은 앱과 예제 모음입니다. 블로그 실습 글의 예제 소스와, 바로 내려받아 쓸 수 있는 응용앱을 함께 둡니다.

Small apps and examples built on the FlameAI API — sources for the FlameAI blog tutorials and ready-to-use apps.

- 블로그 / Blog: https://flameai.im/blogHome
- API 문서 / API docs: https://flameai.im/doc

## 받기 / Get

```
git clone https://github.com/FlameAI-Playground/apps
```

블로그 예제는 글 주소의 slug 와 같은 폴더에 있습니다 (`https://flameai.im/blog/{slug}` ↔ `{slug}/`).
Blog examples live in a folder named after the post slug.

```
{slug}/
├─ README.md     설명 / guide
├─ java/         Java (JDK 21+, 라이브러리 없이 / no libraries)
└─ python/       Python (표준 라이브러리만 / standard library only)
```

## 준비 / Setup

1. FlameBox 설치 후 계정 연결 — https://flameai.im/blog/flamebox-install-windows · https://flameai.im/blog/flamebox-install-linux
2. 콘솔에서 Cortex 만들기 — https://flameai.im/blog/first-api-call
3. 소스 위쪽의 상수 2개를 내 값으로 바꿉니다 / set the two constants at the top of the source

| 상수 / Constant | 어디서 / Where |
|---|---|
| `API_URL` | Cortex 목록에서 쓸 Cortex 의 API URL 복사 / Cortex list › API URL (`https://api-….flameai.im/{경로}/cortex/{Cortex ID}/messages`) |
| `SECRET_KEY` | 설정 › My API › Secret key / Settings › My API › Secret key |

> 실제 Secret Key 를 넣은 파일은 공유하거나 저장소에 올리지 마세요. / Never share or commit a file with your real Secret Key.

## 목록 / Index

| 폴더 / Folder | 설명 / Description | 블로그 글 / Post |
|---|---|---|
| [`photo-generator`](photo-generator) | 문장으로 그림을 만드는 AI 이미지 생성기, Qwen Image (Java · Python) / Text-to-image console app | [Java로 만드는 AI 이미지 생성기](https://flameai.im/blog/photo-generator) |
| [`simple-chatbot`](simple-chatbot) | 대화를 기억하는 LLM 콘솔 챗봇 (Java · Python) / LLM console chatbot that remembers the conversation | [Java로 만드는 LLM 챗봇](https://flameai.im/blog/simple-chatbot) |
| [`english-translator`](english-translator) | LLM 기반 AI 번역기, 한국어 ↔ 영어 (Java · Python) / LLM-based Korean ↔ English translator | [Java로 만드는 LLM 기반 AI 번역기](https://flameai.im/blog/english-translator) |

## License

MIT
