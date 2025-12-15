## A2A Healing Shorts Factory: 시스템 상세 설계 문서

이 문서는 `A2A Healing Shorts Factory` 프로젝트를 연구·논문에 활용할 수 있도록,  
아키텍처와 동작 원리를 **A2A(Agent-to-Agent) 관점**에서 심층적으로 설명합니다.

---

## 1. 시스템 개요

- **목적**
  - Google Gemini 기반 에이전트들이 **A2A 프로토콜**로 상호 협력하여,
  - ASMR·힐링 계열의 **단편(Shorts) 비디오**를 자동으로 기획·검토·생성·업로드하는 **완전 자율 파이프라인**을 구현.

- **핵심 특징**
  - Planner / Reviewer / Producer / Uploader로 분리된 **역할 기반 멀티 에이전트 시스템**
  - `a2a-samples` 스타일의 **Task / AgentCard / AgentMessage 구조**를 따르는 A2A 통신
  - Gemini 2.5 Flash + Veo(또는 Mock) + YouTube Data API의 **엔드-투-엔드 통합**
  - FastAPI 기반 **웹 UI** 및 **MCP(FastMCP) 브리지**를 통한 IDE 내 제어
  - WebSocket을 통한 **실시간 상태 스트리밍**, MOCK 모드 및 **쿼터 초과 자동 폴백**

---

## 2. 전체 아키텍처

### 2.1 모듈 구성도 (논리 계층)

- **프론트엔드(UI)**
  - `static/index.html`, `static/style.css`, `static/script.js`
  - FastAPI 서버가 `/` 경로에서 서빙하는 단일 페이지 웹 UI
  - WebSocket(`/ws`)을 통해 에이전트 대화 및 비디오 처리 상태를 실시간 시각화

- **메인 서버(오케스트레이션 + API 게이트웨이)**
  - `server/main.py`
    - FastAPI 앱, HTTP REST 엔드포인트, WebSocket 엔드포인트, 정적 파일 서빙
    - A2A 오케스트레이터(`Orchestrator`)와 비디오/업로드 툴(`tools.py`)을 호출
    - 백그라운드 작업(BackgroundTasks)으로 비디오 처리 파이프라인 비동기 실행

- **A2A 오케스트레이터**
  - `server/orchestrator.py`
  - Planner / Reviewer 에이전트 사이의 **피드백 루프**를 담당
  - A2A 클라이언트(`A2AClient`)를 사용하여 각 에이전트 서버에 Task 전송
  - 승인된 프롬프트와 YouTube 메타데이터를 상위 계층에 반환

- **A2A 에이전트 서버**
  - `server/agents/planner_server.py`
  - `server/agents/reviewer_server.py`
  - `server/agents/producer_server.py`
  - `server/agents/uploader_server.py`
  - 각 서버는 공통 베이스(`server/a2a_server.py`, `server/agents/base.py`)를 상속하여
    - HTTP+JSON 기반 A2A Task 수신
    - Gemini LLM 호출
    - TaskStatus(성공/실패, output, error)를 JSON으로 응답

- **비디오/업로드 도구 계층**
  - `server/tools.py`
    - Veo API(or Mock)를 통한 비디오 생성: `generate_veo_clip`, `generate_veo_video_for_duration`
    - MoviePy 기반 후처리(과거 seamless loop 기능, 현재는 원본 그대로 사용)
    - YouTube Data API 기반 업로드(`upload_youtube_shorts`, `resumable_upload`)

- **데이터/프로토콜 모델**
  - `server/models.py`
    - A2A 메시지/Task/TaskStatus, ReviewResult, YouTubeMetadata, WorkflowResponse 정의

- **MCP 브리지**
  - `client/mcp_bridge.py`
    - FastMCP(`FastMCP`)를 이용해 MCP 툴로 노출:
      - `create_healing_short`
      - `upload_video_to_youtube`
      - `check_server_health`
    - 내부적으로 HTTP 요청을 메인 서버의 REST 엔드포인트로 전달

