"""
Uploader 에이전트
YouTube 업로드를 담당하는 A2A 에이전트
메타데이터 검증 및 업로드 전 최종 검토를 수행합니다.
"""

from typing import Optional, Dict
from .base import BaseAgent
from ..models import AgentMessage, YouTubeMetadata
from ..tools import upload_youtube_shorts
import os


class UploaderAgent(BaseAgent):
    """
    YouTube 업로드 에이전트
    비디오 파일과 메타데이터를 검증하고 YouTube에 업로드합니다.
    """
    
    def __init__(self):
        super().__init__(
            name="UploaderAgent",
            model_name="gemini-2.5-flash"
        )
    
    async def process(
        self,
        video_path: str,
        youtube_metadata: Optional[YouTubeMetadata] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list] = None,
        privacy_status: str = "unlisted"
    ) -> Dict:
        """
        비디오 파일을 YouTube에 업로드합니다.
        
        Args:
            video_path: 업로드할 비디오 파일 경로
            youtube_metadata: Gemini가 생성한 YouTube 메타데이터 (우선순위 높음)
            title: 사용자가 직접 입력한 제목 (youtube_metadata가 없을 때 사용)
            description: 사용자가 직접 입력한 설명 (youtube_metadata가 없을 때 사용)
            tags: 사용자가 직접 입력한 태그 (youtube_metadata가 없을 때 사용)
            privacy_status: 공개 설정 (public, unlisted, private)
            
        Returns:
            {
                "success": bool,
                "youtube_url": str,
                "message": str
            }
        """
        # 1. 비디오 파일 존재 여부 확인
        if not os.path.exists(video_path):
            return {
                "success": False,
                "youtube_url": None,
                "message": f"비디오 파일을 찾을 수 없습니다: {video_path}"
            }
        
        # 2. 메타데이터 검증 및 최종 결정
        final_title = None
        final_description = None
        final_tags = None
        
        # 우선순위: youtube_metadata > 사용자 입력 > 기본값
        if youtube_metadata:
            final_title = youtube_metadata.title
            final_description = youtube_metadata.description
            final_tags = youtube_metadata.tags
            print(f"[UploaderAgent] Gemini가 생성한 메타데이터 사용")
        elif title or description or tags:
            final_title = title
            final_description = description
            final_tags = tags
            print(f"[UploaderAgent] 사용자가 입력한 메타데이터 사용")
        else:
            # 기본값 생성
            final_title = "Healing Shorts - Auto Generated"
            final_description = "Auto-generated healing video for relaxation and ASMR"
            final_tags = ["healing", "asmr", "relaxing", "meditation"]
            print(f"[UploaderAgent] 기본 메타데이터 사용")
        
        # 3. 메타데이터 최종 검증 (Gemini를 통한 검토)
        try:
            validation_result = await self._validate_metadata(
                final_title,
                final_description,
                final_tags
            )
            
            if not validation_result["valid"]:
                print(f"[UploaderAgent] 메타데이터 검증 실패: {validation_result['feedback']}")
                # 검증 실패 시에도 업로드는 진행 (경고만 표시)
        except Exception as e:
            print(f"[UploaderAgent] 메타데이터 검증 중 오류 발생 (업로드는 계속 진행): {str(e)}")
        
        # 4. YouTube 업로드 실행
        try:
            print(f"[UploaderAgent] YouTube 업로드 시작: {video_path}")
            youtube_url = upload_youtube_shorts(
                file_path=video_path,
                title=final_title,
                description=final_description,
                tags=final_tags,
                privacy_status=privacy_status
            )
            
            return {
                "success": True,
                "youtube_url": youtube_url,
                "message": f"YouTube 업로드 완료: {youtube_url}"
            }
        except Exception as e:
            return {
                "success": False,
                "youtube_url": None,
                "message": f"YouTube 업로드 실패: {str(e)}"
            }
    
    async def _validate_metadata(
        self,
        title: str,
        description: str,
        tags: list
    ) -> Dict:
        """
        Gemini를 사용하여 YouTube 메타데이터를 검증합니다.
        
        Args:
            title: 비디오 제목
            description: 비디오 설명
            tags: 비디오 태그 리스트
            
        Returns:
            {
                "valid": bool,
                "feedback": str,
                "suggestions": Optional[Dict]
            }
        """
        prompt = f"""You are a YouTube metadata validator. Review the following metadata for a healing/ASMR video and provide feedback.

TITLE: {title}
DESCRIPTION: {description}
TAGS: {', '.join(tags)}

Please validate:
1. Title is appropriate for YouTube (not too long, engaging, SEO-friendly)
2. Description is informative and follows YouTube best practices
3. Tags are relevant and help with discoverability
4. Content is appropriate for healing/ASMR/relaxation theme

Respond in JSON format:
{{
    "valid": true/false,
    "feedback": "Brief feedback on the metadata quality",
    "suggestions": {{
        "title": "Optional improved title",
        "description": "Optional improved description",
        "tags": ["optional", "improved", "tags"]
    }}
}}"""

        try:
            response_text = await self._generate_content(prompt, response_mime_type="application/json")
            
            # JSON 파싱
            import json
            result = json.loads(response_text)
            
            return {
                "valid": result.get("valid", True),
                "feedback": result.get("feedback", ""),
                "suggestions": result.get("suggestions")
            }
        except Exception as e:
            # 검증 실패 시 기본값 반환 (업로드는 계속 진행)
            return {
                "valid": True,
                "feedback": f"메타데이터 검증 중 오류 발생: {str(e)}",
                "suggestions": None
            }


