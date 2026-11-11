# simple-chatbot — Java로 만드는 LLM 콘솔 챗봇 (대화를 기억하는 AI)

내 PC의 FlameBox 에서 돌아가는 LLM(Cortex)과 터미널에서 대화하는 챗봇입니다.
**Java 21 이상**, 라이브러리 없이 파일 하나(`Chatbot.java`)로 동작하며 컴파일 없이 바로 실행할 수 있습니다.

핵심은 FlameAI API 의 **이어서 대화하기**입니다. 일반적인 AI API 는 매번 지금까지의 대화 전체를 다시 보내야 하지만,
FlameAI 의 Cortex 는 앞 대화를 기억하므로 **새 메시지만** 보내면 됩니다.

An LLM console chatbot in a single Java file (Java 21+, no libraries). The Cortex remembers the conversation,
so the client sends only the new message. Blog post: https://flameai.im/blog/simple-chatbot

```
$ java Chatbot.java
FlameAI chatbot  (/reset: 새 대화, /exit 또는 빈 줄: 종료, /help)
> 안녕! 내 이름은 민수야. 자바 개발자야.
반가워 민수야! 자바 개발자구나. 만나서 정말 기뻐. 앞으로 궁금한 게 있거나 도움이 필요하면 언제든 물어봐!
> 내 이름이 뭐라고 했지? 내 직업은?
네 이름은 민수이고, 직업은 자바 개발자야.
> /reset
(새 대화를 시작합니다)
> 내 이름이 뭐라고 했지?
죄송하지만 아직 이름을 말씀해 주지 않으셔서 제가 알 수 없습니다. 이름을 알려주시면 기억해 둘게요!
```

(위 출력은 Gemma 4 12B Cortex 로 실제 실행한 결과입니다.)

---

## 1. 준비

1. **FlameBox 설치·계정 연결** — [Windows 편](https://flameai.im/blog/flamebox-install-windows) · [Linux 편](https://flameai.im/blog/flamebox-install-linux)
2. **Cortex 만들기** — [첫 API 호출하기](https://flameai.im/blog/first-api-call). Gemma 4 · Qwen 같은 대화형 모델이면 됩니다.
3. **JDK 21 이상** — `java -version` 으로 확인하세요.

## 2. 받기와 설정

```bash
git clone https://github.com/FlameAI-Playground/apps
cd apps/simple-chatbot/java
```

`Chatbot.java` 위쪽의 상수 2개를 내 값으로 바꿉니다.

```java
static final String API_URL    = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/messages"; // Cortex 목록의 API URL
static final String SECRET_KEY = "YOUR_SECRET_KEY";                                                     // 설정 › My API › Secret key
```

- **API URL** — 마이페이지 › **Cortex** 목록에서 쓸 Cortex 카드의 주소 옆 **복사**.
- **Secret Key** — 마이페이지 › **설정** › My API 의 Secret key 옆 복사 버튼.

> **실제 Secret Key 를 넣은 파일은 공유하거나 저장소에 올리지 마세요.**

챗봇의 성격은 `SYSTEM_PROMPT` 한 줄로 바꿉니다 (예: "You are a Java tutor. Explain with short code examples.").

## 3. 실행

```bash
java Chatbot.java
```

| 입력 | 동작 |
|---|---|
| 아무 문장 | AI 에게 보냅니다 — 앞 대화를 기억한 채로 답합니다 |
| `/reset` | 대화를 비우고 새로 시작합니다 |
| `/help` | 명령 안내 |
| `/exit` 또는 빈 줄 | 종료 |

첫 응답은 Cortex 를 메모리에 올리느라 조금 걸릴 수 있습니다(시험에서 수십 초). 그 뒤 속도는 FlameBox PC 의 GPU 에 따라 다릅니다.

## 4. 코드 설명 — 새 메시지만 보낸다

```java
// 새 대화면 규칙(system) + cortex_reset:true, 이어지는 대화면 새 메시지만
String system = newConversation ? "{\"role\": \"system\", \"content\": " + quote(SYSTEM_PROMPT) + "}," : "";
String body = """
    {"conversationId": "simple-chatbot",
     "options": {"stream": false, "think": false, "cortex_reset": %s},
     "messages": [%s {"role": "user", "content": %s}]}
    """.formatted(newConversation, system, quote(userMessage));
```

| 짚을 점 | 이유 |
|---|---|
| 같은 `conversationId` | Cortex 는 이 ID 의 대화를 기억합니다. 두 번째 요청부터는 **새 메시지 하나**만 보냅니다 |
| `cortex_reset: true` (첫 요청·`/reset`) | 이전 대화를 비우고 이번 `messages` 로 새로 시작합니다 |
| `system` 메시지 (첫 요청만) | 챗봇의 성격·말투. 대화 내내 유지됩니다 |
| `think: false` | 생각 과정을 끄고 바로 답합니다. 깊이 생각하는 답이 필요하면 `true` |

대화가 길어져도 매번 보내는 데이터는 새 메시지 하나라 가볍고, 앞부분을 다시 계산하지 않아 응답도 빠릅니다.

> 하나의 Cortex 는 한 번에 대화 하나를 맡습니다. 다른 프로그램이 같은 Cortex 를 쓰는 중이면 `cortex_occupied` 가 나며,
> `/reset` 으로 새 대화를 시작하면 이 챗봇으로 가져옵니다. 여러 사람이 동시에 쓰려면 Cortex 를 사람 수만큼 만드세요.

## 5. 오류가 날 때

| 메시지 | 확인할 것 |
|---|---|
| 상수를 내 값으로 바꾸세요 | `API_URL`·`SECRET_KEY` 를 아직 안 바꿨습니다 |
| API URL 또는 Secret Key 가 틀렸습니다 (`bearer_invalid`) | Cortex 목록·설정 › My API 에서 다시 복사 |
| FlameBox 가 꺼져 있습니다 (`cortexbox_offline`) | FlameBox PC/서버가 켜져 있고 콘솔에 ONLINE 인지 |
| 다른 대화가 이 Cortex 를 쓰고 있습니다 (`cortex_occupied`) | `/reset` 으로 가져오거나 다른 Cortex 사용 |
| 시간 초과 | 첫 요청(모델 로드)은 오래 걸릴 수 있습니다. 잠시 뒤 다시 |

## 6. Python 버전

같은 기능의 Python 소스가 [`python/chatbot.py`](python/chatbot.py) 에 있습니다 (Python 3.9+, 표준 라이브러리만).
위쪽 상수 2개를 바꾼 뒤 `python chatbot.py` 로 실행합니다.

---

MIT License · [FlameAI](https://flameai.im) · [API 문서](https://flameai.im/doc)
