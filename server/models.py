"""
A2A 프로토콜 데이터 모델
Pydantic을 사용하여 에이전트 간 통신 구조를 정의합니다.
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from enum import Enum


class AgentMessage(BaseModel):
    """
    A2A 프로토콜의 에이전트 간 메시지 구조
    에이전트들이 서로 통신할 때 사용하는 표준 형식
    """
    sender: str = Field(description="메시지를 보내는 에이전트 이름")
    receiver: str = Field(description="메시지를 받는 에이전트 이름")
    content: str = Field(description="프롬프트 텍스트 또는 피드백 텍스트")
    iteration: int = Field(default=1, description="피드백 루프 반복 횟수")


class ReviewResult(BaseModel):
    """
    Reviewer 에이전트의 검토 결과
    Gemini LLM이 JSON 형식으로 출력하는 구조화된 응답
    """
    status: str = Field(description="Must be 'APPROVED' or 'REJECTED'")
    feedback: str = Field(description="Detailed instructions for the Planner")
    score: int = Field(description="Suitability score (0-100)", ge=0, le=100)


class YouTubeMetadata(BaseModel):
    """
    YouTube 메타데이터 (제목, 설명, 태그)
    Gemini가 자동 생성합니다.
    """
    title: str = Field(description="YouTube 비디오 제목")
    description: str = Field(description="YouTube 비디오 설명")
    tags: List[str] = Field(description="YouTube 비디오 태그 리스트")


class WorkflowResponse(BaseModel):
    """
    워크플로우 실행 결과 응답
    """
    status: str = Field(description="워크플로우 상태: 'processing', 'completed', 'failed'")
    approved_prompt: Optional[str] = Field(default=None, description="최종 승인된 프롬프트")
    conversation_log: List[Dict] = Field(default_factory=list, description="에이전트 간 대화 로그")
    video_path: Optional[str] = Field(default=None, description="생성된 비디오 파일 경로")
    youtube_url: Optional[str] = Field(default=None, description="YouTube 업로드 URL")
    youtube_metadata: Optional[YouTubeMetadata] = Field(default=None, description="YouTube 메타데이터 (Gemini 생성)")
    message: Optional[str] = Field(default=None, description="상태 메시지")


# A2A Protocol Models
class TransportProtocol(str, Enum):
    """A2A 전송 프로토콜"""
    HTTP_JSON = "HTTP+JSON"
    JSONRPC = "JSONRPC"


class AgentSkill(BaseModel):
    """A2A Agent Skill 정의"""
    id: str = Field(description="Skill 고유 ID")
    name: str = Field(description="Skill 이름")
    description: str = Field(description="Skill 설명")
    examples: Optional[List[str]] = Field(default=None, description="사용 예제")
    tags: Optional[List[str]] = Field(default=None, description="태그")


class AgentCapabilities(BaseModel):
    """A2A Agent Capabilities"""
    streaming: bool = Field(default=False, description="스트리밍 지원 여부")
    extensions: Optional[Dict[str, Any]] = Field(default=None, description="확장 기능")


class AgentCard(BaseModel):
    """A2A AgentCard - 에이전트 메타데이터"""
    name: str = Field(description="에이전트 이름")
    description: str = Field(description="에이전트 설명")
    url: str = Field(description="에이전트 URL")
    version: str = Field(default="1.0.0", description="에이전트 버전")
    protocol_version: str = Field(default="0.3.0", description="A2A 프로토콜 버전")
    skills: List[AgentSkill] = Field(description="제공하는 Skill 목록")
    preferred_transport: Optional[TransportProtocol] = Field(
        default=TransportProtocol.HTTP_JSON,
        description="선호하는 전송 프로토콜"
    )
    default_input_modes: List[str] = Field(default=["text"], description="기본 입력 모드")
    default_output_modes: List[str] = Field(default=["text"], description="기본 출력 모드")
    capabilities: Optional[AgentCapabilities] = Field(default=None, description="에이전트 기능")
    supports_authenticated_extended_card: bool = Field(
        default=False,
        description="인증된 확장 카드 지원 여부"
    )


class TaskState(str, Enum):
    """A2A Task 상태"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(BaseModel):
    """A2A Task - 에이전트에 전달되는 작업"""
    skill: str = Field(description="실행할 Skill ID")
    input: Dict[str, Any] = Field(description="Task 입력 데이터")
    task_id: Optional[str] = Field(default=None, description="Task 고유 ID")


class TaskStatus(BaseModel):
    """A2A TaskStatus - Task 실행 결과"""
    state: TaskState = Field(description="Task 상태")
    output: Optional[Dict[str, Any]] = Field(default=None, description="Task 출력")
    message: Optional[str] = Field(default=None, description="상태 메시지")
    error: Optional[str] = Field(default=None, description="에러 메시지")

