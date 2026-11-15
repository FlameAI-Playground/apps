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

| 화면 | 명령 |
|---|---|
| 콘솔 대화 | `hermes` |
| 한 번만 묻기 | `hermes chat -q "질문"` |
| 웹 화면 | `hermes dashboard` → http://127.0.0.1:9119 |

## 5. 브리지가 하는 일

| Hermes (OpenAI 형식) | 브리지 | FlameAI |
|---|---|---|
| `GET /v1/models` | Cortex 하나를 모델 `flameai` 로 | — |
| 매번 대화 전체를 보냄 | 앞부분이 Cortex 가 기억하는 것과 같으면 **새 메시지만**, 다르면 `cortex_reset` 으로 다시 구성 | `POST …/messages` |
| `tools` / `role:"tool"` 결과 | 그대로 전달 (FlameBox 가 OpenAI 모양도 받음) | |
| — | 모델이 쓴 도구 호출 원문(`tool_use.raw`, 모델마다 형식이 다름)을 `tool_calls` 로 바꿈 | Qwen 3.5 XML · Gemma 4 · GPT-OSS · JSON |
| 스트리밍 | FlameAI SSE → OpenAI chunk | |

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