### 2.2 실행 관점: 프로세스/포트 구조

- 메인 서버
  - 모듈: `server.main`
  - 기본 포트: `8000`
  - 역할: 웹 UI, REST API, WebSocket, 오케스트레이션, 에이전트 서버 자동 기동

- 에이전트 서버 (기본 포트는 `A2AConfig` 기준)
  - PlannerAgent 서버: `http://localhost:8001`
  - ReviewerAgent 서버: `http://localhost:8002`
  - ProducerAgent 서버: `http://localhost:8003`
  - UploaderAgent 서버: `http://localhost:8004`

메인 서버는 **시작 시점(`startup` 이벤트)** 과 각 요청 처리 전에,  
해당 포트에서 에이전트가 정상 응답하는지 확인하고, 필요시 **서브프로세스로 자동 기동**합니다.

---

## 3. A2A 데이터 모델 및 프로토콜

### 3.1 핵심 모델 (`server/models.py`)

- **`AgentMessage`**
  - 에이전트 간 텍스트 기반 상호작용을 표준화한 구조
  - 필드:
    - `sender`: 발신 에이전트 이름 (예: `"PlannerAgent"`)
    - `receiver`: 수신 에이전트 이름 (예: `"ReviewerAgent"`)
    - `content`: 프롬프트 또는 피드백 텍스트
    - `iteration`: 피드백 루프 반복 인덱스 (1부터 시작)

