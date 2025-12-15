"""
추상 베이스 에이전트 클래스
모든 에이전트가 상속받는 기본 클래스
"""

from abc import ABC, abstractmethod
from typing import Optional
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# Gemini API 키 로드
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


class BaseAgent(ABC):
    """
    모든 A2A 에이전트의 베이스 클래스
    Gemini LLM을 사용하여 의사결정을 내립니다.
    """
    
    def __init__(self, name: str, model_name: str = "gemini-2.5-flash"):
        """
        Args:
            name: 에이전트 이름
            model_name: 사용할 Gemini 모델 이름
        """
        self.name = name
        self.model_name = model_name
        
        if not GEMINI_API_KEY:
            raise ValueError(
                f"{self.name}: GEMINI_API_KEY가 설정되지 않았습니다. "
                ".env 파일에 GEMINI_API_KEY를 설정하세요."
            )
        
        # 새로운 Gemini API 클라이언트 초기화
        self.client = genai.Client(api_key=GEMINI_API_KEY)
    
    @abstractmethod
    async def process(self, input_data: str, context: Optional[str] = None) -> str:
        """
        에이전트의 주요 처리 로직 (서브클래스에서 구현)
        
        Args:
            input_data: 입력 데이터 (프롬프트 또는 피드백)
            context: 추가 컨텍스트 정보
            
        Returns:
            처리 결과 문자열
        """
        pass
    
    def _truncate_prompt(self, prompt: str, max_chars: int = 25000) -> str:
        """
        프롬프트 길이를 제한하여 Gemini API 503 오류를 방지합니다.
        
        Args:
            prompt: 원본 프롬프트
            max_chars: 최대 문자 수 (기본값: 25000자, 약 6000-7000 토큰)
            
        Returns:
            잘린 프롬프트 (필요한 경우)
        """
        if len(prompt) <= max_chars:
            return prompt
        
        # 프롬프트가 너무 길면 자르기
        # 중요한 부분(시작 부분)은 유지하고, 중간/끝 부분을 자름
        truncated = prompt[:max_chars]
        
        # 마지막 문장이 잘리지 않도록 마지막 줄바꿈이나 문장 끝을 찾아서 자름
        last_newline = truncated.rfind('\n')
        last_period = truncated.rfind('.')
        last_cut = max(last_newline, last_period)
        
        if last_cut > max_chars * 0.9:  # 90% 이상이면 그 위치에서 자름
            truncated = truncated[:last_cut + 1]
        
        # 잘렸다는 경고 메시지 추가
        truncated += f"\n\n[Note: 프롬프트가 {len(prompt)}자에서 {len(truncated)}자로 제한되었습니다. 일부 내용이 생략되었을 수 있습니다.]"
        
        return truncated
    
    async def _generate_content(self, prompt: str, response_mime_type: Optional[str] = None) -> str:
        """
        Gemini 모델을 사용하여 콘텐츠 생성 (async)
        FastAPI의 실행 중인 이벤트 루프와 충돌을 방지하기 위해
        동기 버전을 run_in_executor로 실행
        각 스레드에서 독립적인 클라이언트를 생성하여 이벤트 루프 충돌 방지
        
        Args:
            prompt: 프롬프트 텍스트
            response_mime_type: 응답 MIME 타입 (예: "application/json")
            
        Returns:
            생성된 콘텐츠
        """
        import asyncio
        import concurrent.futures
        
        # 프롬프트 길이 제한 적용 (503 오류 방지)
        prompt = self._truncate_prompt(prompt)
        
        # Config 준비
        config = None
        if response_mime_type:
            config = types.GenerateContentConfig(
                response_mime_type=response_mime_type
            )
        
        def _sync_generate():
            """동기 버전의 generate_content를 실행
            각 스레드에서 독립적인 클라이언트를 생성하여 이벤트 루프 충돌 방지
            """
            try:
                # 각 스레드에서 독립적인 클라이언트 생성
                # 이렇게 하면 클라이언트가 내부적으로 이벤트 루프를 사용해도 충돌하지 않음
                thread_client = genai.Client(api_key=GEMINI_API_KEY)
                
                response = thread_client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config
                )
                result = response.text
                
                # 클라이언트 정리
                thread_client.close()
                
                return result
            except Exception as e:
                raise Exception(f"{self.name} 콘텐츠 생성 실패: {str(e)}")
        
        try:
            # 현재 실행 중인 이벤트 루프 가져오기
            loop = asyncio.get_running_loop()
            # 별도 스레드에서 동기 함수 실행
            with concurrent.futures.ThreadPoolExecutor() as executor:
                result = await loop.run_in_executor(executor, _sync_generate)
            return result
        except Exception as e:
            raise Exception(f"{self.name} 콘텐츠 생성 실패: {str(e)}")

