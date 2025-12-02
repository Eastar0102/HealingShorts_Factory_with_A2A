"""
ReviewerAgent A2A 서버
포트 8002에서 실행되는 독립적인 A2A 에이전트 서버
"""

import uvicorn
import os
from typing import Dict, Any
from ..a2a_server import A2AServerBase
from ..models import AgentCard, AgentSkill, Task, TaskStatus, TaskState, TransportProtocol, AgentCapabilities
from .reviewer import ReviewerAgent


# ReviewerAgent 인스턴스 생성
reviewer_agent = ReviewerAgent()


async def handle_reviewer_task(task: Task) -> TaskStatus:
    """
    Reviewer Task 처리 함수
    
    Args:
        task: A2A Task 객체
    
    Returns:
        TaskStatus 객체
    """
    import asyncio
    
    try:
        # Task 입력에서 데이터 추출
        task_input = task.input or {}
        prompt = task_input.get("prompt", "")
        expected_duration = task_input.get("expected_duration")
        
        if not prompt:
            return TaskStatus(
                state=TaskState.FAILED,
                error="prompt가 제공되지 않았습니다",
                message="Task 입력에 'prompt' 필드가 필요합니다"
            )
        
        # ReviewerAgent의 evaluate 메서드 호출
        # 이제 async 함수이므로 직접 await 가능
        review_result = await reviewer_agent.evaluate(prompt, expected_duration=expected_duration)
        
        return TaskStatus(
            state=TaskState.COMPLETED,
            output={
                "status": review_result.status,
                "feedback": review_result.feedback,
                "score": review_result.score
            },
            message=f"프롬프트 검토 완료: {review_result.status}"
        )
        
    except Exception as e:
        return TaskStatus(
            state=TaskState.FAILED,
            error=str(e),
            message=f"프롬프트 검토 실패: {str(e)}"
        )


# AgentCard 생성
def create_reviewer_agent_card(base_url: str = "http://localhost:8002") -> AgentCard:
    """ReviewerAgent의 AgentCard 생성"""
    return AgentCard(
        name="ReviewerAgent",
        description="Healing Shorts 프롬프트의 품질을 검토하고 평가하는 에이전트",
        url=base_url,
        version="1.0.0",
        protocol_version="0.3.0",
        skills=[
            AgentSkill(
                id="review",
                name="Prompt Quality Review",
                description="Veo 프롬프트를 평가하여 Healing/ASMR 콘텐츠에 적합한지 검토합니다.",
                examples=[
                    "Review prompt for healing video",
                    "Evaluate storyboard quality"
                ],
                tags=["review", "quality-check", "validation", "healing", "asmr"]
            )
        ],
        preferred_transport=TransportProtocol.HTTP_JSON,
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        supports_authenticated_extended_card=False
    )


# A2A 서버 생성
def create_server(base_url: str = "http://localhost:8002") -> A2AServerBase:
    """ReviewerAgent A2A 서버 생성"""
    agent_card = create_reviewer_agent_card(base_url)
    return A2AServerBase(agent_card, handle_reviewer_task)


if __name__ == "__main__":
    """서버 실행"""
    import sys
    
    # 환경 변수에서 포트 및 URL 읽기
    port = int(os.getenv("REVIEWER_PORT", "8002"))
    host = os.getenv("REVIEWER_HOST", "0.0.0.0")
    base_url = os.getenv("REVIEWER_URL", f"http://localhost:{port}")
    
    # 서버 생성
    server = create_server(base_url)
    app = server.get_app()
    
    print(f"ReviewerAgent A2A 서버 시작: {base_url}")
    print(f"AgentCard: http://{host}:{port}/a2a/agent_card")
    print(f"Tasks: http://{host}:{port}/a2a/tasks")
    
    # 서버 실행
    uvicorn.run(app, host=host, port=port)

