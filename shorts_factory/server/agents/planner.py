"""
PlannerAgent: The Healing Director
ASMR, Nature Landscapes, Meditation 전문 비디오 디렉터
사용자 키워드를 상세한 Google Veo 프롬프트로 변환합니다.
"""

from typing import Optional
from .base import BaseAgent


class PlannerAgent(BaseAgent):
    """
    크리에이티브 디렉터 에이전트
    Healing/ASMR 콘텐츠를 위한 Veo 프롬프트를 생성합니다.
    """
    
    def __init__(self):
        super().__init__(
            name="PlannerAgent",
            model_name="gemini-2.5-flash"
        )
        self.system_prompt = """You are an expert video director and storyboard artist specializing in ASMR, Nature Landscapes, and Meditation content. 
Your mission is to create detailed, cinematic storyboards for Google Veo video generation.

YOUR ROLE:
You are not just writing a simple prompt - you are creating a professional VIDEO STORYBOARD that describes:
- Visual composition and framing
- Camera movements and angles (can be static, slow pan, gentle zoom, dolly, etc.)
- Lighting and atmosphere
- Subject details and actions
- Timing and pacing
- Overall mood and feeling

CRITICAL REQUIREMENTS:
1. Resolution: MUST be "1080x1920" (vertical format, 9:16 aspect ratio) for YouTube Shorts
2. Vibe: Peaceful, cinematic, photorealistic, 4k quality
3. Theme: ONLY Healing, ASMR, Nature, or Relaxing content
4. Duration: Will be specified in the user request (typically 15-60 seconds for YouTube Shorts)
5. Camera Movement: You can use ANY camera movement that fits the mood:
   - Static/Tripod shots (for seamless loops)
   - Slow, gentle pans
   - Subtle zooms (in/out)
   - Slow dolly movements
   - Gentle camera tilts
   - BUT: All movements must be SLOW, SMOOTH, and CALMING

STORYBOARD FORMAT:
Create your storyboard in this structure:

**VIDEO SPECIFICATIONS:**
- Resolution: 1080x1920 (vertical, 9:16)
- Duration: [exact seconds]
- Format: YouTube Shorts

**STORYBOARD:**

[Scene/Sequence 1] (0:00 - 0:XX)
- Visual Description: [detailed description of what we see]
- Camera: [camera position, angle, movement]
- Lighting: [lighting description]
- Mood: [atmospheric feeling]

[Scene/Sequence 2] (0:XX - 0:XX)
- Visual Description: [detailed description]
- Camera: [camera movement and position]
- Lighting: [lighting description]
- Mood: [atmospheric feeling]

[... continue for all sequences ...]

**OVERALL PROMPT FOR VEO:**
[Combine all storyboard elements into a cohesive, detailed prompt that Veo can understand. 
IMPORTANT: Start the prompt with explicit technical specifications:
- "1080x1920 vertical format (9:16 aspect ratio)" or "YouTube Shorts format"
- "Duration: [X] seconds" or "[X] seconds long"
Then describe the visual content in detail.]

GUIDELINES:
- Be highly detailed and descriptive
- Use cinematic language (composition, framing, depth of field, etc.)
- Describe camera movements clearly (if any)
- Focus on visual elements that create a calming atmosphere
- Avoid fast movements, jarring cuts, or high-energy elements
- If creating a seamless loop, ensure the beginning and end can connect smoothly
- Use professional filmmaking terminology

If you receive feedback from the Reviewer, you MUST incorporate that feedback into your new storyboard."""
    
    async def process(self, input_data: str, context: Optional[str] = None, video_duration: Optional[float] = None) -> str:
        """
        사용자 키워드나 피드백을 받아 Veo 프롬프트를 생성합니다.
        
        Args:
            input_data: 사용자 키워드 (예: "Rain") 또는 Reviewer 피드백
            context: 추가 컨텍스트 (이전 프롬프트 등)
            video_duration: 비디오 길이 (초). YouTube Shorts는 15-60초 권장.
            
        Returns:
            생성된 Veo 프롬프트
        """
        # 비디오 길이 정보 준비
        duration_text = ""
        if video_duration:
            duration_text = f"\n\nIMPORTANT: The video MUST be exactly {int(video_duration)} seconds long. Include this duration explicitly in your prompt."
        
        # 피드백이 있는지 확인
        if context and "rejected" in context.lower():
            # Reviewer로부터 거부된 경우, 피드백을 반영하여 재생성
            prompt = f"""{self.system_prompt}{duration_text}

Previous storyboard attempt was rejected. Here's the feedback:
{input_data}

Create a NEW storyboard that addresses all the feedback while maintaining the critical requirements above.
The new storyboard must be different from the previous one and fully compliant with all requirements.
MUST include: 1080x1920 resolution, {int(video_duration) if video_duration else 'specified'} seconds duration.
You can use any camera movement that fits the mood (static, slow pan, gentle zoom, etc.)."""
        else:
            # 새로운 스토리보드 생성
            duration_requirement = f" The video must be exactly {int(video_duration)} seconds long." if video_duration else ""
            prompt = f"""{self.system_prompt}{duration_text}

User request: {input_data}

Create a professional VIDEO STORYBOARD for Google Veo that captures the essence of "{input_data}" as a healing/ASMR video.

Requirements:
- MUST specify "1080x1920 resolution" or "vertical 9:16 format" for YouTube Shorts{duration_requirement}
- Create a detailed storyboard with multiple scenes/sequences
- Describe camera movements (can be static, slow pan, gentle zoom, etc. - choose what fits best)
- Be creative but maintain a calming, peaceful atmosphere
- Use professional filmmaking language

CRITICAL: In the "OVERALL PROMPT FOR VEO" section, you MUST start with:
"1080x1920 vertical format (9:16 aspect ratio), Duration: {int(video_duration) if video_duration else '[specified]'} seconds. [then your visual description]"

This ensures Veo API understands the technical requirements clearly.

Output your storyboard in the format specified above, then provide the final combined prompt for Veo."""
        
        # Gemini를 사용하여 프롬프트 생성
        generated_prompt = await self._generate_content(prompt)
        
        # 생성된 프롬프트가 Static Camera를 포함하는지 확인 (기본 검증)
        # 하지만 실제 검증은 Reviewer가 LLM으로 수행
        return generated_prompt.strip()
    
    async def generate_youtube_metadata(self, storyboard: str, topic: str) -> dict:
        """
        스토리보드를 기반으로 YouTube 메타데이터(제목, 설명, 태그)를 생성합니다.
        
        Args:
            storyboard: 승인된 스토리보드/프롬프트
            topic: 원본 사용자 요청 키워드
            
        Returns:
            YouTube 메타데이터 딕셔너리 (title, description, tags)
        """
        import json
        
        metadata_prompt = f"""You are a YouTube content strategist specializing in Healing, ASMR, and Meditation videos.

Based on this video storyboard/prompt, create engaging YouTube metadata:

STORYBOARD/PROMPT:
{storyboard}

ORIGINAL TOPIC: {topic}

Create YouTube metadata (title, description, tags) that:
1. Is engaging and SEO-friendly
2. Accurately describes the video content
3. Uses relevant keywords for healing/ASMR/meditation content
4. Is appropriate for YouTube Shorts format
5. Includes relevant hashtags in the description

Output your response as JSON only (no additional text):
{{
    "title": "Engaging YouTube title (max 100 characters, no emojis)",
    "description": "Detailed YouTube description (2-3 paragraphs, include relevant keywords and hashtags)",
    "tags": ["tag1", "tag2", "tag3", ...] (5-10 relevant tags)
}}

Tags should be relevant to: healing, ASMR, meditation, relaxation, nature, etc."""

        try:
            # Gemini를 사용하여 JSON 형식으로 메타데이터 생성
            response_text = await self._generate_content(
                metadata_prompt,
                response_mime_type="application/json"
            )
            
            # JSON 파싱
            try:
                metadata_dict = json.loads(response_text)
            except json.JSONDecodeError:
                # JSON 파싱 실패 시 기본값 사용
                metadata_dict = {
                    "title": f"Healing {topic} - Relaxing ASMR Video",
                    "description": f"Experience the calming atmosphere of {topic}. Perfect for meditation, relaxation, and ASMR. #healing #asmr #meditation #relaxation",
                    "tags": ["healing", "asmr", "meditation", "relaxation", topic.lower()]
                }
            
            return metadata_dict
            
        except Exception as e:
            # 에러 발생 시 기본값 반환
            return {
                "title": f"Healing {topic} - Relaxing ASMR Video",
                "description": f"Experience the calming atmosphere of {topic}. Perfect for meditation, relaxation, and ASMR. #healing #asmr #meditation #relaxation",
                "tags": ["healing", "asmr", "meditation", "relaxation", topic.lower()]
            }

