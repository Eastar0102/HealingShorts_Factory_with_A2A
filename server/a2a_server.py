"""
A2A 프로토콜 서버 베이스 클래스
모든 A2A 에이전트 서버가 상속받는 기본 클래스
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from typing import Dict, Any, Optional, Callable, Union, Awaitable
from .models import AgentCard, Task, TaskStatus, TaskState


class A2AServerBase:
    """
    A2A 프로토콜 서버 베이스 클래스
    모든 A2A 에이전트 서버가 상속받아 사용합니다.
    """
    
    def __init__(
        self,
        agent_card: AgentCard,
        task_handler: Union[Callable[[Task], TaskStatus], Callable[[Task], Awaitable[TaskStatus]]]
    ):
        """
        Args:
            agent_card: 에이전트의 AgentCard
            task_handler: Task를 처리하는 함수
        """
        self.agent_card = agent_card
        self.task_handler = task_handler
        self.app = FastAPI(
            title=f"{agent_card.name} - A2A Agent",
            description=agent_card.description,
            version=agent_card.version
        )
        self._setup_routes()
    
    def _setup_routes(self):
        """A2A 표준 엔드포인트 설정"""
        
        @self.app.get("/a2a/agent_card")
        async def get_agent_card():
            """A2A 표준: AgentCard 반환"""
            return self.agent_card.model_dump()
        
        @self.app.post("/a2a/tasks")
        async def handle_task(task: Task):
            """A2A 표준: Task 처리"""
            import asyncio
            import inspect
            
            try:
                # Task 처리
                # task_handler가 async인지 확인
                if inspect.iscoroutinefunction(self.task_handler):
                    result = await self.task_handler(task)
                else:
                    # 동기 함수인 경우, 이미 실행 중인 이벤트 루프가 있으면
                    # 별도 스레드에서 실행
                    try:
                        loop = asyncio.get_running_loop()
                        # 실행 중인 루프가 있으면 run_in_executor 사용
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            result = await loop.run_in_executor(executor, self.task_handler, task)
                    except RuntimeError:
                        # 실행 중인 루프가 없으면 직접 호출
                        result = self.task_handler(task)
                
                return result.model_dump()
            except Exception as e:
                # 에러 발생 시 FAILED 상태 반환
                error_status = TaskStatus(
                    state=TaskState.FAILED,
                    error=str(e),
                    message=f"Task 처리 중 오류 발생: {str(e)}"
                )
                return error_status.model_dump()
        
        @self.app.get("/health")
        async def health_check():
            """헬스 체크 엔드포인트"""
            return {"status": "healthy", "agent": self.agent_card.name}
    
    def get_app(self) -> FastAPI:
        """FastAPI 앱 반환"""
        return self.app

