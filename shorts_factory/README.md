# A2A Healing Shorts Factory

Google의 [a2a-samples](https://github.com/a2aproject/a2a-samples) 아키텍처 패턴을 엄격히 준수하는 자율적 A2A (Agent-to-Agent) 시스템입니다.

> 이 저장소는 `HealingShorts_Factory_with_A2A` 프로젝트의 실제 구현체로,  
> Planner / Reviewer / Producer / Uploader 에이전트가 서로 A2A 프로토콜로 통신하며 Healing Shorts를 자동 생성합니다.

## 개요

Planner와 Reviewer 에이전트가 Gemini LLM을 통해 피드백 루프로 협업하여 고품질 ASMR/Healing 비디오 프롬프트를 생성하고, Veo로 비디오를 제작한 후 YouTube Shorts에 업로드합니다.

## 핵심 특징

- **엄격한 A2A 통신**: `a2a-samples` 스타일의 Task / AgentCard / AgentMessage 기반 구조화된 에이전트 간 통신
- **LLM 기반 의사결정**: 모든 로직은 Gemini 2.5 Flash 사용, 비즈니스 로직은 최대한 LLM에 위임
- **자율적 피드백 루프**: Planner와 Reviewer가 협업하여 최적의 프롬프트 생성
- **비동기 처리**: FastAPI 비동기 엔드포인트 + 백그라운드 작업으로 비디오 처리 비블로킹
- **MCP 통합**: FastMCP를 통한 Cursor IDE 통합 (`create_healing_short`, `upload_video_to_youtube`, `check_server_health` 툴 제공)
- **MOCK / 실제 모드 자동 전환**: Veo 쿼터 초과 시 자동으로 MOCK 모드로 폴백

## A2A 아키텍처

이 프로젝트는 [a2a-samples](https://github.com/a2aproject/a2a-samples)에 맞춰 다음과 같은 구조를 따릅니다.

- **독립 에이전트 서버**
  - `server/agents/planner_server.py`
  - `server/agents/reviewer_server.py`
  - `server/agents/producer_server.py`
  - `server/agents/uploader_server.py`
- **A2A 클라이언트 / 서버 레이어**
  - `server/a2a_client.py`: Planner / Reviewer / Producer / Uploader 에이전트에 Task를 보내는 클라이언트
  - `server/a2a_server.py`: A2A 프로토콜을 구현하는 에이전트 서버 베이스
  - `server/a2a_config.py`: 각 에이전트의 URL, 포트 설정
- **오케스트레이터**
  - `server/orchestrator.py`: Planner ↔ Reviewer 피드백 루프를 돌리고, 최종 승인된 프롬프트를 Producer / Uploader로 전달

메인 FastAPI 서버(`server/main.py`)는 A2A 오케스트레이션을 감싸는 **HTTP API + Web UI + MCP 브리지** 역할만 담당하며,  
실제 비즈니스 로직은 A2A 에이전트들이 담당합니다.

## 설치

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 다음 변수들을 설정하세요:

#### 필수 환경 변수

```env
# Gemini API 키 (필수)
# Google AI Studio (https://aistudio.google.com/)에서 발급
GEMINI_API_KEY=your-gemini-api-key-here
```

#### 선택적 환경 변수

```env
# 서버 포트 (기본값: 8000)
PORT=8000

# Mock 모드 설정 (기본값: True)
# True: 더미 비디오 생성 및 모킹된 API 사용
# False: 실제 Veo API 및 YouTube API 사용
MOCK_MODE=True

# Vertex AI Veo 설정 (실제 Veo API 사용 시 필요)
# Google Cloud Console에서 프로젝트 ID 확인
GOOGLE_CLOUD_PROJECT_ID=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
VEO_MODEL_NAME=imagegeneration@007

# YouTube 업로드 설정 (YouTube 업로드 사용 시 필요)
# 방법 1: OAuth 클라이언트 시크릿 파일 사용
YOUTUBE_CLIENT_SECRETS_FILE=path/to/client_secrets.json

# 방법 2: OAuth credentials JSON 문자열 사용
# YOUTUBE_OAUTH_CREDENTIALS={"token": "...", "refresh_token": "...", ...}
```

#### 환경 변수 상세 설명

**GEMINI_API_KEY** (필수)
- Google AI Studio (https://aistudio.google.com/)에서 발급
- Planner와 Reviewer 에이전트가 사용하는 LLM API 키
- 발급 방법:
  1. https://aistudio.google.com/ 접속
  2. "Get API Key" 클릭
  3. API 키 생성 또는 기존 키 사용

**MOCK_MODE** (선택, 기본값: True)
- `True`: 더미 비디오 생성, 실제 API 호출 없음 (테스트용)
- `False`: 실제 Veo API 및 YouTube API 사용

**GOOGLE_CLOUD_PROJECT_ID** (실제 Veo 사용 시 필요)
- Google Cloud Console에서 프로젝트 생성 후 프로젝트 ID
- Vertex AI Veo API 사용 시 필요
- 설정 방법:
  1. https://console.cloud.google.com/ 접속
  2. 프로젝트 생성 또는 선택
  3. Vertex AI API 활성화
  4. 프로젝트 ID 확인

**YOUTUBE_CLIENT_SECRETS_FILE** (YouTube 업로드 시 필요)
- YouTube Data API v3 OAuth 2.0 클라이언트 시크릿 파일 경로
- 설정 방법:
  1. https://console.cloud.google.com/apis/credentials 접속
  2. "Create Credentials" > "OAuth client ID" 선택
  3. Application type: "Desktop app" 선택
  4. JSON 파일 다운로드
  5. 파일 경로를 `.env`에 설정

추가로, OAuth 최초 인증 후 생성되는 `token.pickle` 파일과  
`client_secrets.json`, `my-service-account-key.json` 등은 `.gitignore`에 포함되어 **실수로 레포에 올라가지 않도록** 설정되어 있습니다.

## 실행

### 서버 실행

```bash
python -m server.main
```

또는:

```bash
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

### MCP 클라이언트 실행

```bash
python -m client.mcp_bridge
```

Cursor IDE에서 `.cursor/mcp.json`에 이 브리지를 등록하면 다음 MCP 툴을 사용할 수 있습니다.

- `create_healing_short(...)` → `POST /v1/create_shorts`
- `upload_video_to_youtube(...)` → `POST /v1/upload_youtube`
- `check_server_health()` → `GET /health`

## API 사용

### POST /v1/create_shorts

Healing Shorts를 생성합니다.

**요청**:
```json
{
  "topic": "Rain",
  "upload_to_youtube": false,
  "youtube_title": "Healing Rain",
  "youtube_description": "Relaxing rain sounds",
  "youtube_tags": ["healing", "asmr", "rain"]
}
```

**응답**:
```json
{
  "status": "processing",
  "approved_prompt": "Static camera, peaceful rain falling...",
  "conversation_log": [...],
  "message": "프롬프트 승인 완료..."
}
```

## 워크플로우

1. **Planner**: 사용자 키워드를 Veo 프롬프트로 변환
2. **Reviewer**: 프롬프트를 LLM으로 평가 (Static Camera, Theme, Quality)
3. **피드백 루프**: 거부 시 Planner가 피드백을 반영하여 재생성 (최대 5회)
4. **Producer**: 승인된 프롬프트로 Veo 비디오 생성
5. **Loop**: MoviePy로 seamless loop 생성
6. **Uploader**: YouTube Shorts에 업로드 (선택사항)

## 디렉토리 구조

프로젝트 루트 기준:

```
.
├── .gitignore
├── README.md
├── requirements.txt
├── OAUTH_SETUP.md
├── output/                          # 생성된 비디오 (gitignore 대상)
├── client/
│   └── mcp_bridge.py                # FastMCP 클라이언트
├── scripts/
│   ├── start_agent.sh
│   ├── start_agent.bat
│   └── start_all_agents.py          # 모든 에이전트 서버 일괄 실행 스크립트
├── server/
│   ├── main.py                      # FastAPI 메인 서버 (UI + REST + MCP 엔트리포인트)
│   ├── models.py                    # Pydantic 모델
│   ├── orchestrator.py              # A2A 워크플로우 오케스트레이터
│   ├── tools.py                     # 비디오 처리 및 YouTube 업로드 도구
│   ├── a2a_client.py                # A2A 클라이언트
│   ├── a2a_server.py                # A2A 서버 베이스
│   ├── a2a_config.py                # 에이전트 서버 설정
│   └── agents/
│       ├── base.py                  # 베이스 에이전트 (Gemini 연동)
│       ├── planner.py               # Planner 에이전트
│       ├── reviewer.py              # Reviewer 에이전트
│       ├── uploader.py              # Uploader 에이전트
│       ├── producer_server.py       # Producer 에이전트 서버
│       ├── planner_server.py        # Planner 에이전트 서버
│       ├── reviewer_server.py       # Reviewer 에이전트 서버
│       └── uploader_server.py        # Uploader 에이전트 서버
├── static/                          # 웹 UI 정적 파일
└── venv/                            # (선택) 가상환경, gitignore 대상
```

## 빠른 시작

### 1. 저장소 클론

```bash
git clone https://github.com/Eastar0102/HealingShorts_Factory_with_A2A.git
cd HealingShorts_Factory_with_A2A
```

### 2. 가상 환경 생성 (선택사항)

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정

```bash
# .env.example을 .env로 복사
cp .env.example .env

# .env 파일 편집하여 GEMINI_API_KEY 설정
# Windows: notepad .env
# Linux/Mac: nano .env
```

최소한 다음만 설정하면 됩니다:
```env
GEMINI_API_KEY=your-actual-api-key-here
```

### 5. 서버 실행

```bash
python -m server.main
```

서버가 `http://localhost:8000`에서 실행됩니다.

### 6. API 테스트

```bash
curl -X POST "http://localhost:8000/v1/create_shorts" \
  -H "Content-Type: application/json" \
  -d '{"topic": "Rain", "upload_to_youtube": false}'
```

## 문제 해결

### GEMINI_API_KEY 오류

```
ValueError: PlannerAgent: GEMINI_API_KEY가 설정되지 않았습니다.
```

**해결 방법**:
1. `.env` 파일이 프로젝트 루트에 있는지 확인
2. `GEMINI_API_KEY=your-key` 형식으로 올바르게 설정되었는지 확인
3. Google AI Studio에서 API 키가 유효한지 확인

### YouTube 업로드 오류

```
ValueError: YouTube 업로드를 위해 OAuth 인증이 필요합니다.
```

**해결 방법**:
1. Google Cloud Console에서 OAuth 클라이언트 ID 생성
2. `YOUTUBE_CLIENT_SECRETS_FILE`에 파일 경로 설정
3. 또는 `YOUTUBE_OAUTH_CREDENTIALS`에 인증 정보 설정

### Veo API 오류

실제 Veo API를 사용하려면:
1. `MOCK_MODE=False` 설정
2. `GOOGLE_CLOUD_PROJECT_ID` 설정
3. Google Cloud에서 Vertex AI API 활성화

Veo API 쿼터 초과(예: `RESOURCE_EXHAUSTED`)가 발생하면 내부적으로 자동으로 MOCK 모드로 폴백하여  
애플리케이션이 완전히 중단되지 않고, 더미 비디오 생성으로라도 워크플로우가 끝까지 진행되도록 설계되어 있습니다.

## 참고 자료

- [A2A Samples](https://github.com/a2aproject/a2a-samples)
- [Gemini API 문서](https://ai.google.dev/docs)
- [Gemini API 키 발급](https://aistudio.google.com/)
- [FastAPI 문서](https://fastapi.tiangolo.com/)
- [FastMCP](https://github.com/jlowin/fastmcp)
- [Vertex AI Veo 문서](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-reference/veo-video-generation)
- [YouTube Data API 문서](https://developers.google.com/youtube/v3)

