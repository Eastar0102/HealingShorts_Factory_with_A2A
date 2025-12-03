"""
A2A 프로토콜 클라이언트 유틸리티
다른 A2A 에이전트와 통신하기 위한 클라이언트
"""

import httpx
from typing import Dict, Any, Optional
from .models import AgentCard, Task, TaskStatus, TaskState


class A2AClient:
    """
    A2A 프로토콜 클라이언트
    다른 A2A 에이전트와 통신합니다.
    """
    
    def __init__(self, agent_url: str, timeout: int = 300):
        """
        Args:
            agent_url: 에이전트의 기본 URL (예: "http://localhost:8001")
            timeout: 요청 타임아웃 (초)
        """
        self.agent_url = agent_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def get_agent_card(self) -> AgentCard:
        """
        에이전트의 AgentCard를 조회합니다.
        
        Returns:
            AgentCard 객체
        
        Raises:
            httpx.HTTPError: HTTP 요청 실패 시
        """
        try:
            response = await self.client.get(f"{self.agent_url}/a2a/agent_card")
            response.raise_for_status()
            return AgentCard(**response.json())
        except httpx.HTTPError as e:
            raise Exception(f"AgentCard 조회 실패 ({self.agent_url}): {str(e)}")
    
    async def execute_task(self, task: Task) -> TaskStatus:
        """
        에이전트에 Task를 전송하고 결과를 받습니다.
        
        Args:
            task: 실행할 Task
        
        Returns:
            TaskStatus 객체
        
        Raises:
            httpx.HTTPError: HTTP 요청 실패 시
        """
        try:
            response = await self.client.post(
                f"{self.agent_url}/a2a/tasks",
                json=task.model_dump(exclude_none=True)
            )
            response.raise_for_status()
            return TaskStatus(**response.json())
        except httpx.HTTPError as e:
            # HTTP 에러 시 FAILED 상태 반환
            return TaskStatus(
                state=TaskState.FAILED,
                error=f"HTTP 요청 실패: {str(e)}",
                message=f"에이전트 통신 실패 ({self.agent_url})"
            )
        except Exception as e:
            return TaskStatus(
                state=TaskState.FAILED,
                error=str(e),
                message=f"Task 실행 중 오류 발생: {str(e)}"
            )
    
    async def health_check(self) -> bool:
        """
        에이전트의 헬스 체크를 수행합니다.
        
        Returns:
            에이전트가 정상이면 True
        """
        try:
            response = await self.client.get(f"{self.agent_url}/health", timeout=5)
            response.raise_for_status()
            return True
        except:
            return False
    
    async def close(self):
        """클라이언트 연결 종료"""
        await self.client.aclose()
    
    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료"""
        await self.close()




