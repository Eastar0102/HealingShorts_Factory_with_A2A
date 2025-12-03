"""
FastAPI 서버 엔트리포인트
A2A 워크플로우를 실행하고 비디오 처리를 BackgroundTask로 처리합니다.
"""

import os
import json
import asyncio
import time
import subprocess
import sys
import socket
import urllib.request
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from dotenv import load_dotenv

from .orchestrator import Orchestrator
from .tools import generate_veo_video_for_duration, make_seamless_loop
from .models import WorkflowResponse
from .agents.uploader import UploaderAgent
from .a2a_config import A2AConfig

# .env 파일 로드
load_dotenv()

# FastAPI 앱 생성
app = FastAPI(
    title="A2A Healing Shorts Factory",
    description="Autonomous Agent-to-Agent system for generating healing shorts",
    version="1.0.0"
)

# 정적 파일 서빙 (HTML, CSS, JS)
# 프로젝트 루트 기준으로 디렉토리 경로 설정
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
static_dir = os.path.join(project_root, "static")
output_dir = os.path.join(project_root, "output")

# 디렉토리가 없으면 생성
os.makedirs(static_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

# 정적 파일 마운트
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 비디오 파일 서빙 (output 디렉토리)
# 디렉토리가 존재하는 경우에만 마운트
if os.path.exists(output_dir):
    try:
        app.mount("/videos", StaticFiles(directory=output_dir), name="videos")
        print(f"[Server] 비디오 파일 서빙 활성화: {output_dir}")
        print(f"[Server] 비디오 파일 접근 경로: /videos/<filename>.mp4")
    except Exception as e:
        print(f"[Server] 경고: 비디오 파일 서빙 마운트 실패: {e}")
else:
    print(f"[Server] 경고: output 디렉토리가 없습니다: {output_dir}")

# 오케스트레이터 및 에이전트 인스턴스
orchestrator = Orchestrator()
uploader_agent = UploaderAgent()

# 전역 변수: 실행 중인 에이전트 프로세스 관리
agent_processes: Dict[str, subprocess.Popen] = {}

# WebSocket 연결 관리
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()


def check_agent_health(url: str, timeout: float = 1.0) -> bool:
    """에이전트 서버 헬스 체크"""
    try:
        response = urllib.request.urlopen(f"{url}/health", timeout=timeout)
        return response.getcode() == 200
    except:
        return False


def check_port_in_use(port: int) -> bool:
    """포트가 사용 중인지 확인"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


async def ensure_agent_servers_running() -> Dict[str, bool]:
    """
    필요한 에이전트 서버들이 실행 중인지 확인하고, 
    실행 중이 아니면 자동으로 시작합니다.
    
    Returns:
        각 에이전트의 시작 성공 여부
    """
    agent_configs = [
        ("planner", "server.agents.planner_server", A2AConfig.DEFAULT_PLANNER_PORT, A2AConfig.get_planner_url()),
        ("reviewer", "server.agents.reviewer_server", A2AConfig.DEFAULT_REVIEWER_PORT, A2AConfig.get_reviewer_url()),
        ("producer", "server.agents.producer_server", A2AConfig.DEFAULT_PRODUCER_PORT, A2AConfig.get_producer_url()),
        ("uploader", "server.agents.uploader_server", A2AConfig.DEFAULT_UPLOADER_PORT, A2AConfig.get_uploader_url()),
    ]
    
    results = {}
    # server/main.py -> server -> shorts_factory
    project_root = Path(__file__).parent.parent
    
    for agent_name, module_name, port, url in agent_configs:
        # 이미 실행 중인 프로세스가 있고 살아있는지 확인
        if agent_name in agent_processes:
            process = agent_processes[agent_name]
            if process.poll() is None:  # 프로세스가 실행 중
                # 헬스 체크로 실제로 응답하는지 확인
                if check_agent_health(url, timeout=1.0):
                    results[agent_name] = True
                    continue
                else:
                    # 프로세스는 있지만 응답하지 않음 - 종료하고 재시작
                    try:
                        process.terminate()
                        process.wait(timeout=2)
                    except:
                        process.kill()
                    del agent_processes[agent_name]
        
        # 포트가 사용 중인지 확인 (다른 프로세스가 실행 중일 수 있음)
        if check_port_in_use(port):
            # 헬스 체크로 실제로 에이전트 서버인지 확인
            if check_agent_health(url, timeout=1.0):
                results[agent_name] = True
                continue
        
        # 서버 시작
        try:
            print(f"  [START] {agent_name.upper()}Agent 시작 중... (포트: {port})")
            process = subprocess.Popen(
                [sys.executable, "-m", module_name],
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            agent_processes[agent_name] = process
            
            # 서버 시작 대기 (최대 10초)
            max_wait = 10
            wait_interval = 0.5
            started = False
            
            for attempt in range(int(max_wait / wait_interval)):
                await asyncio.sleep(wait_interval)
                
                # 프로세스가 종료되었는지 확인
                if process.poll() is not None:
                    # 프로세스가 종료됨 - 에러 발생
                    # 에러 메시지 읽기
                    try:
                        stdout, _ = process.communicate(timeout=1)
                        error_lines = [line for line in stdout.split('\n') 
                                     if line.strip() and 
                                     ('Error' in line or 'Exception' in line or 'Traceback' in line or 'Failed' in line)
                                     and 'FutureWarning' not in line]
                        if error_lines:
                            print(f"    [FAIL] {agent_name.upper()}Agent 시작 실패: {error_lines[0][:100]}")
                        else:
                            print(f"    [FAIL] {agent_name.upper()}Agent 시작 실패 (프로세스가 종료됨)")
                    except:
                        print(f"    ❌ {agent_name.upper()}Agent 시작 실패 (프로세스가 종료됨)")
                    results[agent_name] = False
                    break
                
                # 헬스 체크
                if check_agent_health(url, timeout=1.0):
                    results[agent_name] = True
                    started = True
                    print(f"    [OK] {agent_name.upper()}Agent 시작 완료")
                    break
            
            if not started and process.poll() is None:
                # 프로세스는 실행 중이지만 헬스 체크 실패
                # 일단 성공으로 간주 (서버가 아직 완전히 시작되지 않았을 수 있음)
                results[agent_name] = True
                print(f"    [WAIT] {agent_name.upper()}Agent 시작 중 (헬스 체크 대기 중...)")
            elif not started:
                results[agent_name] = False
                print(f"    [FAIL] {agent_name.upper()}Agent 시작 실패")
                
        except Exception as e:
            print(f"    [FAIL] {agent_name.upper()}Agent 시작 중 예외 발생: {e}")
            results[agent_name] = False
    
    return results


class CreateShortsRequest(BaseModel):
    """비디오 생성 요청 모델"""
    topic: str = Field(description="비디오 주제 키워드 (예: 'Rain', 'Ocean Waves')")
    video_duration: Optional[float] = Field(
        default=30.0, 
        description="비디오 길이 (초). 8초 이하는 단일 클립, 8초 초과는 다중 클립 병합. YouTube Shorts는 15-60초 권장. 기본값: 30초",
        ge=1.0,
        le=300.0
    )
    upload_to_youtube: bool = Field(default=False, description="YouTube에 업로드할지 여부")
    youtube_title: Optional[str] = Field(default=None, description="YouTube 비디오 제목")
    youtube_description: Optional[str] = Field(default=None, description="YouTube 비디오 설명")
    youtube_tags: Optional[List[str]] = Field(default=None, description="YouTube 비디오 태그")


async def process_video_pipeline_with_updates(
    approved_prompt: str,
    video_duration: float = 30.0,
    upload_to_youtube: bool = False,
    youtube_title: Optional[str] = None,
    youtube_description: Optional[str] = None,
    youtube_tags: Optional[List[str]] = None,
    websocket: Optional[WebSocket] = None,
    youtube_metadata: Optional[Dict] = None  # Gemini가 생성한 메타데이터
):
    """
    비디오 생성 파이프라인을 실행하고 WebSocket으로 진행 상황을 전송합니다.
    """
    try:
        # Veo 비디오 생성 시작
        await manager.broadcast({
            "type": "video_status",
            "status": "generating",
            "message": "Veo 비디오 생성 중...",
            "step": "veo_generation"
        })
        
        veo_video_path = generate_veo_video_for_duration(
            prompt=approved_prompt,
            total_duration_seconds=int(video_duration) if video_duration else None,
            aspect_ratio="9:16",  # YouTube Shorts 세로형
            resolution="1080p",  # YouTube Shorts 권장 해상도
        )
        
        await manager.broadcast({
            "type": "video_status",
            "status": "veo_complete",
            "message": f"Veo 비디오 생성 완료: {veo_video_path}",
            "step": "veo_generation",
            "video_path": veo_video_path
        })
        
        # Seamless loop 생성 시작
        await manager.broadcast({
            "type": "video_status",
            "status": "looping",
            "message": "Seamless loop 생성 중...",
            "step": "loop_creation"
        })
        
        looped_video_path = make_seamless_loop(
            veo_video_path,
            target_duration=video_duration,
            target_resolution=(1080, 1920)  # YouTube Shorts 규격
        )
        
        await manager.broadcast({
            "type": "video_status",
            "status": "loop_complete",
            "message": f"Seamless loop 생성 완료: {looped_video_path}",
            "step": "loop_creation",
            "video_path": looped_video_path
        })
        
        # YouTube 업로드는 비디오 완료 후 버튼으로 진행하므로 여기서는 제거
        # 완료
        # 웹에서 접근 가능하도록 파일명만 추출
        import os
        video_filename = os.path.basename(looped_video_path)
        
        await manager.broadcast({
            "type": "video_status",
            "status": "completed",
            "message": "비디오 파이프라인 완료",
            "step": "complete",
            "final_video_path": looped_video_path,
            "video_filename": video_filename,  # 웹 접근용 파일명
            "video_ready_for_upload": True,  # 업로드 준비 완료 플래그
            "youtube_metadata": youtube_metadata  # Gemini가 생성한 YouTube 메타데이터
        })
        
    except Exception as e:
        await manager.broadcast({
            "type": "video_status",
            "status": "error",
            "message": f"비디오 파이프라인 오류: {str(e)}",
            "step": "error"
        })


@app.get("/", response_class=FileResponse)
async def root():
    """웹 인터페이스 메인 페이지"""
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 엔드포인트 - 실시간 업데이트 전송"""
    await manager.connect(websocket)
    try:
        while True:
            # 클라이언트로부터 메시지 수신 대기 (필요시)
            data = await websocket.receive_text()
            # 에코 응답 (선택사항)
            await websocket.send_json({"type": "echo", "message": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/v1/create_shorts", response_model=WorkflowResponse)
async def create_shorts(
    request: CreateShortsRequest,
    background_tasks: BackgroundTasks
):
    """
    Healing Shorts 생성 엔드포인트
    
    A2A 워크플로우를 실행하여:
    1. 필요한 에이전트 서버들이 실행 중인지 확인하고 자동 시작
    2. Planner와 Reviewer가 협업하여 승인된 프롬프트 생성
    3. 비디오 처리를 BackgroundTask로 스케줄링
    4. 즉시 응답 반환 (비동기 처리)
    """
    try:
        # 0. 필요한 에이전트 서버들이 실행 중인지 확인 (startup에서 이미 시작했지만, 혹시 모를 상황 대비)
        from .a2a_config import A2AConfig
        
        planner_healthy = check_agent_health(A2AConfig.get_planner_url(), timeout=1.0)
        reviewer_healthy = check_agent_health(A2AConfig.get_reviewer_url(), timeout=1.0)
        
        # 필수 에이전트가 실행 중이 아니면 재시도
        if not planner_healthy or not reviewer_healthy:
            print("[WARNING] 일부 에이전트 서버가 응답하지 않습니다. 재시도 중...")
            agent_status = await ensure_agent_servers_running()
            
            if not agent_status.get("planner", False):
                raise HTTPException(
                    status_code=503,
                    detail="PlannerAgent 서버를 시작할 수 없습니다. 서버를 재시작해주세요."
                )
            if not agent_status.get("reviewer", False):
                raise HTTPException(
                    status_code=503,
                    detail="ReviewerAgent 서버를 시작할 수 없습니다. 서버를 재시작해주세요."
                )
        
        # A2A 워크플로우 실행 중 실시간 이벤트 전송
        async def send_agent_updates():
            # 오케스트레이터의 워크플로우를 수정하여 실시간 업데이트 전송
            # 현재는 간단하게 conversation_log를 전송
            pass
        
        # 1. A2A 워크플로우 실행 (동기적으로 실행하여 승인된 프롬프트 획득)
        workflow_result = await orchestrator.run_a2a_workflow(
            request.topic,
            video_duration=request.video_duration
        )
        
        # 실시간 에이전트 대화 로그 전송
        if "conversation_log" in workflow_result:
            for entry in workflow_result["conversation_log"]:
                agent = entry.get("agent", "Unknown")
                action = entry.get("action", "")
                output = entry.get("output", {})
                
                if action == "generate":
                    await manager.broadcast({
                        "type": "agent_message",
                        "agent": agent,
                        "action": "generate",
                        "message": output if isinstance(output, str) else output.get("content", "")
                    })
                elif action == "review":
                    review_output = output if isinstance(output, dict) else {}
                    await manager.broadcast({
                        "type": "agent_message",
                        "agent": agent,
                        "action": "review",
                        "status": review_output.get("status", "UNKNOWN"),
                        "score": review_output.get("score", 0),
                        "feedback": review_output.get("feedback", "")
                    })
        
        if not workflow_result["success"]:
            return WorkflowResponse(
                status="failed",
                conversation_log=workflow_result.get("conversation_log", []),
                message=workflow_result.get("error", "워크플로우 실행 실패")
            )
        
        approved_prompt = workflow_result["approved_prompt"]
        conversation_log = workflow_result["conversation_log"]
        youtube_metadata = workflow_result.get("youtube_metadata")
        
        # YouTube 메타데이터: 사용자가 제공한 값이 있으면 우선 사용, 없으면 Gemini 생성 값 사용
        youtube_title = request.youtube_title
        youtube_description = request.youtube_description
        youtube_tags = request.youtube_tags
        
        if youtube_metadata:
            # Gemini가 생성한 메타데이터를 기본값으로 사용
            if not youtube_title:
                youtube_title = youtube_metadata.title
            if not youtube_description:
                youtube_description = youtube_metadata.description
            if not youtube_tags:
                youtube_tags = youtube_metadata.tags
        
        # 2. 비디오 처리를 BackgroundTask로 스케줄링 (WebSocket 업데이트 포함)
        background_tasks.add_task(
            process_video_pipeline_with_updates,
            approved_prompt=approved_prompt,
            video_duration=request.video_duration,
            upload_to_youtube=request.upload_to_youtube,
            youtube_title=youtube_title,
            youtube_description=youtube_description,
            youtube_tags=youtube_tags,
            youtube_metadata=youtube_metadata.dict() if youtube_metadata else None  # Gemini 메타데이터 전달
        )
        
        # 3. 즉시 응답 반환
        return WorkflowResponse(
            status="processing",
            approved_prompt=approved_prompt,
            conversation_log=conversation_log,
            youtube_metadata=youtube_metadata,
            message=f"프롬프트 승인 완료. 비디오 생성이 백그라운드에서 진행 중입니다. (반복 횟수: {workflow_result['iterations']}, 점수: {workflow_result['final_score']})"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"서버 오류: {str(e)}"
        )


class UploadYouTubeRequest(BaseModel):
    """YouTube 업로드 요청 모델"""
    video_path: str = Field(description="업로드할 비디오 파일 경로")
    title: Optional[str] = Field(default=None, description="YouTube 비디오 제목")
    description: Optional[str] = Field(default=None, description="YouTube 비디오 설명")
    tags: Optional[List[str]] = Field(default=None, description="YouTube 비디오 태그")
    privacy_status: str = Field(default="public", description="공개 설정 (public, unlisted, private)")


async def process_youtube_upload_with_updates(
    video_path: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    privacy_status: str = "public",
    youtube_metadata: Optional[Dict] = None
):
    """
    UploaderAgent를 사용하여 YouTube 업로드를 실행하고 WebSocket으로 진행 상황을 전송합니다.
    """
    try:
        await manager.broadcast({
            "type": "youtube_upload_status",
            "status": "uploading",
            "message": "UploaderAgent: YouTube 업로드 준비 중...",
            "step": "youtube_upload"
        })
        
        # YouTubeMetadata 객체 생성 (있는 경우)
        from .models import YouTubeMetadata
        metadata_obj = None
        if youtube_metadata:
            try:
                metadata_obj = YouTubeMetadata(**youtube_metadata)
            except Exception as e:
                print(f"[UploaderAgent] 메타데이터 파싱 실패: {e}")
        
        # UploaderAgent를 사용하여 업로드 실행
        result = await uploader_agent.process(
            video_path=video_path,
            youtube_metadata=metadata_obj,
            title=title,
            description=description,
            tags=tags,
            privacy_status=privacy_status
        )
        
        if result["success"]:
            await manager.broadcast({
                "type": "youtube_upload_status",
                "status": "upload_complete",
                "message": f"UploaderAgent: {result['message']}",
                "step": "youtube_upload",
                "youtube_url": result["youtube_url"]
            })
            return result["youtube_url"]
        else:
            raise Exception(result["message"])
        
    except Exception as e:
        await manager.broadcast({
            "type": "youtube_upload_status",
            "status": "upload_failed",
            "message": f"UploaderAgent: YouTube 업로드 실패: {str(e)}",
            "step": "youtube_upload"
        })
        raise


@app.post("/v1/upload_youtube")
async def upload_youtube(
    request: UploadYouTubeRequest,
    background_tasks: BackgroundTasks
):
    """
    이미 생성된 비디오 파일을 YouTube에 업로드합니다.
    
    Args:
        request: 업로드 요청 정보 (비디오 경로, 제목, 설명, 태그, 공개 설정)
        background_tasks: 백그라운드 작업 관리
        
    Returns:
        업로드 시작 응답
    """
    try:
        import os
        
        # 비디오 파일 경로 처리 (상대 경로를 절대 경로로 변환)
        video_path = request.video_path
        if not os.path.isabs(video_path):
            # 상대 경로인 경우 프로젝트 루트 기준으로 변환
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # output 디렉토리 기준으로도 확인
            output_dir = os.path.join(project_root, "output")
            if os.path.exists(os.path.join(output_dir, video_path)):
                video_path = os.path.join(output_dir, video_path)
            elif os.path.exists(os.path.join(project_root, video_path)):
                video_path = os.path.join(project_root, video_path)
            else:
                video_path = os.path.join(output_dir, video_path)  # 기본값
        
        # 비디오 파일 존재 여부 확인
        if not os.path.exists(video_path):
            raise HTTPException(
                status_code=404,
                detail=f"비디오 파일을 찾을 수 없습니다: {video_path}\n"
                       f"원본 경로: {request.video_path}"
            )
        
        # YouTube 메타데이터 가져오기 (있는 경우)
        youtube_metadata = None
        # TODO: 비디오 파일과 연결된 메타데이터를 찾는 로직 추가 가능
        
        # YouTube 업로드를 BackgroundTask로 실행 (UploaderAgent 사용)
        background_tasks.add_task(
            process_youtube_upload_with_updates,
            video_path=video_path,
            title=request.title,
            description=request.description,
            tags=request.tags,
            privacy_status=request.privacy_status,
            youtube_metadata=youtube_metadata
        )
        
        return {
            "status": "processing",
            "message": "YouTube 업로드가 시작되었습니다."
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"YouTube 업로드 실패: {str(e)}"
        )


@app.get("/v1/list_videos")
async def list_videos():
    """
    output 폴더에 있는 모든 비디오 파일 목록을 반환합니다.
    
    Returns:
        비디오 파일 목록 (파일명, 경로, 크기, 수정 시간)
    """
    try:
        video_files = []
        
        # output 디렉토리에서 .mp4 파일 찾기
        if os.path.exists(output_dir):
            print(f"[Server] output 디렉토리 스캔 중: {output_dir}")
            for filename in os.listdir(output_dir):
                if filename.lower().endswith('.mp4'):
                    file_path = os.path.join(output_dir, filename)
                    if not os.path.exists(file_path):
                        print(f"[Server] 경고: 파일이 존재하지 않음: {file_path}")
                        continue
                    file_stat = os.stat(file_path)
                    
                    video_files.append({
                        "filename": filename,
                        "path": f"output/{filename}",  # API 응답용 경로
                        "url": f"/videos/{filename}",  # 웹 접근용 URL 추가
                        "size": file_stat.st_size,
                        "size_mb": round(file_stat.st_size / (1024 * 1024), 2),
                        "modified_time": file_stat.st_mtime,
                        "modified_time_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(file_stat.st_mtime))
                    })
            print(f"[Server] 발견된 비디오 파일 수: {len(video_files)}")
        else:
            print(f"[Server] 경고: output 디렉토리가 존재하지 않음: {output_dir}")
        
        # 수정 시간 기준으로 최신순 정렬
        video_files.sort(key=lambda x: x["modified_time"], reverse=True)
        
        return {
            "status": "success",
            "count": len(video_files),
            "videos": video_files
        }
    except Exception as e:
        print(f"[Server] 비디오 목록 조회 오류: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"비디오 목록 조회 실패: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """헬스 체크 엔드포인트"""
    return {"status": "healthy"}


@app.on_event("startup")
async def startup_event():
    """서버 시작 시 에이전트 서버들을 미리 시작"""
    print("\n" + "=" * 60)
    print("[START] 메인 서버 시작 중...")
    print("=" * 60)
    print("\n[INFO] A2A 에이전트 서버들을 시작합니다...\n")
    
    agent_status = await ensure_agent_servers_running()
    
    print("\n" + "=" * 60)
    print("[OK] 에이전트 서버 시작 완료")
    print("=" * 60)
    
    # 각 에이전트 상태 출력
    for agent_name, status in agent_status.items():
        status_icon = "[OK]" if status else "[FAIL]"
        status_text = "실행 중" if status else "실패"
        print(f"  {status_icon} {agent_name.upper()}Agent: {status_text}")
    
    print("\n" + "=" * 60)
    print("[INFO] 웹 인터페이스: http://localhost:8000")
    print("=" * 60 + "\n")
    
    # 필수 에이전트가 시작되지 않은 경우 경고
    if not agent_status.get("planner", False) or not agent_status.get("reviewer", False):
        print("[WARNING] 경고: 필수 에이전트 서버가 시작되지 않았습니다.")
        print("          비디오 생성 기능이 정상적으로 작동하지 않을 수 있습니다.\n")


@app.on_event("shutdown")
async def shutdown_event():
    """서버 종료 시 에이전트 서버들도 종료"""
    print("\n" + "=" * 60)
    print("[SHUTDOWN] 메인 서버 종료 중...")
    print("=" * 60)
    print("\n[INFO] A2A 에이전트 서버들을 종료합니다...\n")
    
    for agent_name, process in agent_processes.items():
        if process.poll() is None:  # 프로세스가 실행 중인 경우
            try:
                process.terminate()
                process.wait(timeout=5)
                print(f"  [OK] {agent_name.upper()}Agent 종료됨")
            except:
                process.kill()
                print(f"  [OK] {agent_name.upper()}Agent 강제 종료됨")
    
    print("\n" + "=" * 60)
    print("[OK] 모든 서버 종료 완료")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
