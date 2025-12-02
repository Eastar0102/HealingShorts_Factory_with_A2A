"""
ReviewerAgent: The Gatekeeper
Seamless Loop Healing Shorts의 품질 게이트키퍼
LLM을 사용하여 프롬프트를 의미론적으로 평가합니다.
"""

import json
from typing import Optional
from .base import BaseAgent
from ..models import ReviewResult


class ReviewerAgent(BaseAgent):
    """
    품질 검토 에이전트
    Gemini LLM을 사용하여 프롬프트를 의미론적으로 평가합니다.
    규칙 기반 로직을 사용하지 않고 순수 LLM 이해에 의존합니다.
    """
    
    def __init__(self):
        super().__init__(
            name="ReviewerAgent",
            model_name="gemini-2.5-flash"
        )
        self.system_prompt = """You are a strict quality gatekeeper for "Healing Shorts" video storyboards and prompts.

Your role is to evaluate storyboards/prompts for Google Veo and ensure they meet ALL of the following criteria:

1. THEME (CRITICAL - MUST PASS):
   - The storyboard/prompt must be for Healing, ASMR, Nature, or Relaxing content
   - REJECT any prompts that suggest:
     * Violence, action, or high-energy scenes
     * Fast-paced movement or rapid changes
     * Loud sounds, explosions, or jarring elements
     * Anything that would not be calming or meditative
   - If this criterion fails, you MUST REJECT

2. STORYBOARD FORMAT (CRITICAL - MUST PASS):
   - The output should follow the storyboard format with:
     * **VIDEO SPECIFICATIONS** section (resolution, duration, format)
     * **STORYBOARD** section with scene/sequence breakdowns
     * **OVERALL PROMPT FOR VEO** section (final combined prompt)
   - Each scene should include: Visual Description, Camera, Lighting, Mood
   - If the format is missing or incomplete, you MUST REJECT and specify what's missing

3. TECHNICAL REQUIREMENTS (CRITICAL - MUST PASS):
   - MUST explicitly mention resolution: "1080x1920" or "vertical 9:16 format" or "YouTube Shorts format"
   - MUST specify the exact duration in seconds (e.g., "15 seconds", "30 seconds")
   - If resolution or duration is missing, you MUST REJECT and specify what's missing

4. CAMERA MOVEMENT (FLEXIBLE):
   - Camera movements are ALLOWED (static, slow pan, gentle zoom, dolly, etc.)
   - BUT: All movements must be SLOW, SMOOTH, and CALMING
   - REJECT if movements are described as fast, jarring, or energetic
   - For seamless loops, static camera is preferred but not mandatory
   - If camera movement is too fast/jarring, you MUST REJECT

5. STORYBOARD QUALITY (IMPORTANT):
   - The storyboard should be detailed and professional
   - Should include visual elements, lighting, composition, camera work, and mood
   - Should be specific enough for Veo to generate high-quality video
   - Should have clear scene/sequence descriptions with timing
   - If quality is too low or vague, you should REJECT and specify what needs improvement

6. CONTENT DETAIL (IMPORTANT):
   - Should be highly descriptive with cinematic language
   - Should focus on visual elements that create a calming atmosphere
   - Should avoid fast movements, jarring cuts, or high-energy elements
   - If content is too generic or lacks detail, you should REJECT and specify what needs more detail

EVALUATION PROCESS:
1. Check each criterion systematically
2. If ANY critical criterion (1, 2, 3) fails, you MUST REJECT
3. For flexible criteria (4, 5, 6), evaluate quality and reject if significantly lacking
4. Provide SPECIFIC, ACTIONABLE feedback for each failed criterion
5. If approved, explain why it meets all requirements

You must output your evaluation as a JSON object with the following structure:
{
    "status": "APPROVED" or "REJECTED",
    "feedback": "Detailed explanation of why it was approved or what needs to be changed. Be SPECIFIC about which criteria failed and how to fix them.",
    "score": 0-100 (suitability score - only give high scores (80+) if ALL criteria are met)
}

Be strict but fair. Only approve storyboards/prompts that meet ALL critical criteria and have good quality."""
    
    async def process(self, input_data: str, context: Optional[str] = None) -> str:
        """
        BaseAgent의 추상 메서드 구현
        프롬프트를 평가하고 결과를 JSON 문자열로 반환합니다.
        
        Args:
            input_data: 평가할 Veo 프롬프트
            context: 추가 컨텍스트 (사용하지 않음)
            
        Returns:
            ReviewResult의 JSON 문자열 표현
        """
        review_result = await self.evaluate(input_data)
        # ReviewResult를 JSON 문자열로 변환
        import json
        return json.dumps(review_result.dict(), ensure_ascii=False)
    
    async def evaluate(self, prompt: str, expected_duration: Optional[float] = None) -> ReviewResult:
        """
        프롬프트를 평가하여 ReviewResult를 반환합니다.
        
        Args:
            prompt: 평가할 Veo 프롬프트
            expected_duration: 예상 비디오 길이 (초). None이면 검증하지 않음.
            
        Returns:
            ReviewResult 객체 (status, feedback, score)
        """
        duration_check = ""
        if expected_duration:
            duration_check = f"\n\nIMPORTANT: The video MUST be exactly {int(expected_duration)} seconds long. Verify that the prompt/storyboard explicitly mentions this duration."
        
        evaluation_prompt = f"""{self.system_prompt}{duration_check}

Evaluate this storyboard/prompt:
{prompt}

Check ALL criteria systematically:
1. Is the theme appropriate (Healing/ASMR/Nature/Relaxing)?
2. Does it follow the storyboard format (VIDEO SPECIFICATIONS, STORYBOARD sections, OVERALL PROMPT)?
3. Does it mention 1080x1920 resolution and specify duration?
4. Are camera movements (if any) slow and calming?
5. Is the storyboard detailed and professional?
6. Is the content specific and descriptive enough?

Output your evaluation as JSON only (no additional text):"""
        
        try:
            # Gemini를 사용하여 JSON 형식으로 평가 결과 생성
            response_text = await self._generate_content(
                evaluation_prompt,
                response_mime_type="application/json"
            )
            
            # JSON 파싱
            try:
                result_dict = json.loads(response_text)
            except json.JSONDecodeError:
                # JSON 파싱 실패 시, 텍스트에서 JSON 추출 시도
                # 또는 기본값 사용
                result_dict = {
                    "status": "REJECTED",
                    "feedback": "JSON 파싱 실패. 프롬프트를 다시 검토해주세요.",
                    "score": 0
                }
            
            # ReviewResult 객체 생성
            review_result = ReviewResult(
                status=result_dict.get("status", "REJECTED").upper(),
                feedback=result_dict.get("feedback", "No feedback provided"),
                score=result_dict.get("score", 0)
            )
            
            # status가 APPROVED 또는 REJECTED가 아니면 REJECTED로 설정
            if review_result.status not in ["APPROVED", "REJECTED"]:
                review_result.status = "REJECTED"
                review_result.feedback = f"Invalid status '{review_result.status}'. " + review_result.feedback
            
            return review_result
            
        except Exception as e:
            # 에러 발생 시 안전하게 REJECTED 반환
            return ReviewResult(
                status="REJECTED",
                feedback=f"Reviewer 평가 중 오류 발생: {str(e)}",
                score=0
            )

