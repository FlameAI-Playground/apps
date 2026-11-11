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
├─ python/       Python (표준 라이브러리만 / standard library only)
└─ java/         Java (JDK 11+)
```

## 준비 / Setup

1. FlameBox 설치 후 계정 연결 — https://flameai.im/blog/flamebox-install-windows · https://flameai.im/blog/flamebox-install-linux
2. 콘솔에서 Cortex 만들기 — https://flameai.im/blog/first-api-call
3. 환경변수 3개 (콘솔 **설정 › AI 에이전트와 연동하기**에 같은 이름으로 나옵니다 / shown in the console under Settings)

| 이름 / Name | 값 / Value |
|---|---|
| `FLAMEAI_API_BASE` | API base url (예: `https://api-xxxx.flameai.im/AbCd1234`) |
| `FLAMEAI_SECRET_KEY` | Secret key — 코드에 직접 쓰지 마세요 / never hard-code it |
| `FLAMEAI_CORTEX_ID` | 부를 Cortex 의 ID / the Cortex to call |

## 목록 / Index

| 폴더 / Folder | 설명 / Description | 블로그 / Post |
|---|---|---|
| [`english-translator`](english-translator) | 한국어 ↔ 영어 콘솔 번역기 (Python · Java) / Korean ↔ English console translator | [english-translator](https://flameai.im/blog/english-translator) (준비 중 / coming soon) |

## License

MIT
