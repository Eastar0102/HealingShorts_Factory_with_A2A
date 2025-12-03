"""
FastMCP 클라이언트 브리지
Cursor IDE와 A2A 서버 간의 통신을 담당합니다.
"""

import requests
from mcp.server.fastmcp import FastMCP
from typing import Dict, Any

# A2A 서버 엔드포인트
A2A_SERVER_URL = "http://localhost:8000"

# FastMCP 인스턴스 초기화
mcp = FastMCP("A2A Healing Shorts Factory Bridge")


def _call_a2a_server(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    A2A 서버에 HTTP 요청을 전송합니다.
    
    Args:
        endpoint: API 엔드포인트 경로
        payload: 요청 페이로드
        
    Returns:
        서버 응답
    """
    url = f"{A2A_SERVER_URL}{endpoint}"
    
    try:
        # YouTube 업로드 포함 시 더 긴 타임아웃 (최대 15분)
        timeout = 900 if payload.get("upload_to_youtube", False) else 300
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        return {
            "error": "A2A 서버에 연결할 수 없습니다.",
            "message": f"서버가 실행 중인지 확인하세요: {A2A_SERVER_URL}",
            "hint": "server/main.py를 실행하여 서버를 시작하세요."
        }
    except requests.exceptions.Timeout:
        return {
            "error": "요청 시간 초과",
            "message": "A2A 서버의 응답이 너무 오래 걸렸습니다."
        }
    except requests.exceptions.HTTPError as e:
        return {
            "error": f"HTTP 오류: {e.response.status_code}",
            "message": str(e),
            "response": e.response.text if hasattr(e, "response") else None
        }
    except Exception as e:
        return {
            "error": "예상치 못한 오류",
            "message": str(e)
        }


@mcp.tool()
def create_healing_short(
    topic: str,
    video_duration: float = 30.0,
    upload_to_youtube: bool = False,
    youtube_title: str = None,
    youtube_description: str = None,
    youtube_tags: str = None
) -> Dict[str, Any]:
    """
    Healing Shorts를 생성합니다.
    
    A2A 워크플로우를 실행하여 Planner와 Reviewer가 협업하여 승인된 프롬프트를 생성하고,
    비디오를 생성합니다.
    
    Args:
        topic: 비디오 주제 키워드 (예: "Rain", "Ocean Waves", "Forest")
        video_duration: 비디오 길이 (초). YouTube Shorts는 1초 이상 가능. 기본값: 30초
        upload_to_youtube: YouTube에 업로드할지 여부
        youtube_title: YouTube 비디오 제목 (선택사항)
        youtube_description: YouTube 비디오 설명 (선택사항)
        youtube_tags: YouTube 비디오 태그 (쉼표로 구분된 문자열, 선택사항)
        
    Returns:
        워크플로우 실행 결과 및 에이전트 대화 로그
    """
    # 비디오 길이 최소값 검증 (1초 이상)
    if video_duration < 1:
        return {
            "error": "비디오 길이 오류",
            "message": "비디오 길이는 최소 1초 이상이어야 합니다."
        }
    
    # 태그 문자열을 리스트로 변환
    tags_list = None
    if youtube_tags:
        tags_list = [tag.strip() for tag in youtube_tags.split(",")]
    
    # A2A 서버에 요청 전송
    payload = {
        "topic": topic,
        "video_duration": video_duration,
        "upload_to_youtube": upload_to_youtube,
        "youtube_title": youtube_title,
        "youtube_description": youtube_description,
        "youtube_tags": tags_list
    }
    
    # YouTube 업로드가 요청된 경우 동기 엔드포인트 사용 (완료될 때까지 기다림)
    endpoint = "/v1/create_shorts_sync" if upload_to_youtube else "/v1/create_shorts"
    result = _call_a2a_server(endpoint, payload)
    
    # 에이전트 대화 로그 포맷팅
    if "conversation_log" in result:
        formatted_log = []
        for entry in result["conversation_log"]:
            agent_name = entry.get("agent", "Unknown")
            action = entry.get("action", "unknown")
            iteration = entry.get("iteration", 0)
            
            if action == "generate":
                formatted_log.append({
                    "iteration": iteration,
                    "agent": agent_name,
                    "action": "프롬프트 생성",
                    "output": entry.get("output", "")
                })
            elif action == "review":
                review_output = entry.get("output", {})
                formatted_log.append({
                    "iteration": iteration,
                    "agent": agent_name,
                    "action": "프롬프트 검토",
                    "status": review_output.get("status", "UNKNOWN"),
                    "score": review_output.get("score", 0),
                    "feedback": review_output.get("feedback", "")
                })
            elif action == "error":
                formatted_log.append({
                    "iteration": iteration,
                    "agent": agent_name,
                    "action": "오류",
                    "error": entry.get("error", "Unknown error")
                })
        
        result["formatted_conversation_log"] = formatted_log
    
    return result


@mcp.tool()
def upload_video_to_youtube(
    video_path: str,
    title: str = None,
    description: str = None,
    tags: str = None,
    privacy_status: str = "public"
) -> Dict[str, Any]:
    """
    이미 생성된 비디오 파일을 YouTube에 업로드합니다.
    
    Args:
        video_path: 업로드할 비디오 파일 경로 (예: "output/seamless_loop_1234567890.mp4")
        title: YouTube 비디오 제목 (선택사항, 기본값: "Healing Shorts - Auto Generated")
        description: YouTube 비디오 설명 (선택사항)
        tags: YouTube 비디오 태그 (쉼표로 구분된 문자열, 선택사항)
        privacy_status: 공개 설정 (public, unlisted, private). 기본값: unlisted
        
    Returns:
        업로드된 YouTube 비디오 URL 및 상태 정보
    """
    # 태그 문자열을 리스트로 변환
    tags_list = None
    if tags:
        tags_list = [tag.strip() for tag in tags.split(",")]
    
    # A2A 서버에 요청 전송
    payload = {
        "video_path": video_path,
        "title": title,
        "description": description,
        "tags": tags_list,
        "privacy_status": privacy_status
    }
    
    result = _call_a2a_server("/v1/upload_youtube", payload)
    return result


@mcp.tool()
def check_server_health() -> Dict[str, Any]:
    """
    A2A 서버의 상태를 확인합니다.
    
    Returns:
        서버 상태 정보
    """
    try:
        response = requests.get(f"{A2A_SERVER_URL}/health", timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "message": "서버에 연결할 수 없습니다."
        }


if __name__ == "__main__":
    """
    MCP 서버 실행
    """
    print("=" * 60)
    print("A2A Healing Shorts Factory MCP Bridge")
    print("=" * 60)
    print(f"A2A 서버 URL: {A2A_SERVER_URL}")
    print("=" * 60)
    
    # MCP 서버 실행
    mcp.run()

