"""
UploaderAgent A2A 서버
포트 8004에서 실행되는 독립적인 A2A 에이전트 서버
"""

import uvicorn
import os
from typing import Dict, Any
from ..a2a_server import A2AServerBase
from ..models import AgentCard, AgentSkill, Task, TaskStatus, TaskState, TransportProtocol, AgentCapabilities, YouTubeMetadata
from .uploader import UploaderAgent


# UploaderAgent 인스턴스 생성
uploader_agent = UploaderAgent()


async def handle_uploader_task(task: Task) -> TaskStatus:
    """
    Uploader Task 처리 함수
    
    Args:
        task: A2A Task 객체
    
    Returns:
        TaskStatus 객체
    """
    import asyncio
    
    try:
        # Task 입력에서 데이터 추출
        task_input = task.input or {}
        video_path = task_input.get("video_path", "")
        youtube_metadata = task_input.get("youtube_metadata")
        title = task_input.get("title")
        description = task_input.get("description")
        tags = task_input.get("tags")
        privacy_status = task_input.get("privacy_status", "public")
        
        if not video_path:
            return TaskStatus(
                state=TaskState.FAILED,
                error="video_path가 제공되지 않았습니다",
                message="Task 입력에 'video_path' 필드가 필요합니다"
            )
        
        # YouTubeMetadata 객체 생성 (있는 경우)
        youtube_metadata_obj = None
        if youtube_metadata:
            youtube_metadata_obj = YouTubeMetadata(**youtube_metadata)
        
        # UploaderAgent의 process 메서드 호출
        # 이제 async 함수이므로 직접 await 가능
        result = await uploader_agent.process(
            video_path=video_path,
            youtube_metadata=youtube_metadata_obj,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status
        )
        
        if result.get("success"):
            return TaskStatus(
                state=TaskState.COMPLETED,
                output={
                    "youtube_url": result.get("youtube_url"),
                    "video_path": video_path,
                    "message": result.get("message")
                },
                message=result.get("message", "YouTube 업로드 완료")
            )
        else:
            return TaskStatus(
                state=TaskState.FAILED,
                error=result.get("message", "업로드 실패"),
                message=result.get("message", "YouTube 업로드 실패")
            )
        
    except Exception as e:
        return TaskStatus(
            state=TaskState.FAILED,
            error=str(e),
            message=f"YouTube 업로드 실패: {str(e)}"
        )


# AgentCard 생성
def create_uploader_agent_card(base_url: str = "http://localhost:8004") -> AgentCard:
    """UploaderAgent의 AgentCard 생성"""
    return AgentCard(
        name="UploaderAgent",
        description="비디오 파일을 YouTube Shorts에 업로드하는 에이전트",
        url=base_url,
        version="1.0.0",
        protocol_version="0.3.0",
        skills=[
            AgentSkill(
                id="upload",
                name="YouTube Upload",
                description="비디오 파일을 YouTube Shorts에 업로드하고 메타데이터를 설정합니다.",
                examples=[
                    "Upload video to YouTube",
                    "Publish healing video"
                ],
                tags=["upload", "youtube", "publishing", "shorts"]
            )
        ],
        preferred_transport=TransportProtocol.HTTP_JSON,
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        supports_authenticated_extended_card=False
    )


# A2A 서버 생성
def create_server(base_url: str = "http://localhost:8004") -> A2AServerBase:
    """UploaderAgent A2A 서버 생성"""
    agent_card = create_uploader_agent_card(base_url)
    return A2AServerBase(agent_card, handle_uploader_task)


if __name__ == "__main__":
    """서버 실행"""
    import sys
    
    # 환경 변수에서 포트 및 URL 읽기
    port = int(os.getenv("UPLOADER_PORT", "8004"))
    host = os.getenv("UPLOADER_HOST", "0.0.0.0")
    base_url = os.getenv("UPLOADER_URL", f"http://localhost:{port}")
    
    # 서버 생성
    server = create_server(base_url)
    app = server.get_app()
    
    print(f"UploaderAgent A2A 서버 시작: {base_url}")
    print(f"AgentCard: http://{host}:{port}/a2a/agent_card")
    print(f"Tasks: http://{host}:{port}/a2a/tasks")
    
    # 서버 실행
    uvicorn.run(app, host=host, port=port)

