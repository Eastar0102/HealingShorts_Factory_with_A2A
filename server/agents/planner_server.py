"""
PlannerAgent A2A 서버
포트 8001에서 실행되는 독립적인 A2A 에이전트 서버
"""

import uvicorn
import os
from typing import Dict, Any
from ..a2a_server import A2AServerBase
from ..models import AgentCard, AgentSkill, Task, TaskStatus, TaskState, TransportProtocol, AgentCapabilities
from .planner import PlannerAgent


# PlannerAgent 인스턴스 생성
planner_agent = PlannerAgent()


async def handle_planner_task(task: Task) -> TaskStatus:
    """
    Planner Task 처리 함수
    
    Args:
        task: A2A Task 객체
    
    Returns:
        TaskStatus 객체
    """
    import asyncio
    
    try:
        # Task 입력에서 데이터 추출
        task_input = task.input or {}
        topic = task_input.get("topic", "")
        video_duration = task_input.get("video_duration")
        context = task_input.get("context")
        feedback = task_input.get("feedback")  # Reviewer 피드백
        
        if not topic:
            return TaskStatus(
                state=TaskState.FAILED,
                error="topic이 제공되지 않았습니다",
                message="Task 입력에 'topic' 필드가 필요합니다"
            )
        
        # PlannerAgent의 process 메서드 호출
        # 이제 async 함수이므로 직접 await 가능
        if feedback:
            prompt = await planner_agent.process(feedback, context=context, video_duration=video_duration)
        else:
            prompt = await planner_agent.process(topic, context=context, video_duration=video_duration)
        
        return TaskStatus(
            state=TaskState.COMPLETED,
            output={
                "prompt": prompt,
                "topic": topic,
                "video_duration": video_duration
            },
            message="프롬프트 생성 완료"
        )
        
    except Exception as e:
        return TaskStatus(
            state=TaskState.FAILED,
            error=str(e),
            message=f"프롬프트 생성 실패: {str(e)}"
        )


# AgentCard 생성
def create_planner_agent_card(base_url: str = "http://localhost:8001") -> AgentCard:
    """PlannerAgent의 AgentCard 생성"""
    return AgentCard(
        name="PlannerAgent",
        description="Healing/ASMR 콘텐츠를 위한 Veo 프롬프트를 생성하는 에이전트",
        url=base_url,
        version="1.0.0",
        protocol_version="0.3.0",
        skills=[
            AgentSkill(
                id="plan",
                name="Video Prompt Planning",
                description="사용자 키워드를 상세한 Google Veo 프롬프트로 변환합니다. Healing/ASMR 콘텐츠 전문.",
                examples=[
                    "Create a prompt for 'Rain' video",
                    "Generate storyboard for 'Ocean Waves'"
                ],
                tags=["planning", "prompt-generation", "video", "healing", "asmr"]
            )
        ],
        preferred_transport=TransportProtocol.HTTP_JSON,
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        supports_authenticated_extended_card=False
    )


# A2A 서버 생성
def create_server(base_url: str = "http://localhost:8001") -> A2AServerBase:
    """PlannerAgent A2A 서버 생성"""
    agent_card = create_planner_agent_card(base_url)
    return A2AServerBase(agent_card, handle_planner_task)


if __name__ == "__main__":
    """서버 실행"""
    import sys
    
    # 환경 변수에서 포트 및 URL 읽기
    port = int(os.getenv("PLANNER_PORT", "8001"))
    host = os.getenv("PLANNER_HOST", "0.0.0.0")
    base_url = os.getenv("PLANNER_URL", f"http://localhost:{port}")
    
    # 서버 생성
    server = create_server(base_url)
    app = server.get_app()
    
    print(f"PlannerAgent A2A 서버 시작: {base_url}")
    print(f"AgentCard: http://{host}:{port}/a2a/agent_card")
    print(f"Tasks: http://{host}:{port}/a2a/tasks")
    
    # 서버 실행
    uvicorn.run(app, host=host, port=port)

