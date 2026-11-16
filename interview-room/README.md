# interview-room — AI 면접관과 원격 면접 연습 (Java)

브라우저에 화상 면접실을 띄우고, **내 PC 의 FlameBox 에서 돌아가는 LLM** 이 면접관이 되어 면접을 봅니다.
나는 말로 답하고(브라우저 음성 인식), 면접관은 화상회의 자막처럼 글로 묻습니다. 면접이 끝나면 같은 LLM 이 평가자가 되어 평가표를 줍니다.

A remote (video call) job interview practice app. An LLM Cortex on your own FlameBox plays the interviewer;
you answer by voice (browser speech recognition) or text, and get a score sheet at the end.
Java 21+, one file, no libraries (JDK built-in HTTP server). Blog post: https://flameai.im/blog/interview-room

![interview-room](images/interviewer_f.png)

## 무엇을 하나

| 구분 | 내용 |
|---|---|
| 첫 화면 | 지원 직무 입력 + **면접실 1**(한서연 인사팀장, 친절하지만 날카롭게 되묻는 스타일) · **면접실 2**(강태호 개발본부장, 압박 면접) |
| 면접실 | 왼쪽 면접관 화면 위에 자막(한 글자씩)과 최근 대화, 오른쪽 내 웹캠과 내가 하는 말(실시간 글자) |
| 답하기 | **🎤 말하기** → 말하고 → **✔ 답변 완료**. 입력창에 쳐서 Enter 로 보내도 됩니다 |
| 읽어 주기 | **🔊 읽어 주기** 를 켜면 면접관의 말을 브라우저 음성으로 읽습니다 |
| 끝 | 면접관이 마무리하거나 **면접 끝내기** → 평가표(논리성·구체성·직무 이해·전달력, 잘한 점·고칠 점, 다시 연습할 질문) + `interview_날짜_시각.txt` 저장 |

## 어떻게 동작하나

```
브라우저 (면접실 화면·카메라·음성 인식)  ─ 내 답(글자) ─▶  InterviewRoom.java (JDK HttpServer, 127.0.0.1:8790)  ─▶  내 FlameBox · LLM Cortex
                                         ◀─ 면접관의 말 ─                     │ 면접 기록을 들고 있음
                                                                              └─ 끝나면 기록 전체를 "평가자" 새 대화로 ─▶ 평가표
```

- **면접관은 system 프롬프트 하나**입니다. 이름·직책·성격·직무를 끼워 넣고, 규칙(한 번에 질문 하나, 짧게, 모범 답안을 알려 주지 않기, 끝나면 `[면접종료]`)을 적었습니다.
  같은 코드로 면접관 성격만 바꿔 면접실 두 개를 만듭니다.
- **이어지는 대화는 새 메시지만** 보냅니다. 첫 요청에만 system 과 `cortex_reset: true`, 그다음은 내 답 한 줄씩. Cortex 가 앞의 대화를 기억합니다.
- **평가는 역할 밖에서** 합니다. 면접이 끝나면 프로그램이 들고 있던 기록 전체를 평가자 프롬프트와 함께 `cortex_reset: true` 로 새로 보냅니다.
  면접관은 끝까지 역할을 깨지 않고, 평가는 `temperature: 0.2` 로 차분하게 받습니다. Cortex 는 한 번에 대화 하나만 기억하므로 기록은 프로그램이 들고 있어야 합니다.
- **음성 인식은 브라우저 기능**(Web Speech API)입니다. Chrome·Edge 에서 되고, 소리를 글자로 바꾸는 일은 브라우저 회사(Google·Microsoft)의 서버가 합니다.
  면접 대화와 평가는 내 FlameBox 에서 처리됩니다.

## 1. 준비

