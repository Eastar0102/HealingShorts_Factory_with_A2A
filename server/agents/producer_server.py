"""
ProducerAgent A2A 서버
포트 8003에서 실행되는 독립적인 A2A 에이전트 서버
"""

import uvicorn
import os
from typing import Dict, Any
from ..a2a_server import A2AServerBase
from ..models import AgentCard, AgentSkill, Task, TaskStatus, TaskState, TransportProtocol, AgentCapabilities
from ..tools import generate_veo_clip, make_seamless_loop


def handle_producer_task(task: Task) -> TaskStatus:
    """
    Producer Task 처리 함수
    
    Args:
        task: A2A Task 객체
    
    Returns:
        TaskStatus 객체
    """
    try:
        # Task 입력에서 데이터 추출
        task_input = task.input or {}
        prompt = task_input.get("prompt", "")
        video_duration = task_input.get("video_duration")
        output_dir = task_input.get("output_dir", "output")
        
        if not prompt:
            return TaskStatus(
                state=TaskState.FAILED,
                error="prompt가 제공되지 않았습니다",
                message="Task 입력에 'prompt' 필드가 필요합니다"
            )
        
        # 1. Veo 비디오 생성
        print(f"[ProducerAgent] Veo 비디오 생성 시작...")
        veo_video_path = generate_veo_clip(
            prompt=prompt,
            output_dir=output_dir,
            duration_seconds=int(video_duration) if video_duration else None,
            aspect_ratio="9:16",  # YouTube Shorts 세로형
            resolution="1080p"  # YouTube Shorts 권장 해상도
        )
        
        # 2. Seamless loop 생성
        print(f"[ProducerAgent] Seamless loop 생성 시작...")
        looped_video_path = make_seamless_loop(
            veo_video_path,
            target_duration=video_duration if video_duration else None,
            target_resolution=(1080, 1920)  # YouTube Shorts 규격
        )
        
        return TaskStatus(
            state=TaskState.COMPLETED,
            output={
                "video_path": looped_video_path,
                "original_video_path": veo_video_path,
                "prompt": prompt
            },
            message=f"비디오 생성 완료: {looped_video_path}"
        )
        
    except Exception as e:
        return TaskStatus(
            state=TaskState.FAILED,
            error=str(e),
            message=f"비디오 생성 실패: {str(e)}"
        )


# AgentCard 생성
def create_producer_agent_card(base_url: str = "http://localhost:8003") -> AgentCard:
    """ProducerAgent의 AgentCard 생성"""
    return AgentCard(
        name="ProducerAgent",
        description="Veo API를 사용하여 비디오를 생성하고 seamless loop를 만드는 에이전트",
        url=base_url,
        version="1.0.0",
        protocol_version="0.3.0",
        skills=[
            AgentSkill(
                id="produce",
                name="Video Production",
                description="Veo 프롬프트를 기반으로 비디오를 생성하고 seamless loop를 만듭니다.",
                examples=[
                    "Generate video from prompt",
                    "Create seamless loop video"
                ],
                tags=["production", "video-generation", "veo", "seamless-loop"]
            )
        ],
        preferred_transport=TransportProtocol.HTTP_JSON,
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        supports_authenticated_extended_card=False
    )


# A2A 서버 생성
def create_server(base_url: str = "http://localhost:8003") -> A2AServerBase:
    """ProducerAgent A2A 서버 생성"""
    agent_card = create_producer_agent_card(base_url)
    return A2AServerBase(agent_card, handle_producer_task)


if __name__ == "__main__":
    """서버 실행"""
    import sys
    
    # 환경 변수에서 포트 및 URL 읽기
    port = int(os.getenv("PRODUCER_PORT", "8003"))
    host = os.getenv("PRODUCER_HOST", "0.0.0.0")
    base_url = os.getenv("PRODUCER_URL", f"http://localhost:{port}")
    
    # 서버 생성
    server = create_server(base_url)
    app = server.get_app()
    
    print(f"ProducerAgent A2A 서버 시작: {base_url}")
    print(f"AgentCard: http://{host}:{port}/a2a/agent_card")
    print(f"Tasks: http://{host}:{port}/a2a/tasks")
    
    # 서버 실행
    uvicorn.run(app, host=host, port=port)