- **`Task` / `TaskStatus` / `TaskState`**
  - A2A 프로토콜에서 공통으로 사용하는 **추상 Task 모델**
  - `Task`
    - `skill`: 실행할 스킬 ID (예: `"plan"`, `"review"`)
    - `input`: 스킬별로 필요한 임의의 JSON 데이터
    - `task_id`: 선택적 식별자
  - `TaskStatus`
    - `state`: `TaskState` Enum (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`)
    - `output`: 에이전트 실행 결과(JSON)
    - `message`: 상태 메시지
    - `error`: 에러 메시지

- **`ReviewResult`**
  - Reviewer 에이전트가 프롬프트를 평가한 결과
  - 필드:
    - `status`: `"APPROVED"` 또는 `"REJECTED"`
    - `feedback`: Planner가 따라야 할 구체 지시사항
    - `score`: 0–100 점수(힐링/ASMR 적합성, 카메라/스타일/일관성 등)

- **`YouTubeMetadata`**
  - Gemini를 통해 자동 생성되는 YouTube 업로드용 메타데이터
  - 필드:
    - `title`: 비디오 제목
    - `description`: 설명
    - `tags`: 태그 리스트

- **`WorkflowResponse`**
  - 메인 서버 REST API에서 클라이언트로 반환하는 워크플로우 전체 결과
  - 필드:
    - `status`: `'processing' | 'completed' | 'failed'`
    - `approved_prompt`: 최종 승인 프롬프트
    - `conversation_log`: Planner/Reviewer 간 상호작용 로그
    - `video_path`: 생성된 비디오 경로 (동기 모드에서 사용)
    - `youtube_url`: YouTube 업로드 URL (동기 업로드 모드)
    - `youtube_metadata`: Gemini 생성 메타데이터
    - `message`: 상태 메시지

### 3.2 A2A AgentCard 및 Skill

코드 상에서는 각 에이전트 서버 모듈에서 `AgentCard`와 `AgentSkill`이 정의되며,  
이는 `a2a-samples`의 구조를 따르는 **메타데이터 레이어**입니다.

- **AgentCard**
  - 에이전트 이름, 설명, URL, 버전, 지원 스킬 목록, 프로토콜 버전 등
  - 예: PlannerAgent
    - `skills`: `plan` (프롬프트/스토리보드 생성), `generate_youtube_metadata` 등

- **AgentSkill**
  - 각 스킬의 ID, 설명, 사용 예시, 태그 등을 정의
  - 예: ReviewerAgent
    - `skill = "review"`: 프롬프트를 평가하고 승인/거부 및 피드백 제공

---

## 4. Planner–Reviewer 피드백 루프 (오케스트레이터)

### 4.1 워크플로우 개요 (`server/orchestrator.py`)

`Orchestrator.run_a2a_workflow()` 의 주요 로직:

1. 입력:
   - `user_topic`: 사용자가 요청한 키워드 또는 주제 (예: `"Rain"`)
   - `video_duration`: 목표 비디오 길이 (초)
   - `max_iterations`: 최대 반복 횟수 (기본 5회)

2. 초기 상태:
   - `current_prompt = user_topic`
   - `attempts = 0`
   - `approved_prompt = None`
   - `youtube_metadata = None`

3. Planner / Reviewer 에이전트에 대한 A2A 클라이언트 생성:
   - `A2AClient(self.planner_url)`
   - `A2AClient(self.reviewer_url)`

4. 반복 루프 (최대 `max_iterations` 회):

   1) **Planner 호출**
      - `Task(skill="plan", input={...})` 형태로 Planner 서버에 전송
      - 1회차:
        - `topic = user_topic`
        - `context = None`
        - `feedback = None`
      - 2회차 이상:
        - `topic = current_prompt` (Reviewer 피드백을 반영한 문맥)
        - `context = "Previous prompt was rejected..."` 형태의 설명
        - `feedback = 이전 Reviewer 피드백 요약`
      - Planner 결과:
        - `planner_result.output["prompt"]` → `generated_prompt`
      - `conversation_log`에 Planner의 생성결과를 **AgentMessage** 형식으로 기록

   2) **Reviewer 호출**
      - `Task(skill="review", input={"prompt": generated_prompt, "expected_duration": video_duration})`
      - 반환된 JSON을 `ReviewResult`로 변환
      - `status`가 `"APPROVED"`인 경우:
        - 루프 종료
        - `approved_prompt = generated_prompt`
        - `final_score = review_result.score`
      - `status`가 `"REJECTED"`인 경우:
        - 다음 반복을 위해 `current_prompt`를 **강화된 피드백 메시지**로 변경:
          - 이전 프롬프트가 왜 거부되었는지
          - 원래 요청/목표 길이
          - 반드시 수정해야 할 사항
        - 이 강화된 프롬프트는 다시 Planner에 입력되어, **점진적으로 품질을 개선하는 피드백 루프** 형성

5. 승인 성공 시:
   - `PlannerAgent.generate_youtube_metadata()`를 **오케스트레이터 내부에서 직접 호출** (A2A 바깥의 헬퍼 역할)
   - 실패 시 기본 YouTubeMetadata를 생성:
     - `title = "Healing {topic} - Relaxing ASMR Video"`
     - `tags = ["healing", "asmr", ... , topic.lower()]`

6. 승인 실패 시:
   - 최대 반복 후에도 `approved_prompt`가 없으면 `success=False`와 함께 에러 메시지 반환

### 4.2 시퀀스 다이어그램 (개념적)

다음은 `create_shorts` 호출 시 Planner/Reviewer 루프의 개념적 시퀀스를 나타낸 것입니다.

```text
Client → MainServer(create_shorts)
MainServer → Orchestrator.run_a2a_workflow(topic)

loop (최대 5회)
  Orchestrator → PlannerAgent (Task: plan)
  PlannerAgent → Orchestrator (TaskStatus: COMPLETED, prompt)

  Orchestrator → ReviewerAgent (Task: review(prompt))
  ReviewerAgent → Orchestrator (TaskStatus: COMPLETED, ReviewResult)

  alt 승인(APPROVED)
    Orchestrator → PlannerAgent (generate_youtube_metadata)
    Orchestrator → MainServer (approved_prompt, youtube_metadata, conversation_log)
    break
  else 거부(REJECTED)
    Orchestrator: current_prompt 업데이트 (feedback 기반)
  end
end
```

---

## 5. 비디오 생성 파이프라인

### 5.1 Veo 기반 비디오 생성 (`server/tools.py`)

#### 5.1.1 `generate_veo_clip`

- 입력:
  - `prompt`: Veo 스타일 텍스트 프롬프트
  - `duration_seconds`: 개별 클립 길이(초)
  - `aspect_ratio`: `"9:16"` 또는 `"16:9"`
  - `resolution`: `"1080p"` 등
  - `force_mock`: 강제 Mock 모드 여부

- 동작:
  1. `.env` 로딩 후 `MOCK_MODE` 플래그 확인
  2. **MOCK_MODE=True** 또는 `force_mock=True`이면:
     - MoviePy `ColorClip`을 사용해 단색 배경의 dummy 비디오 생성
     - 크기: 1080×1920 (세로형, Shorts 포맷)
     - 길이: `duration_seconds` (없으면 기본 10초)
  3. **실제 모드**인 경우:
     - `google-genai` 클라이언트를 통해 Veo 모델(`VEO_MODEL_NAME`) 호출
     - 프롬프트에서 **OVERALL PROMPT FOR VEO** 섹션 및 마크다운 제거
     - 비율/해상도/길이를 프롬프트 및 config에 명시
     - 최대 8초짜리 비디오를 1개 생성 (또는 다수 호출 시 분할 생성)
     - 결과 비디오를 다운로드하여 `output/`에 저장
  4. Veo 쿼터 초과/429/RESOURCE_EXHAUSTED 발생 시:
     - 예외를 포착하고 로그 출력 후
     - 자동으로 **Mock 모드로 재호출**하여 워크플로우를 끝까지 유지

#### 5.1.2 `generate_veo_video_for_duration`

- 목적:
  - Veo가 단일 요청당 약 8초까지 지원한다는 제약을 고려하여,
  - 원하는 전체 길이(예: 30초)를 **여러 클립으로 분할 생성 후 병합**.

- 로직:
  - `total_duration_seconds` ≤ 8초:
    - 단일 `generate_veo_clip` 호출
  - `total_duration_seconds` > 8초:
    - `[8, 8, 나머지]` 형태로 세그먼트 분할
    - 각 세그먼트에 대해 `generate_veo_clip` 호출 → temp 파일 리스트 확보
    - MoviePy `concatenate_videoclips`로 병합
    - `veo_multi_<timestamp>.mp4` 이름으로 저장 후, 임시 파일 삭제

### 5.2 메인 서버의 파이프라인 연계 (`server/main.py`)

#### 5.2.1 비동기 파이프라인 (`process_video_pipeline_with_updates`)

- 입력:
  - `approved_prompt`
  - `video_duration`
  - `upload_to_youtube` 플래그
  - YouTube 메타데이터 (Gemini 생성 or 사용자 입력)

- 단계:

1. WebSocket 브로드캐스트:
   - `"Veo 비디오 생성 중..."` 상태 메시지 전송 (`type="video_status", step="veo_generation"`)

2. 비디오 생성:
   - `generate_veo_video_for_duration(...)` 호출
   - 생성 완료 후:
     - 파일 경로/파일명을 WebSocket으로 전송

3. YouTube 업로드 (옵션):
   - `upload_to_youtube=True`인 경우
     - `process_youtube_upload_with_updates()` 호출
     - 성공/실패 여부를 WebSocket 이벤트로 브로드캐스트

4. 최종 완료:
   - `status="completed"` 메시지 브로드캐스트
   - `final_video_path`, `video_filename`, `youtube_url`, `youtube_metadata` 등 포함

#### 5.2.2 동기 파이프라인 (`process_video_pipeline_sync`)

- MCP 등에서 **완전한 동기 응답**을 원하는 경우 사용
- 주요 차이:
  - WebSocket 브로드캐스트 없이, 내부에서만 비디오 생성·업로드를 실행
  - 호출자에게 `{"success": True/False, "video_path", "youtube_url"}` 형태로 직접 반환

---

## 6. YouTube 업로드 설계

### 6.1 업로드 함수 (`upload_youtube_shorts`)

- 모드 분기:
  - `MOCK_MODE=True`:
    - 실제 API 호출 없이 더미 URL(`https://www.youtube.com/watch?v=dQw4w9WgXcQ`) 반환
    - 개발/테스트 단계에서 안전하게 사용 가능
  - `MOCK_MODE=False`:
    - YouTube Data API v3를 통한 실제 업로드 수행

- 인증 처리:
  - OAuth 2.0 Desktop App 플로우 사용
  - `YOUTUBE_CLIENT_SECRETS_FILE` 또는 `YOUTUBE_OAUTH_CREDENTIALS` 환경 변수로 설정
  - 최초 인증 이후 `token.pickle`에 credential 저장 → 이후 자동 재사용

- 업로드 전략:
  - `MediaFileUpload(resumable=True)` 를 사용한 **재개 가능한 업로드**
  - `resumable_upload` 함수에서:
    - `MAX_RETRIES=10`, 지수 백오프(Exponential Backoff) 전략
    - 재시도 가능한 HTTP 상태 코드: 500, 502, 503, 504
    - 업로드 진행률(%)를 로그로 표시

### 6.2 메인 서버와의 연계

- `/v1/upload_youtube` (FastAPI 엔드포인트)
  - 요청 바디: `video_path`, `title`, `description`, `tags`, `privacy_status`
  - 상대 경로를 프로젝트 루트 혹은 `output` 디렉터리 기준 절대 경로로 변환
  - `BackgroundTasks`에 `process_youtube_upload_with_updates` 등록:
    - UploaderAgent 사용
    - WebSocket으로 업로드 상태(`uploading`, `upload_complete`, `upload_failed`) 브로드캐스트

---

## 7. 메인 서버 API 설계

### 7.1 `POST /v1/create_shorts` (비동기)

- 목적: Healing Shorts 생성 시작, 즉시 `'processing'` 상태 응답
- 요청 바디(`CreateShortsRequest`):
  - `topic: str` – 비디오 주제 키워드
  - `video_duration: float = 30.0` – 1~300초
  - `upload_to_youtube: bool = False` – 자동 업로드 여부
  - `youtube_title/description/tags` – 선택적 메타데이터

- 처리 흐름:
  1. Planner/Reviewer 에이전트 헬스 체크 및 필요 시 자동 기동 (`ensure_agent_servers_running`)
  2. `Orchestrator.run_a2a_workflow` 호출로 승인 프롬프트 및 YouTube 메타데이터 획득
  3. `BackgroundTasks`에 비디오 파이프라인 등록 (`process_video_pipeline_with_updates`)
  4. `status="processing"`, `approved_prompt`, `conversation_log`, `youtube_metadata` 등을 응답

### 7.2 `POST /v1/create_shorts_sync` (동기)

- 목적: 비디오 생성 및 YouTube 업로드까지 완료된 **최종 결과**를 동기적으로 반환
- 동일한 `CreateShortsRequest` 사용
- 처리 흐름:
  1. A2A 워크플로우 실행 (Planner/Reviewer 루프)
  2. `process_video_pipeline_sync` 호출 → 비디오 생성(+옵션 업로드) 완료까지 대기
  3. `status="completed"`, `video_path`, `youtube_url`, `approved_prompt` 등 포함해 반환

### 7.3 `POST /v1/upload_youtube`

- 이미 생성되어 저장된 비디오를 **사후 업로드**하는 엔드포인트
- 웹 UI의 "Video Library" 와 YouTube 업로드 섹션에서 사용

### 7.4 `GET /v1/list_videos`

- `output/` 디렉터리 내 `.mp4` 파일 목록을 반환
  - 파일명, 상대 경로, `/videos/<filename>` URL, 파일 크기(MB), 수정시각 등

### 7.5 `GET /health`

- 단순 헬스 체크 (`{"status": "healthy"}`) – MCP 및 외부 모니터링에서 사용

---

## 8. 웹 UI 설계

### 8.1 레이아웃 (`static/index.html`, `style.css`)

- **좌측 컬럼**
  - **Create New Shorts** 섹션
    - `topic` 텍스트 입력
    - `videoDuration` 숫자 입력 (초 단위, 기본 30)
    - `Start Generation` 버튼 → `POST /v1/create_shorts`
  - **Agent Workflow** 상태 카드
    - WebSocket 이벤트(`agent_message`) 기반 Planner/Reviewer 로그 표시
  - **Video Processing** 상태 카드
    - WebSocket 이벤트(`video_status`, `youtube_upload_status`) 기반 비디오/업로드 진행 상황 표시

- **우측 컬럼**
  - **Preview**
    - 생성 완료된 비디오를 `<video>` 태그로 바로 재생
  - **Upload to YouTube** 섹션
    - Gemini가 생성한 메타데이터를 입력 폼에 자동 채우고, 사용자가 수정 가능
    - `Upload to YouTube` 버튼 → `/v1/upload_youtube`
  - **Video Library**
    - `/v1/list_videos`로부터 출력된 비디오 목록
    - 각 항목에서 "YouTube 업로드" 버튼으로 사후 업로드 가능

### 8.2 WebSocket 상호작용 (`static/script.js`)

- `connectWebSocket()`
  - `/ws`에 연결, 끊어질 시 3초 간격으로 자동 재연결

- 이벤트 타입:
  - `agent_message`
    - Planner: `"프롬프트 생성"` 로그
    - Reviewer: `"프롬프트 검토"` 로그, 점수/피드백 표시
  - `video_status`
    - `generating`, `veo_complete`, `completed`, `error` 등 상태에 따라 UI 배지/로그 업데이트
    - `completed` 시:
      - `video_filename` 또는 `final_video_path`를 이용해 preview 영역 업데이트
      - YouTube 업로드 섹션 노출 + 메타데이터 폼 초기화
  - `youtube_upload_status`
    - `uploading`, `upload_complete`, `upload_failed` 상태에 따라 메시지 및 버튼 상태 갱신

---

## 9. MCP 통합 설계

### 9.1 MCP 브리지 (`client/mcp_bridge.py`)

- `FastMCP("A2A Healing Shorts Factory Bridge")` 인스턴스를 생성하여 MCP 서버 역할 수행

- 정의된 MCP 툴:

1. **`create_healing_short`**
   - 인자:
     - `topic: str`
     - `video_duration: float = 30.0`
     - `upload_to_youtube: bool = False`
     - `youtube_title/description/tags`
   - 동작:
     - `upload_to_youtube=True`이면 `/v1/create_shorts_sync` 호출
     - 아니면 `/v1/create_shorts` 호출
   - `conversation_log`를 사람이 읽기 쉬운 `formatted_conversation_log`로 가공

2. **`upload_video_to_youtube`**
   - 인자:
     - `video_path`
     - `title/description/tags`
     - `privacy_status`
   - 동작:
     - `/v1/upload_youtube`에 POST 요청

3. **`check_server_health`**
   - 단순히 `/health` 엔드포인트의 상태를 반환

### 9.2 Cursor IDE에서의 사용

- `.cursor/mcp.json` 예시:

```json
{
  "mcpServers": {
    "shorts-factory": {
      "command": "python",
      "args": ["-m", "client.mcp_bridge"]
    }
  }
}
```

이 설정을 통해 개발자는 **IDE 안에서 직접**:
- Healing Shorts 생성,
- YouTube 업로드,
- 서버 상태 확인을 모두 MCP 툴 호출만으로 수행할 수 있습니다.

---

## 10. 환경 설정 및 실행

### 10.1 필수 환경 변수

- `GEMINI_API_KEY`
  - Gemini 2.x / Veo용 API 키
  - Planner/Reviewer 및 Veo(실제 모드)에서 사용

### 10.2 선택적 환경 변수 (주요 항목)

- 서버 관련
  - `PORT`: 메인 FastAPI 서버 포트 (기본 8000)

- 모드/Backend 관련
  - `MOCK_MODE`: `True`(기본) / `False`
    - True: Veo/YouTube 모두 Mock 동작, 개발·테스트용
    - False: 실제 API 호출

- Veo/Vertex AI 관련
  - `GOOGLE_CLOUD_PROJECT_ID`, `GOOGLE_CLOUD_LOCATION`, `VEO_MODEL_NAME`

- YouTube 관련
  - `YOUTUBE_CLIENT_SECRETS_FILE` 또는 `YOUTUBE_OAUTH_CREDENTIALS`
  - 최초 인증 후 생성되는 `token.pickle` 사용

### 10.3 실행 절차 요약

1. 의존성 설치: `pip install -r requirements.txt`
2. `.env` 생성 및 `GEMINI_API_KEY` 설정
3. 메인 서버 실행:
   - `python -m server.main` 또는
   - `uvicorn server.main:app --host 0.0.0.0 --port 8000`
4. (선택) MCP 브리지 실행:
   - `python -m client.mcp_bridge`

---

## 11. 연구 관점에서의 특징 및 확장 가능성

### 11.1 연구 포인트

- **A2A 피드백 루프의 효과 분석**
  - Planner/Reviewer 반복 구조가 프롬프트 품질(예: 주관적 선호도, 시청 유지율)에 미치는 영향
  - 반복 횟수와 Reviewer 점수(`final_score`) 간 상관관계

- **LLM 기반 메타데이터 자동 생성**
  - `YouTubeMetadata`의 태그/제목이 실제 YouTube 알고리즘(조회수, 추천 노출)에 미치는 영향
  - LLM 생성 메타데이터 vs 수동 작성 메타데이터 비교 실험 가능

- **MOCK 모드와 실제 모드의 차이**
  - Mock 비디오(단색 배경)로도 사용자 주관 평가 실험(예: 프롬프트 텍스트만 보여주기)이 가능
  - 실제 Veo 비디오와 비교한 시청 경험, 시청 시간, 피드백 등 측정

### 11.2 확장 방향

- 에이전트 추가
  - 예: BGM/사운드 전용 SoundDesigner 에이전트
  - 예: 썸네일 생성용 ImageDesigner 에이전트

- Reviewer 다중화
  - 여러 Reviewer 에이전트를 구성하여 **다수결** 또는 **가중 평균** 기반 승인 전략 등 연구 가능

- 품질 메트릭의 정교화
  - ReviewResult에 카테고리별 점수(카메라, 색감, 동작, 치료적 요소 등)를 도입
  - 프롬프트 구조(`Subject/Style/Action/Lighting/Camera`)와 점수 간 관계 분석

---

## 12. 결론

본 프로젝트는 **A2A 에이전트 아키텍처**, **LLM 기반 프롬프트 최적화**,  
**멀티모달(텍스트→비디오→YouTube) 파이프라인**을 통합한 실험 플랫폼입니다.

- Planner/Reviewer의 피드백 루프를 통해
  - 휴먼 개입 없이도 일정 수준의 품질을 보장하는 힐링 비디오 프롬프트를 생성하고,
- Veo 및 YouTube API, Web UI, MCP 통합을 통해
  - 연구자와 개발자가 동일한 인프라 위에서 다양한 실험을 수행할 수 있도록 설계되었습니다.

이 문서를 기반으로, 연구자는 각 계층(에이전트, 오케스트레이션, 비디오 처리, 업로드, UI, MCP)에서  
구체적인 실험 가설과 평가 지표를 정의하고, 논문/프로젝트에 적합한 형태로 재구성할 수 있습니다.





