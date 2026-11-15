# hermes-flameai — Hermes Agent 의 두뇌를 내 PC 의 AI 로 (Python 브리지 · 대화 + 도구 호출)

[Hermes Agent](https://github.com/NousResearch/hermes-agent)(Nous Research 의 오픈소스 AI 에이전트)는 OpenAI 형식(`/v1/chat/completions`) 주소면
어떤 모델이든 두뇌로 쓸 수 있습니다. FlameAI 는 형식이 달라서(대화를 기억하는 Stateful 방식) 그대로는 붙지 않으므로,
**파일 하나짜리 브리지**(`python/flameai_bridge.py`, 표준 라이브러리만)가 중간에서 바꿔 줍니다.

Use your own FlameBox Cortex as the brain of Hermes Agent: a one-file bridge (standard library only) that turns
OpenAI chat-completions requests — including tool calls — into FlameAI `/messages` calls.
Blog post: https://flameai.im/blog/hermes-agent-flameai

```
Hermes Agent ──OpenAI 형식──▶ flameai_bridge.py (내 PC, 127.0.0.1:8765) ──FlameAI 형식──▶ 내 FlameBox 의 Cortex
```

```
❯ 지금 폴더에 hello.txt 파일을 만들고 내용으로 '안녕, FlameAI!' 한 줄을 써줘. 그 다음 지금 폴더의 파일 목록을 확인해서 알려줘.
✍️ Write hello.txt  2.4s
│ +안녕, FlameAI!
💻 $ ls  0.4s
☤ Hermes
hello.txt 파일을 생성했으며, 현재 폴더의 파일 목록은 다음과 같습니다: hello.txt
```

(실제 실행 결과 — 개발 시험용 Gemma 4 E4B Q8, 컨텍스트 64K. 새 대화의 첫 요청 13초, 이어지는 요청 1초 안팎)

## 왜 브리지가 필요한가

Hermes 는 모델을 **OpenAI 형식**(`/v1/models`, `/v1/chat/completions`)으로만 부릅니다. FlameAI Cortex 는 형식이 다릅니다.

| 항목 | Hermes 가 기대하는 것 (OpenAI) | FlameAI Cortex |
|---|---|---|
| 주소 | `/v1/models`, `/v1/chat/completions` | `…/cortex/{id}/messages` |
| 대화 | 매번 처음부터 **전체**를 보냄 (Stateless) | Cortex 가 기억 — **새 메시지만** (Stateful) |
| 도구 호출 응답 | `tool_calls` — 이름 + JSON 인자 | `tool_use.raw` — 모델이 쓴 호출 **원문** (모델마다 모양이 다름) |
| 끝난 이유·스트림 | `finish_reason`, `choices[].delta` | `usage.stop_reason`, `message.delta` 이벤트 |

브리지는 **Hermes 가 보내는 OpenAI 형식(Chat Completions) 요청을 그대로 받아** FlameAI 형식으로 바꿔 Cortex 에 전하고, 답은 다시 Hermes 가 기다리는 형식으로 돌려줍니다.
Hermes 에게는 OpenAI 서버처럼, Cortex 에게는 FlameAI 클라이언트처럼 행동하는 통역사라 Hermes 는 고치지 않습니다. (Hermes 설정의 API mode 3·4 — Responses, Anthropic Messages — 는 지원하지 않습니다.)

## 1. 준비

1. **FlameBox 설치·계정 연결** — [Windows 편](https://flameai.im/blog/flamebox-install-windows) · [Linux 편](https://flameai.im/blog/flamebox-install-linux)
2. **LLM Cortex 하나, 컨텍스트 65536 이상** — Hermes 는 64K 보다 작은 모델은 시작할 때 거부합니다.
   콘솔 Cortex 만들기(또는 설정 변경)에서 **컨텍스트**를 65536 으로. 실제 사용에는 **Gemma 4 12B 이상**을 권장합니다(개발 시험은 가벼운 Gemma 4 E4B 로 했습니다).
3. **Python 3.9 이상** — 브리지용. 설치할 라이브러리는 없습니다.
4. **Hermes Agent** — Windows PowerShell: `iex (irm https://hermes-agent.nousresearch.com/install.ps1)` /
   macOS·Linux: `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash` (공식 설치 안내를 따르세요)

## 2. 브리지 설정 — 값 2개

- **API URL** — 마이페이지 › **Cortex** 목록에서 그 Cortex 카드의 주소 **복사** (`…/messages` 로 끝남)
- **Secret Key** — 마이페이지 › **설정** › My API

**Windows (PowerShell)**
```powershell
$env:FLAMEAI_API_URL    = "https://api-3.flameai.im/Nx7bQ2mZ/cortex/7f3c9a12-4e6b-4d8f-9a21-6b5e8c1f2d3a/messages"
$env:FLAMEAI_SECRET_KEY = "0123456789ABCDEFGH"
python flameai_bridge.py
```

**macOS · Linux**
```bash
export FLAMEAI_API_URL="https://api-3.flameai.im/Nx7bQ2mZ/cortex/7f3c9a12-4e6b-4d8f-9a21-6b5e8c1f2d3a/messages"
export FLAMEAI_SECRET_KEY="0123456789ABCDEFGH"
python3 flameai_bridge.py
```

(예시 값입니다. 또는 `flameai_bridge.py` 위쪽 상수 2개 `API_URL`, `SECRET_KEY` 를 바꿉니다.)

```
FlameAI Bridge: http://127.0.0.1:8765/v1  (model: flameai)  — Ctrl+C 로 종료
```

이 창은 켜 둡니다. Hermes 가 부를 때마다 한 줄씩 기록이 나옵니다.

> **실제 Secret Key 를 넣은 파일은 공유하거나 저장소에 올리지 마세요.** 브리지는 `127.0.0.1`(내 PC)에서만 열립니다.

## 3. Hermes 에 연결

설치 마지막의 설정 마법사(또는 나중에 `hermes setup model`)에서:

| 질문 | 입력 |
|---|---|
| How would you like to set up Hermes? | `2` Full setup |
| Select provider | `Custom endpoint (enter URL manually)` |
| API base URL | `http://127.0.0.1:8765/v1` |
| API key | 비워 두고 Enter (브리지는 키를 보지 않음) |
| API compatibility mode | `2` Chat Completions |
| Use this model? (`flameai`) | `Y` |
| Context length | `65536` |
| Display name | `FlameAI` |

나머지(도구 키, 메신저, 자동 시작)는 건너뛰어도 됩니다. **마법사를 끝까지 마친 뒤** Hermes 를 실행하세요 — 마법사가 열려 있는 동안은
`Gateway draining: update_paused` 로 시작하지 않습니다.

## 4. 실행

브리지 창은 켜 둔 채로 새 터미널에서, Hermes 가 일할 폴더로 이동합니다. Hermes 는 **실행한 폴더**를 기준으로 파일을 만들고 명령을 실행하므로 처음에는 빈 폴더가 안전합니다.

```
D:\workfolder> hermes                      ← 콘솔 대화: 맨 아래 ❯ 에 한국어로 입력하고 Enter
D:\workfolder> hermes dashboard            ← 웹 화면
HERMES_DASHBOARD_READY port=9119
  Hermes Web UI → http://127.0.0.1:9119    ← 브라우저로 열고 왼쪽 CHAT, 맨 아래 ❯ 에 입력
D:\workfolder> hermes chat -q "질문"        ← 한 번만 묻고 끝
```

| 콘솔에서 | 하는 일 |
|---|---|
| `/help` | 명령 목록 |
| `/stop` | 진행 중인 작업 멈추기 |
| `/quit` (또는 `/exit`) | 끝내기 (대시보드는 띄운 터미널에서 Ctrl+C) |

## 5. 브리지가 하는 일 — 도구 호출 한 번의 흐름

1. **Hermes → 브리지**: 시스템 프롬프트 + 지금까지의 대화 전체 + 도구 설명(약 1만 토큰)을 OpenAI 형식으로 보냅니다.
2. **대화 기억 맞추기**: 앞부분이 바로 전에 Cortex 에 보낸 것과 같고, Cortex 상태(`/status` 의 conversationId·last_response_id)도 그대로면
   **새로 붙은 메시지만** 보냅니다. 처음이거나 달라졌으면 `cortex_reset: true` 로 전체를 다시 넣습니다.
3. **Cortex 의 판단**: 도구를 쓰기로 하면 `tool_use` 블록에 호출 원문(`raw`)을 담아 돌려줍니다.

   | 모델 | `raw` 형식 예시 (FlameBox 명세 기준) |
   |---|---|
   | Gemma 4 | `call:write_file{path:<\|"\|>hello.txt<\|"\|>}` |
   | Qwen 3.5·3.8 | `<function=write_file><parameter=path>hello.txt</parameter></function>` |
   | GPT-OSS | `… to=functions.write_file … <\|message\|>{"path":"hello.txt"}` |
   | Qwen 3 | `{"name": "write_file", "arguments": {"path": "hello.txt"}}` |

4. **원문 → `tool_calls`**: `parse_raw()` 가 해석해 OpenAI `tool_calls`(이름 + JSON 문자열 인자)로 바꾸고 `finish_reason: "tool_calls"` 로 돌려줍니다.
   글자로 온 숫자·참거짓은 도구 스키마의 type 에 맞춰 바꿉니다(`fix_types()`).
5. **Hermes 가 실행**: 도구는 내 PC 의 Hermes 가 실행하고, 결과를 `role: "tool"` 로 붙여 다시 보냅니다. 브리지는 2번처럼 **결과만** Cortex 에 넘깁니다
   (FlameBox 는 OpenAI 모양의 `tools`·`role:"tool"` 도 그대로 받습니다). 대화를 다시 구성할 때는 받아 둔 `raw` 를 그대로 돌려줍니다.

| 코드 | 하는 일 |
|---|---|
| `plan()` | 새 메시지만 보낼지, `cortex_reset` 으로 다시 구성할지 결정. 다른 대화가 점유 중이면 409 |
| `to_flame()` | OpenAI 메시지 → FlameAI 메시지 |
| `parse_raw()` · `fix_types()` | 모델별 호출 원문 → `tool_calls` |
| `chat()` | `/messages` 스트림 호출, 결과를 OpenAI 응답으로 |
| `Handler` | `GET /v1/models`, `POST /v1/chat/completions` (stream 은 OpenAI chunk 로) |

- 브리지는 conversationId `hermes-bridge` 로 Cortex 를 씁니다. **다른 대화가 그 Cortex 를 쓰고 있으면 빼앗지 않고** 409 를 돌려줍니다.
- Ctrl+C 로 끄면 Cortex 컨텍스트를 비우고 점유를 풀어 줍니다.
- 이미지 입력은 이 버전에서 넘기지 않습니다(텍스트만).

## 6. 주의

- **Hermes 의 터미널·파일 도구는 내 PC 에서 바로 실행됩니다.** 처음에는 빈 폴더에서 해 보고, 지울 수 없는 일은 시키지 마세요.
  작은 모델(2B 급)은 경로를 잘못 잡아 엉뚱한 곳에 파일을 쓰기도 했습니다.
- Hermes 는 매 요청에 시스템 프롬프트와 도구 설명(약 1만 토큰)을 보냅니다. 새 대화의 첫 요청이 가장 오래 걸립니다.
- 컨텍스트 64K 는 메모리를 많이 씁니다. 같은 FlameBox 에 다른 큰 모델이 올라가 있으면 `failed to initialize context` 가 날 수 있습니다.

## 시험 기록 (2026-11-15, 같은 두 과제)

| 모델 (64K) | 도구 사용 | 답 | 새 대화 첫 요청 | 이어지는 요청 |
|---|---|---|---|---|
| Qwen 3.5 2B | 홈 폴더에 잘못 씀 | 없는 사실을 지어냄 | 4초 | 1~2초 |
| GPT-OSS | 정확 | 영어 | 2~3분 (시험 장비) | 5~10초 |
| **Gemma 4 E4B Q8** | **정확, 두 도구 동시 호출** | **한국어, 정확** | **8~13초** | **1초 안팎** |

개발하면서 시험한 결과이며, 같은 모델이라도 장비(GPU 메모리)에 따라 속도가 크게 다릅니다. Gemma 4 E4B 는 개발용으로 썼고, **실제 사용에는 Gemma 4 12B 이상을 권장합니다.**
