# english-translator — Java로 만드는 LLM 기반 AI 번역기 (한국어 ↔ 영어)

내 PC의 FlameBox 에서 돌아가는 LLM(Cortex)을 불러 **한국어 ↔ 영어**를 번역하는 콘솔 프로그램입니다.
**Java 21 이상**, 라이브러리 없이 파일 하나(`Translator.java`)로 동작하며 컴파일 없이 바로 실행할 수 있습니다.
다른 언어(일본어·중국어 등)도 옵션 하나로 바꿀 수 있습니다.

An LLM-based AI translator (Korean ↔ English) in a single Java file — Java 21+, no libraries.
It calls your own FlameBox Cortex through the FlameAI API. Blog post: https://flameai.im/blog/english-translator

```
$ java Translator.java "오늘 회의 자료를 공유드립니다."
I am sharing today's meeting materials.

$ java Translator.java "Please check the attached file."
첨부된 파일을 확인해 주세요.

$ java Translator.java --to ja < note.txt
ありがとうございます。また明日お会いしましょう。
```

(위 출력은 Gemma 4 12B Cortex 로 실제 실행한 결과입니다. 모델·설정에 따라 문장은 조금씩 달라질 수 있습니다.)

---

## 1. 준비

1. **FlameBox 설치·계정 연결** — [Windows 편](https://flameai.im/blog/flamebox-install-windows) · [Linux 편](https://flameai.im/blog/flamebox-install-linux)
2. **Cortex 만들기** — [첫 API 호출하기](https://flameai.im/blog/first-api-call). 번역에는 **Gemma 4** 같은 다국어에 강한 대화형 모델을 권합니다.
   이 번역기는 요청마다 대화를 새로 시작하므로(아래 4절) **번역 전용 Cortex** 를 하나 만들어 쓰는 것이 좋습니다.
3. **JDK 21 이상** — `java -version` 으로 확인하세요.

## 2. 받기와 설정

```bash
git clone https://github.com/FlameAI-Playground/apps
cd apps/english-translator/java
```

`Translator.java` 위쪽의 상수 2개를 내 값으로 바꿉니다.

```java
static final String API_URL    = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/messages"; // Cortex 목록의 API URL
static final String SECRET_KEY = "YOUR_SECRET_KEY";                                                     // 설정 › My API › Secret key
```

- **API URL** — 마이페이지 › **Cortex** 목록에서 번역에 쓸 Cortex 카드의 주소 옆 **복사**. 내 계정 경로와 Cortex ID 가 들어간 완성된 주소입니다.
- **Secret Key** — 마이페이지 › **설정** › My API 의 Secret key 옆 복사 버튼.

상수 대신 **환경변수** `FLAMEAI_API_URL`, `FLAMEAI_SECRET_KEY` 로 넣어도 됩니다. 상수가 자리 표시 값(`YOUR_…`) 그대로이면 환경변수를 읽습니다 —
키를 소스에 적지 않아도 되어 더 안전합니다. / You can also set the environment variables `FLAMEAI_API_URL` and `FLAMEAI_SECRET_KEY` instead.

> **실제 Secret Key 를 넣은 파일은 공유하거나 저장소에 올리지 마세요.** 키가 새어 나갔다면 설정 화면의 **변경**으로 바로 재발급하세요.

## 3. 실행

| 하고 싶은 것 | 명령 |
|---|---|
| 한 문장 번역 (한글이 있으면 영어로, 없으면 한국어로) | `java Translator.java "번역할 문장"` |
| 다른 언어로 | `java Translator.java --to ja "번역할 문장"` (ko, en, ja, zh, es, fr, de, vi 또는 언어 이름) |
| 파일 통째로 | `java Translator.java < note.txt` |
| 계속 입력하며 번역 | `java Translator.java` → `>` 에 입력, 빈 줄로 종료 |

Java 11 부터는 `.java` 파일을 컴파일 없이 바로 실행할 수 있습니다. 컴파일해서 쓰려면 `javac -encoding UTF-8 Translator.java` 후 `java Translator "…"`.

**첫 실행은 느릴 수 있습니다.** Cortex 가 메모리에서 내려가 있으면 첫 요청 때 모델을 올립니다(시험에서 약 1분).
그 뒤 속도는 FlameBox PC 의 GPU 에 따라 다릅니다.

## 4. 코드 설명 — 핵심은 요청 하나

```java
String body = """
    {"conversationId": "english-translator",
     "options": {"stream": false, "think": false, "cortex_reset": true},
     "messages": [
       {"role": "system", "content": %s},
       {"role": "user", "content": %s}]}
    """.formatted(quote(rule), quote(text));
// POST {API_URL}
// Authorization: Bearer {SECRET_KEY}, Content-Type: application/json, X-API-Version: 1
```

| 짚을 점 | 이유 |
|---|---|
| `system` 메시지 | "번역문만 출력하라"는 규칙을 고정합니다. 설명·따옴표 없이 번역문만 나옵니다 |
| `think: false` | 번역에는 긴 생각 과정이 필요 없습니다. 생각을 끄면 더 빨리 답합니다 (Gemma 4 는 0=끔, 1=켬) |
| `cortex_reset: true` | FlameAI 의 Cortex 는 앞 대화를 **기억**합니다. 서로 관계없는 문장을 번역할 때는 앞 문장이 섞이지 않게 매번 새로 시작합니다 |
| 응답 읽기 | `message.content` 에서 `type` 이 `text` 인 블록의 `text` 를 이어 붙이면 번역문입니다 |
| JSON | 예제를 파일 하나로 두려고 라이브러리 없이 처리했습니다. 실제 프로젝트에서는 Jackson·Gson 을 쓰세요 |

> `cortex_reset: true` 는 다른 대화가 그 Cortex 를 쓰는 중이어도 대화를 가져옵니다. 그래서 번역 전용 Cortex 를 권합니다.
> 반대로 **긴 문서를 문단별로 이어서 번역**할 때는 `cortex_reset` 을 빼고 같은 `conversationId` 로 새 문단만 보내면,
> Cortex 가 앞 문단을 기억해 용어와 말투가 일관됩니다 — FlameAI API 의 특징입니다.

## 5. 응용

- **말투 바꾸기** — 번역 규칙(`rule`)에 "Use a polite business tone." 같은 한 줄을 더합니다.
- **번역하지 않을 단어** — "Do not translate these words: FlameBox, Cortex." 를 더합니다.
- **다른 모델** — 다른 Cortex 의 API URL 로 바꾸면 됩니다. 작은 모델은 빠르지만 번역 품질이 떨어질 수 있습니다.

## 6. 오류가 날 때

| 메시지 | 확인할 것 |
|---|---|
| 상수를 내 값으로 바꾸거나 환경변수를 설정하세요 | `API_URL`·`SECRET_KEY` 를 안 바꿨고 환경변수 `FLAMEAI_API_URL`·`FLAMEAI_SECRET_KEY` 도 없습니다 |
| API URL 또는 Secret Key 가 틀렸습니다 (`bearer_invalid`) | Cortex 목록·설정 › My API 에서 다시 복사. 키를 재발급했다면 새 키 |
| FlameBox 가 꺼져 있습니다 (`cortexbox_offline`) | FlameBox PC/서버가 켜져 있고 콘솔에 ONLINE 인지 |
| 시간 초과 | 첫 요청(모델 로드)은 수십 초~수 분 걸릴 수 있습니다. 잠시 뒤 다시 |

## 7. Python 버전

같은 기능의 Python 소스가 [`python/translate.py`](python/translate.py) 에 있습니다 (Python 3.9+, 표준 라이브러리만).
위쪽 상수 2개(`API_URL`, `SECRET_KEY`)를 바꾼 뒤 `python translate.py "번역할 문장"` 으로 실행합니다.

---

MIT License · [FlameAI](https://flameai.im) · [API 문서](https://flameai.im/doc)
