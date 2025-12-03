"""
에이전트 테스트 스크립트
각 에이전트가 제대로 작동하는지 확인합니다.
"""

import asyncio
import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from server.agents.planner import PlannerAgent
from server.agents.reviewer import ReviewerAgent


async def test_planner_agent():
    """PlannerAgent 테스트"""
    print("\n" + "=" * 60)
    print("[TEST] PlannerAgent 테스트")
    print("=" * 60)
    
    try:
        agent = PlannerAgent()
        print(f"[OK] PlannerAgent 초기화 성공")
        print(f"   - Model: {agent.model_name}")
        print(f"   - Client type: {type(agent.client)}")
        print(f"   - Has aio: {hasattr(agent.client, 'aio')}")
        
        # 간단한 프롬프트 생성 테스트
        print("\n[TEST] 프롬프트 생성 테스트...")
        prompt = await agent.process(
            input_data="Rain",
            video_duration=30.0
        )
        
        print(f"[OK] 프롬프트 생성 성공!")
        print(f"   - 길이: {len(prompt)} 문자")
        print(f"   - 첫 200자: {prompt[:200]}...")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] PlannerAgent 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_reviewer_agent():
    """ReviewerAgent 테스트"""
    print("\n" + "=" * 60)
    print("[TEST] ReviewerAgent 테스트")
    print("=" * 60)
    
    try:
        agent = ReviewerAgent()
        print(f"[OK] ReviewerAgent 초기화 성공")
        print(f"   - Model: {agent.model_name}")
        
        # 간단한 프롬프트 평가 테스트
        test_prompt = """
        **VIDEO SPECIFICATIONS:**
        - Resolution: 1080x1920 (vertical, 9:16)
        - Duration: 30 seconds
        - Format: YouTube Shorts
        
        **STORYBOARD:**
        [Scene 1] (0:00 - 0:30)
        - Visual Description: Gentle rain falling on green leaves
        - Camera: Static, close-up
        - Lighting: Soft, natural daylight
        - Mood: Calming, peaceful
        
        **OVERALL PROMPT FOR VEO:**
        1080x1920 vertical format (9:16 aspect ratio), Duration: 30 seconds. Gentle rain falling on green leaves, static camera, soft natural lighting, calming and peaceful atmosphere.
        """
        
        print("\n[TEST] 프롬프트 평가 테스트...")
        review_result = await agent.evaluate(
            prompt=test_prompt,
            expected_duration=30.0
        )
        
        print(f"[OK] 프롬프트 평가 성공!")
        print(f"   - Status: {review_result.status}")
        print(f"   - Score: {review_result.score}")
        print(f"   - Feedback: {review_result.feedback[:200]}...")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] ReviewerAgent 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_a2a_server_integration():
    """A2A 서버 통합 테스트"""
    print("\n" + "=" * 60)
    print("[TEST] A2A 서버 통합 테스트")
    print("=" * 60)
    
    try:
        from server.agents.planner_server import handle_planner_task
        from server.models import Task, TaskState
        
        print("[TEST] PlannerAgent 서버 task_handler 테스트...")
        
        task = Task(
            skill="plan",
            input={
                "topic": "Ocean Waves",
                "video_duration": 30.0
            }
        )
        
        result = await handle_planner_task(task)
        
        if result.state == TaskState.COMPLETED:
            print(f"[OK] Task 처리 성공!")
            print(f"   - State: {result.state}")
            print(f"   - Output keys: {list(result.output.keys()) if result.output else None}")
            if result.output and "prompt" in result.output:
                prompt = result.output["prompt"]
                print(f"   - Prompt length: {len(prompt)} 문자")
        else:
            print(f"[FAIL] Task 처리 실패: {result.error or result.message}")
            return False
        
        return True
        
    except Exception as e:
        print(f"[FAIL] A2A 서버 통합 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """모든 테스트 실행"""
    print("\n" + "=" * 60)
    print("[START] 에이전트 테스트 시작")
    print("=" * 60)
    
    # GEMINI_API_KEY 확인
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[FAIL] GEMINI_API_KEY가 설정되지 않았습니다!")
        print("   .env 파일에 GEMINI_API_KEY를 설정하세요.")
        return
    
    print(f"[OK] GEMINI_API_KEY 확인됨 (길이: {len(api_key)} 문자)")
    
    results = []
    
    # 1. PlannerAgent 테스트
    results.append(await test_planner_agent())
    
    # 2. ReviewerAgent 테스트
    results.append(await test_reviewer_agent())
    
    # 3. A2A 서버 통합 테스트
    results.append(await test_a2a_server_integration())
    
    # 결과 요약
    print("\n" + "=" * 60)
    print("[SUMMARY] 테스트 결과 요약")
    print("=" * 60)
    
    test_names = ["PlannerAgent", "ReviewerAgent", "A2A 서버 통합"]
    for name, result in zip(test_names, results):
        status = "[PASS] 통과" if result else "[FAIL] 실패"
        print(f"  {status} - {name}")
    
    total_passed = sum(results)
    total_tests = len(results)
    
    print(f"\n총 {total_tests}개 테스트 중 {total_passed}개 통과")
    
    if all(results):
        print("\n[SUCCESS] 모든 테스트 통과!")
    else:
        print("\n[WARNING] 일부 테스트 실패")


if __name__ == "__main__":
    asyncio.run(main())