1. **FlameBox 설치·계정 연결** — [Windows 편](https://flameai.im/blog/flamebox-install-windows) · [Linux 편](https://flameai.im/blog/flamebox-install-linux)
2. **텍스트 LLM Cortex** — 한국어를 잘하는 모델일수록 면접관 말투가 자연스럽습니다(예: Gemma 4 12B 이상).
3. **JDK 21 이상**
4. **Chrome 또는 Edge** (음성 인식), 웹캠·마이크. 없으면 입력창으로 진행됩니다.

## 2. 받기와 설정

```bash
git clone https://github.com/FlameAI-Playground/apps
cd apps/interview-room/java
```

값 2개가 필요합니다. **API URL** 은 콘솔 Cortex 목록에서 텍스트 Cortex 카드의 주소, **Secret Key** 는 설정 › My API 에서 복사합니다.

### 방법 1 — 환경변수 (권장, 파일에 키가 남지 않음)

```powershell
# Windows PowerShell
$env:FLAMEAI_API_URL    = "https://api-3.flameai.im/Nx7bQ2mZ/cortex/7f3c9a12-4e6b-4d8f-9a21-6b5e8c1f2d3a/messages"
$env:FLAMEAI_SECRET_KEY = "0123456789ABCDEFGH"
java InterviewRoom.java
```

```bash
# macOS · Linux
export FLAMEAI_API_URL="https://api-3.flameai.im/Nx7bQ2mZ/cortex/7f3c9a12-4e6b-4d8f-9a21-6b5e8c1f2d3a/messages"
export FLAMEAI_SECRET_KEY="0123456789ABCDEFGH"
java InterviewRoom.java
```

### 방법 2 — 소스 위쪽 상수

```java
static final String API_URL    = "https://api-xxxx.flameai.im/AbCd1234/cortex/YOUR_CORTEX_ID/messages";
static final String SECRET_KEY = "YOUR_SECRET_KEY";
```

> 실제 Secret Key 를 넣은 파일은 공유하거나 저장소에 올리지 마세요.

## 3. 실행

```
java InterviewRoom.java
면접실이 열렸습니다 → http://localhost:8790   (Ctrl+C 로 종료)
```

브라우저로 http://localhost:8790 을 열고, 직무를 적고 면접실을 고릅니다. 카메라·마이크 권한을 허용하세요.
`images/` 폴더(면접관 사진)를 찾아야 하므로 `java/` 폴더에서 실행합니다.

## 4. 바꿔 보기

| 바꿀 것 | 어디 |
|---|---|
| 면접관 이름·직책·성격, 사진 | `ROOMS` (사진은 `images/` 에 PNG 로) |
| 질문 순서·규칙 | `INTERVIEWER_PROMPT` |
| 평가 항목·형식 | `EVALUATOR_PROMPT` |
| 포트 | `PORT` (기본 8790) |

면접관 사진은 FlameAI 이미지 생성(FLUX 3)으로 만든 가상 인물입니다.

## 5. 한계와 주의

- **연습용입니다.** 평가는 LLM 의 의견이며 실제 합격 여부와 관계가 없습니다. 모델이 평가를 후하게 주는 경향이 있어 프롬프트에 "후하게 주지 말 것"을 적었습니다.
- **음성 인식은 브라우저 회사 서버를 거칩니다.** 민감한 내용이면 입력창으로 답하세요. Firefox 는 음성 인식을 지원하지 않습니다.
- **작은 모델은 역할이 흐려질 수 있습니다** — 질문을 여러 개 한꺼번에 하거나, 일찍 `[면접종료]` 를 붙이기도 합니다.
- **한 번에 면접 하나**(이 PC 에서만 접속, `127.0.0.1`). 실행 중에는 이 Cortex 를 이 앱이 씁니다 — 다른 프로그램이 같은 Cortex 를 쓰면 `cortex_occupied` 가 납니다.
- JDK 내장 HttpServer 는 내 PC 에서 쓰는 도구용입니다. 여러 사람이 쓰는 서비스로 키우려면 Spring Boot·Tomcat 등으로 옮기세요.

## 6. 오류

| 화면에 나오는 말 | 할 일 |
|---|---|
| API URL 또는 Secret Key 가 틀렸습니다 | Cortex 목록·설정 화면에서 다시 복사 |
| FlameBox 가 꺼져 있습니다 | PC/서버에서 FlameBox 켜기 |
| Cortex 가 없거나 삭제되었습니다 | API URL 다시 복사 |
| 다른 대화가 이 Cortex 를 쓰고 있습니다 | 다른 프로그램을 끄거나 면접을 새로 시작 |
| 시간 초과 | 첫 요청은 모델을 올리느라 느립니다 — 잠시 뒤 다시 |
