"""
A2A 워크플로우 오케스트레이터.
Planner / Reviewer 에이전트를 사용해 프롬프트를 반복 개선합니다.
"""

import os
from typing import Dict, List, Optional

from .a2a_client import A2AClient
from .agents.planner import PlannerAgent
from .models import AgentMessage, ReviewResult, Task, TaskState, YouTubeMetadata


class Orchestrator:
    """A2A 워크플로우 오케스트레이터."""

    def __init__(
        self,
        planner_url: Optional[str] = None,
        reviewer_url: Optional[str] = None,
        producer_url: Optional[str] = None,
        uploader_url: Optional[str] = None,
    ) -> None:
        # 환경 변수 또는 기본값으로 에이전트 URL 설정
        self.planner_url = planner_url or os.getenv(
            "PLANNER_AGENT_URL", "http://localhost:8001"
        )
        self.reviewer_url = reviewer_url or os.getenv(
            "REVIEWER_AGENT_URL", "http://localhost:8002"
        )
        self.producer_url = producer_url or os.getenv(
            "PRODUCER_AGENT_URL", "http://localhost:8003"
        )
        self.uploader_url = uploader_url or os.getenv(
            "UPLOADER_AGENT_URL", "http://localhost:8004"
        )

        self.max_iterations = 5
        # YouTube 메타데이터 생성을 위한 직접 PlannerAgent
        self.planner_for_metadata = PlannerAgent()

    async def run_a2a_workflow(
        self,
        user_topic: str,
        video_duration: Optional[float] = None,
        max_iterations: Optional[int] = None,
    ) -> Dict:
        """
        Planner / Reviewer 에이전트를 사용해 프롬프트를 반복 개선합니다.
        """
        if max_iterations is None:
            max_iterations = self.max_iterations

        conversation_log: List[Dict] = []
        current_prompt = user_topic
        attempts = 0
        approved_prompt: Optional[str] = None
        youtube_metadata: Optional[YouTubeMetadata] = None
        final_score = 0

        # Planner / Reviewer A2A 클라이언트 생성
        async with A2AClient(self.planner_url) as planner_client, A2AClient(
            self.reviewer_url
        ) as reviewer_client:
            while attempts < max_iterations:
                attempts += 1

                # 1) Planner 호출
                try:
                    task_input = {
                        "topic": user_topic if attempts == 1 else current_prompt,
                        "video_duration": video_duration,
                        "context": (
                            "Previous prompt was rejected by Reviewer. "
                            "Incorporate the feedback."
                            if attempts > 1
                            else None
                        ),
                        "feedback": current_prompt if attempts > 1 else None,
                    }

                    planner_task = Task(skill="plan", input=task_input)
                    planner_result = await planner_client.execute_task(planner_task)

                    if planner_result.state != TaskState.COMPLETED:
                        conversation_log.append(
                            {
                                "iteration": attempts,
                                "agent": "PlannerAgent",
                                "action": "error",
                                "error": planner_result.error
                                or planner_result.message,
                            }
                        )
                        return {
                            "success": False,
                            "approved_prompt": None,
                            "youtube_metadata": None,
                            "conversation_log": conversation_log,
                            "iterations": attempts,
                            "final_score": 0,
                            "error": f"Planner 오류: {planner_result.error or planner_result.message}",
                        }

                    generated_prompt = planner_result.output.get("prompt", "")

                    msg_to_reviewer = AgentMessage(
                        sender="PlannerAgent",
                        receiver="ReviewerAgent",
                        content=generated_prompt,
                        iteration=attempts,
                    )

                    conversation_log.append(
                        {
                            "iteration": attempts,
                            "agent": "PlannerAgent",
                            "action": "generate",
                            "message": msg_to_reviewer.model_dump(),
                            "output": generated_prompt,
                        }
                    )
                except Exception as e:
                    conversation_log.append(
                        {
                            "iteration": attempts,
                            "agent": "PlannerAgent",
                            "action": "error",
                            "error": str(e),
                        }
                    )
                    return {
                        "success": False,
                        "approved_prompt": None,
                        "youtube_metadata": None,
                        "conversation_log": conversation_log,
                        "iterations": attempts,
                        "final_score": 0,
                        "error": f"Planner 오류: {str(e)}",
                    }

                # 2) Reviewer 호출
                try:
                    reviewer_task = Task(
                        skill="review",
                        input={
                            "prompt": generated_prompt,
                            "expected_duration": video_duration,
                        },
                    )
                    reviewer_result = await reviewer_client.execute_task(
                        reviewer_task
                    )

                    if reviewer_result.state != TaskState.COMPLETED:
                        conversation_log.append(
                            {
                                "iteration": attempts,
                                "agent": "ReviewerAgent",
                                "action": "error",
                                "error": reviewer_result.error
                                or reviewer_result.message,
                            }
                        )
                        return {
                            "success": False,
                            "approved_prompt": None,
                            "youtube_metadata": None,
                            "conversation_log": conversation_log,
                            "iterations": attempts,
                            "final_score": 0,
                            "error": f"Reviewer 오류: {reviewer_result.error or reviewer_result.message}",
                        }

                    review_output = reviewer_result.output or {}
                    review_result = ReviewResult(
                        status=review_output.get("status", "REJECTED"),
                        feedback=review_output.get("feedback", ""),
                        score=review_output.get("score", 0),
                    )

                    conversation_log.append(
                        {
                            "iteration": attempts,
                            "agent": "ReviewerAgent",
                            "action": "review",
                            "message": {
                                "sender": "ReviewerAgent",
                                "receiver": "PlannerAgent",
                                "content": review_result.feedback,
                                "iteration": attempts,
                            },
                            "output": review_result.model_dump(),
                        }
                    )

                    if review_result.status == "APPROVED":
                        approved_prompt = generated_prompt
                        final_score = review_result.score

                        # 승인된 경우 YouTube 메타데이터 생성
                        try:
                            metadata_dict = (
                                await self.planner_for_metadata.generate_youtube_metadata(
                                    approved_prompt, user_topic
                                )
                            )
                            youtube_metadata = YouTubeMetadata(**metadata_dict)
                        except Exception:
                            # 실패 시 기본값
                            youtube_metadata = YouTubeMetadata(
                                title=f"Healing {user_topic} - Relaxing ASMR Video",
                                description=(
                                    f"Experience the calming atmosphere of {user_topic}. "
                                    "Perfect for meditation, relaxation, and ASMR."
                                ),
                                tags=[
                                    "healing",
                                    "asmr",
                                    "meditation",
                                    "relaxation",
                                    user_topic.lower(),
                                ],
                            )

                        break

                    # 거부된 경우 피드백 기반으로 프롬프트 업데이트
                    current_prompt = (
                        "Previous storyboard was REJECTED by Reviewer.\n\n"
                        f"REJECTION REASON:\n{review_result.feedback}\n\n"
                        f"ORIGINAL REQUEST: {user_topic}\n"
                        f"REQUIRED DURATION: {int(video_duration) if video_duration else 'Not specified'} seconds\n\n"
                        "You MUST create a NEW storyboard that fixes all issues and keeps the healing/ASMR style."
                    )
                except Exception as e:
                    conversation_log.append(
                        {
                            "iteration": attempts,
                            "agent": "ReviewerAgent",
                            "action": "error",
                            "error": str(e),
                        }
                    )
                    return {
                        "success": False,
                        "approved_prompt": None,
                        "youtube_metadata": None,
                        "conversation_log": conversation_log,
                        "iterations": attempts,
                        "final_score": 0,
                        "error": f"Reviewer 오류: {str(e)}",
                    }

        # 최대 반복 후에도 승인 실패
        if approved_prompt is None:
            return {
                "success": False,
                "approved_prompt": None,
                "youtube_metadata": None,
                "conversation_log": conversation_log,
                "iterations": attempts,
                "final_score": 0,
                "error": f"최대 반복 횟수({max_iterations})에 도달했지만 승인된 프롬프트를 생성하지 못했습니다.",
            }

        return {
            "success": True,
            "approved_prompt": approved_prompt,
            "youtube_metadata": youtube_metadata,
            "conversation_log": conversation_log,
            "iterations": attempts,
            "final_score": final_score,
        }


