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
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from dotenv import load_dotenv

from .orchestrator import Orchestrator
from .tools import generate_veo_clip, make_seamless_loop
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
        description="비디오 길이 (초). YouTube Shorts는 15-60초 권장. 기본값: 30초",
        ge=15.0,
        le=60.0
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
        
        veo_video_path = generate_veo_clip(
            approved_prompt,
            duration_seconds=int(video_duration) if video_duration else None,
            aspect_ratio="9:16",  # YouTube Shorts 세로형
            resolution="1080p"  # YouTube Shorts 권장 해상도
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


@app.get("/", response_class=HTMLResponse)
async def root():
    """웹 인터페이스 메인 페이지"""
    html_content = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>A2A Healing Shorts Factory</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .header p {
            opacity: 0.9;
        }
        
        .content {
            padding: 30px;
        }
        
        .input-section {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 15px;
            margin-bottom: 30px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #333;
        }
        
        input[type="text"], input[type="number"], textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        
        input[type="text"]:focus, input[type="number"]:focus, textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        
        small {
            display: block;
            margin-top: 5px;
            color: #666;
            font-size: 14px;
        }
        
        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        input[type="checkbox"] {
            width: 20px;
            height: 20px;
            cursor: pointer;
        }
        
        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 40px;
            font-size: 18px;
            font-weight: 600;
            border-radius: 10px;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .status-section {
            margin-top: 30px;
        }
        
        .status-card {
            background: #f8f9fa;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
        }
        
        .status-card h3 {
            margin-bottom: 15px;
            color: #333;
        }
        
        .log-container {
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 20px;
            border-radius: 10px;
            max-height: 400px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.6;
        }
        
        .log-entry {
            margin-bottom: 10px;
            padding: 8px;
            border-left: 3px solid #667eea;
            padding-left: 15px;
        }
        
        .log-entry.planner {
            border-left-color: #4CAF50;
        }
        
        .log-entry.reviewer {
            border-left-color: #FF9800;
        }
        
        .log-entry.video {
            border-left-color: #2196F3;
        }
        
        .log-entry.error {
            border-left-color: #f44336;
        }
        
        .status-badge {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            margin-left: 10px;
        }
        
        .status-badge.processing {
            background: #FF9800;
            color: white;
        }
        
        .status-badge.completed {
            background: #4CAF50;
            color: white;
        }
        
        .status-badge.failed {
            background: #f44336;
            color: white;
        }
        
        .video-preview {
            margin-top: 20px;
            text-align: center;
        }
        
        .video-preview video {
            max-width: 100%;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        
        .hidden {
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎬 A2A Healing Shorts Factory</h1>
            <p>자율적 에이전트 협업 시스템으로 힐링 쇼츠를 생성합니다</p>
        </div>
        
        <div class="content">
            <div class="input-section">
                <div class="form-group">
                    <label for="topic">비디오 주제</label>
                    <input type="text" id="topic" placeholder="예: Rain, Ocean Waves, Forest" value="Rain">
                </div>
                
                <div class="form-group">
                    <label for="videoDuration">비디오 길이 (초) - YouTube Shorts: 15-60초 권장</label>
                    <input type="number" id="videoDuration" min="15" max="60" step="1" value="30" placeholder="30">
                    <small style="color: #666; display: block; margin-top: 5px;">YouTube Shorts는 최소 15초, 최대 60초입니다.</small>
                </div>
                
                <button id="createBtn">비디오 생성 시작</button>
            </div>
            
            <div class="input-section" style="margin-top: 30px;">
                <h3 style="margin-bottom: 20px;">📁 저장된 영상 목록</h3>
                <button id="refreshVideoListBtn" style="margin-bottom: 15px; padding: 10px 20px; font-size: 14px;">🔄 목록 새로고침</button>
                <div id="videoListContainer" style="max-height: 400px; overflow-y: auto;">
                    <p style="color: #666; text-align: center; padding: 20px;">영상 목록을 불러오는 중...</p>
                </div>
            </div>
            
            <div class="status-section" id="statusSection" style="display: none;">
                <div class="status-card">
                    <h3>에이전트 대화 로그 <span class="status-badge processing" id="agentStatus">대기 중</span></h3>
                    <div class="log-container" id="agentLog"></div>
                </div>
                
                <div class="status-card">
                    <h3>비디오 생성 상태 <span class="status-badge processing" id="videoStatus">대기 중</span></h3>
                    <div class="log-container" id="videoLog"></div>
                </div>
                
                <div class="video-preview" id="videoPreview"></div>
                
                <div class="form-group" id="youtubeUploadSection" style="display: none; margin-top: 20px; background: #f8f9fa; padding: 20px; border-radius: 10px;">
                    <h3>YouTube 업로드</h3>
                    <div class="form-group" style="margin-top: 15px;">
                        <label for="uploadTitle">제목</label>
                        <input type="text" id="uploadTitle" placeholder="YouTube 비디오 제목" style="width: 100%; padding: 10px; border: 2px solid #e0e0e0; border-radius: 5px;">
                    </div>
                    <div class="form-group" style="margin-top: 15px;">
                        <label for="uploadDescription">설명</label>
                        <textarea id="uploadDescription" rows="4" placeholder="YouTube 비디오 설명" style="width: 100%; padding: 10px; border: 2px solid #e0e0e0; border-radius: 5px;"></textarea>
                    </div>
                    <div class="form-group" style="margin-top: 15px;">
                        <label for="uploadTags">태그 (쉼표로 구분)</label>
                        <input type="text" id="uploadTags" placeholder="healing, asmr, nature" style="width: 100%; padding: 10px; border: 2px solid #e0e0e0; border-radius: 5px;">
                    </div>
                    <button id="uploadYoutubeBtn" style="background: #ff0000; color: white; padding: 12px 30px; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; margin-top: 15px;">
                        📺 YouTube에 업로드
                    </button>
                    <div id="youtubeUploadStatus" style="margin-top: 10px;"></div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let ws = null;
        let currentVideoPath = null;
        let currentVideoMetadata = null;
        
        function addLog(containerId, message, className = '') {
            const container = document.getElementById(containerId);
            const entry = document.createElement('div');
            entry.className = `log-entry ${className}`;
            entry.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
            container.appendChild(entry);
            container.scrollTop = container.scrollHeight;
        }
        
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            
            ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
                addLog('agentLog', 'WebSocket 연결됨', '');
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                if (data.type === 'agent_message') {
                    const agent = data.agent;
                    const action = data.action;
                    const message = data.message;
                    
                    if (action === 'generate') {
                        addLog('agentLog', `🤖 ${agent}: 프롬프트 생성`, 'planner');
                        addLog('agentLog', `   "${message}"`, 'planner');
                    } else if (action === 'review') {
                        const status = data.status;
                        const score = data.score;
                        const feedback = data.feedback;
                        
                        addLog('agentLog', `🔍 ${agent}: 프롬프트 검토`, 'reviewer');
                        addLog('agentLog', `   상태: ${status} (점수: ${score}/100)`, status === 'APPROVED' ? 'reviewer' : 'error');
                        if (feedback) {
                            addLog('agentLog', `   피드백: ${feedback}`, 'reviewer');
                        }
                    }
                } else if (data.type === 'video_status') {
                    const status = data.status;
                    const message = data.message;
                    
                    addLog('videoLog', message, 'video');
                    
                    if (status === 'completed') {
                        document.getElementById('videoStatus').textContent = '완료';
                        document.getElementById('videoStatus').className = 'status-badge completed';
                        
                        // video_filename이 있으면 우선 사용, 없으면 final_video_path에서 파일명 추출
                        const videoFile = data.video_filename || (data.final_video_path ? data.final_video_path.split(/[\\/]/).pop() : null);
                        if (videoFile) {
                            // currentVideoPath를 올바른 형식으로 설정 (output/filename.mp4)
                            currentVideoPath = `output/${videoFile}`;
                            console.log('[DEBUG] 비디오 생성 완료, currentVideoPath 설정:', currentVideoPath);
                            showVideoPreview(videoFile);
                            
                            // YouTube 메타데이터 설정
                            if (data.youtube_metadata) {
                                currentVideoMetadata = data.youtube_metadata;
                                console.log('[DEBUG] YouTube 메타데이터 설정:', currentVideoMetadata);
                                
                                const titleInput = document.getElementById('uploadTitle');
                                const descriptionInput = document.getElementById('uploadDescription');
                                const tagsInput = document.getElementById('uploadTags');
                                
                                if (titleInput) {
                                    titleInput.value = data.youtube_metadata.title || '';
                                }
                                if (descriptionInput) {
                                    descriptionInput.value = data.youtube_metadata.description || '';
                                }
                                if (tagsInput) {
                                    tagsInput.value = data.youtube_metadata.tags ? data.youtube_metadata.tags.join(', ') : '';
                                }
                            }
                            
                            // YouTube 업로드 섹션 표시
                            const uploadSection = document.getElementById('youtubeUploadSection');
                            if (uploadSection) {
                                uploadSection.style.display = 'block';
                                console.log('[DEBUG] YouTube 업로드 섹션 표시됨');
                                
                                // 업로드 버튼 이벤트 리스너 재설정 (중요!)
                                const uploadBtn = document.getElementById('uploadYoutubeBtn');
                                if (uploadBtn) {
                                    // 기존 이벤트 리스너 제거
                                    uploadBtn.onclick = null;
                                    uploadBtn.replaceWith(uploadBtn.cloneNode(true));
                                    const newUploadBtn = document.getElementById('uploadYoutubeBtn');
                                    
                                    // 이벤트 리스너 등록
                                    newUploadBtn.addEventListener('click', (e) => {
                                        console.log('[DEBUG] ========== uploadYoutubeBtn 클릭 이벤트 발생 (비디오 생성 완료 후) ==========');
                                        e.preventDefault();
                                        e.stopPropagation();
                                        uploadToYouTube().catch(err => {
                                            console.error('[DEBUG] uploadToYouTube 실행 중 오류:', err);
                                        });
                                    });
                                    
                                    // onclick 속성도 설정 (이중 보험)
                                    newUploadBtn.setAttribute('onclick', 'event.preventDefault(); event.stopPropagation(); uploadToYouTube();');
                                    newUploadBtn.disabled = false; // 버튼 활성화
                                    console.log('[DEBUG] 업로드 버튼 이벤트 리스너 재설정됨 (onclick 속성도 설정)');
                                } else {
                                    console.error('[DEBUG] uploadYoutubeBtn 요소를 찾을 수 없음');
                                }
                            } else {
                                console.error('[DEBUG] youtubeUploadSection 요소를 찾을 수 없음');
                            }
                        }
                    } else if (status === 'error') {
                        document.getElementById('videoStatus').textContent = '오류';
                        document.getElementById('videoStatus').className = 'status-badge failed';
                    }
                } else if (data.type === 'youtube_upload_status') {
                    const status = data.status;
                    const message = data.message;
                    
                    addLog('videoLog', message, 'video');
                    
                    const uploadStatusDiv = document.getElementById('youtubeUploadStatus');
                    if (status === 'upload_complete') {
                        uploadStatusDiv.innerHTML = `<p style="color: green; font-weight: 600;">✅ ${message}</p>`;
                        if (data.youtube_url) {
                            uploadStatusDiv.innerHTML += `<p style="margin-top: 10px;"><a href="${data.youtube_url}" target="_blank" style="color: #ff0000; text-decoration: none; font-weight: 600;">YouTube에서 보기 →</a></p>`;
                        }
                        document.getElementById('uploadYoutubeBtn').disabled = false;
                        document.getElementById('uploadYoutubeBtn').textContent = '📺 YouTube에 업로드 완료';
                    } else if (status === 'upload_failed') {
                        uploadStatusDiv.innerHTML = `<p style="color: red; font-weight: 600;">❌ ${message}</p>`;
                        document.getElementById('uploadYoutubeBtn').disabled = false;
                    } else if (status === 'uploading') {
                        uploadStatusDiv.innerHTML = `<p style="color: #666;">⏳ ${message}</p>`;
                        document.getElementById('uploadYoutubeBtn').disabled = true;
                        document.getElementById('uploadYoutubeBtn').textContent = '⏳ 업로드 중...';
                    }
                }
            };
            
            ws.onerror = (error) => {
                addLog('agentLog', 'WebSocket 오류 발생', 'error');
            };
            
            ws.onclose = () => {
                addLog('agentLog', 'WebSocket 연결 종료', '');
            };
        }
        
        function showVideoPreview(videoPath) {
            const preview = document.getElementById('videoPreview');
            // 파일명만 추출 (이미 파일명만 전달되도록 수정됨)
            const fileName = videoPath.split(/[\\/]/).pop();
            const videoUrl = `/videos/${fileName}`;
            
            preview.innerHTML = `
                <h3>생성된 비디오</h3>
                <video controls autoplay loop style="max-width: 100%; border-radius: 10px;">
                    <source src="${videoUrl}" type="video/mp4">
                    비디오를 재생할 수 없습니다.
                </video>
                <p style="margin-top: 10px; color: #666;">파일: ${fileName}</p>
                <p style="margin-top: 5px; color: #999; font-size: 12px;">URL: ${videoUrl}</p>
            `;
        }
        
        async function createShorts() {
            const topic = document.getElementById('topic').value;
            const videoDuration = parseFloat(document.getElementById('videoDuration').value) || 30.0;
            
            if (!topic) {
                alert('비디오 주제를 입력하세요.');
                return;
            }
            
            if (videoDuration < 15 || videoDuration > 60) {
                alert('비디오 길이는 15초에서 60초 사이여야 합니다.');
                return;
            }
            
            // UI 초기화
            document.getElementById('statusSection').style.display = 'block';
            document.getElementById('agentLog').innerHTML = '';
            document.getElementById('videoLog').innerHTML = '';
            document.getElementById('videoPreview').innerHTML = '';
            document.getElementById('youtubeUploadSection').style.display = 'none';
            document.getElementById('youtubeUploadStatus').innerHTML = '';
            document.getElementById('createBtn').disabled = true;
            document.getElementById('agentStatus').textContent = '처리 중';
            document.getElementById('videoStatus').textContent = '대기 중';
            
            // WebSocket 연결
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                connectWebSocket();
                await new Promise(resolve => setTimeout(resolve, 500));
            }
            
            // API 호출
            try {
                const response = await fetch('/v1/create_shorts', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        topic: topic,
                        video_duration: videoDuration,
                        upload_to_youtube: false  // 업로드는 나중에 버튼으로
                    })
                });
                
                const result = await response.json();
                
                if (result.status === 'processing') {
                    addLog('agentLog', '✅ 프롬프트 승인 완료!', 'planner');
                    addLog('agentLog', `   반복 횟수: ${result.conversation_log?.length || 0}`, '');
                    document.getElementById('agentStatus').textContent = '완료';
                    document.getElementById('agentStatus').className = 'status-badge completed';
                    
                    // YouTube 메타데이터 저장
                    if (result.youtube_metadata) {
                        currentVideoMetadata = result.youtube_metadata;
                    }
                } else {
                    addLog('agentLog', `❌ 오류: ${result.message}`, 'error');
                    document.getElementById('agentStatus').textContent = '실패';
                    document.getElementById('agentStatus').className = 'status-badge failed';
                }
            } catch (error) {
                addLog('agentLog', `❌ 요청 실패: ${error.message}`, 'error');
                document.getElementById('agentStatus').textContent = '실패';
                document.getElementById('agentStatus').className = 'status-badge failed';
            } finally {
                document.getElementById('createBtn').disabled = false;
            }
        }
        
        // 전역 업로드 핸들러 함수 (버튼 클릭 이벤트용)
        window.handleYouTubeUpload = async function handleYouTubeUpload(e) {
            console.log('[DEBUG] ========== handleYouTubeUpload 함수 호출됨 ==========');
            console.log('[DEBUG] 이벤트 객체:', e);
            console.log('[DEBUG] currentVideoPath:', currentVideoPath);
            if (e) {
                e.preventDefault();
                e.stopPropagation();
            }
            try {
                if (window.uploadToYouTube) {
                    console.log('[DEBUG] window.uploadToYouTube 함수 호출 시작');
                    await window.uploadToYouTube();
                } else {
                    console.error('[DEBUG] window.uploadToYouTube 함수를 찾을 수 없음');
                    alert('업로드 함수를 찾을 수 없습니다. 페이지를 새로고침해주세요.');
                }
            } catch (err) {
                console.error('[DEBUG] uploadToYouTube 실행 중 오류:', err);
                alert(`업로드 중 오류가 발생했습니다: ${err.message}`);
            }
        };
        
        // 통합된 YouTube 업로드 함수 (전역 함수로 선언)
        window.uploadToYouTube = async function uploadToYouTube() {
            console.log('[DEBUG] ========== uploadToYouTube 함수 호출됨 ==========');
            console.log('[DEBUG] currentVideoPath:', currentVideoPath);
            console.log('[DEBUG] currentVideoMetadata:', currentVideoMetadata);
            
            if (!currentVideoPath) {
                alert('업로드할 비디오가 없습니다. 먼저 비디오를 생성하거나 목록에서 선택하세요.');
                console.error('[DEBUG] currentVideoPath가 설정되지 않음');
                return;
            }
            
            const uploadBtn = document.getElementById('uploadYoutubeBtn');
            const uploadStatus = document.getElementById('youtubeUploadStatus');
            
            if (!uploadBtn) {
                console.error('[DEBUG] uploadYoutubeBtn 요소를 찾을 수 없음');
                alert('업로드 버튼을 찾을 수 없습니다.');
                return;
            }
            
            if (!uploadStatus) {
                console.error('[DEBUG] youtubeUploadStatus 요소를 찾을 수 없음');
                alert('업로드 상태 표시 영역을 찾을 수 없습니다.');
                return;
            }
            
            console.log('[DEBUG] 업로드 시작');
            uploadBtn.disabled = true;
            uploadBtn.textContent = '⏳ 업로드 중...';
            uploadStatus.innerHTML = '<p style="color: #667eea;">YouTube에 업로드 중입니다...</p>';
            
            // 입력 필드에서 메타데이터 가져오기 (우선순위), 없으면 저장된 메타데이터 사용
            const titleInput = document.getElementById('uploadTitle');
            const descriptionInput = document.getElementById('uploadDescription');
            const tagsInput = document.getElementById('uploadTags');
            
            const title = titleInput?.value?.trim() || currentVideoMetadata?.title || null;
            const description = descriptionInput?.value?.trim() || currentVideoMetadata?.description || null;
            const tagsValue = tagsInput?.value?.trim();
            const tags = tagsValue ? tagsValue.split(',').map(t => t.trim()).filter(t => t) : (currentVideoMetadata?.tags || null);
            
            console.log('[DEBUG] 업로드 메타데이터:', { title, description, tags, video_path: currentVideoPath });
            
            try {
                const requestBody = {
                    video_path: currentVideoPath,
                    title: title || null,
                    description: description || null,
                    tags: tags,
                    privacy_status: 'unlisted'
                };
                
                console.log('[DEBUG] API 요청 전송:', requestBody);
                
                const response = await fetch('/v1/upload_youtube', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(requestBody)
                });
                
                console.log('[DEBUG] API 응답 상태:', response.status);
                
                if (!response.ok) {
                    const errorText = await response.text();
                    console.error('[DEBUG] API 오류 응답:', errorText);
                    throw new Error(`서버 오류 (${response.status}): ${errorText}`);
                }
                
                const result = await response.json();
                console.log('[DEBUG] API 응답 결과:', result);
                
                if (result.status === 'processing') {
                    uploadStatus.innerHTML = '<p style="color: #4CAF50;">✅ YouTube 업로드가 시작되었습니다. 완료되면 WebSocket을 통해 알림을 받습니다.</p>';
                    addLog('videoLog', 'YouTube 업로드 시작됨', 'video');
                } else {
                    throw new Error(result.message || '업로드 실패');
                }
            } catch (error) {
                console.error('[DEBUG] 업로드 오류:', error);
                addLog('videoLog', `❌ YouTube 업로드 요청 실패: ${error.message}`, 'error');
                uploadStatus.innerHTML = `<p style="color: #f44336;">❌ 업로드 요청 실패: ${error.message}</p>`;
                uploadBtn.disabled = false;
                uploadBtn.textContent = '📺 YouTube에 업로드';
            }
        }
        
        // 영상 목록 불러오기
        async function loadVideoList() {
            const container = document.getElementById('videoListContainer');
            container.innerHTML = '<p style="color: #666; text-align: center; padding: 20px;">영상 목록을 불러오는 중...</p>';
            
            try {
                const response = await fetch('/v1/list_videos');
                const result = await response.json();
                
                if (result.status === 'success' && result.videos && result.videos.length > 0) {
                    container.innerHTML = '';
                    
                    result.videos.forEach(video => {
                        const videoItem = document.createElement('div');
                        videoItem.style.cssText = 'border: 1px solid #e0e0e0; border-radius: 8px; padding: 15px; margin-bottom: 10px; background: white;';
                        
                        // 비디오 경로와 파일명을 안전하게 이스케이프
                        const safePath = video.path.replace(/'/g, "\\'").replace(/"/g, '&quot;');
                        const safeFilename = video.filename.replace(/'/g, "\\'").replace(/"/g, '&quot;');
                        
                        videoItem.innerHTML = `
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div style="flex: 1;">
                                    <div style="font-weight: 600; margin-bottom: 5px;">${video.filename}</div>
                                    <div style="font-size: 12px; color: #666;">
                                        크기: ${video.size_mb} MB | 수정: ${video.modified_time_str}
                                    </div>
                                    <video controls style="max-width: 100%; margin-top: 10px; border-radius: 5px;" src="${video.url || '/videos/' + video.filename}"></video>
                                </div>
                                <div style="margin-left: 15px;">
                                    <button class="video-upload-btn" 
                                            data-video-path="${safePath}"
                                            data-video-filename="${safeFilename}"
                                            style="background: #ff0000; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: 600;">
                                        📺 YouTube 업로드
                                    </button>
                                </div>
                            </div>
                        `;
                        
                        // 버튼에 이벤트 리스너 직접 추가 (onclick 속성 대신)
                        const uploadBtn = videoItem.querySelector('.video-upload-btn');
                        if (uploadBtn) {
                            uploadBtn.addEventListener('click', function(e) {
                                console.log('[DEBUG] ========== 영상 목록의 YouTube 업로드 버튼 클릭됨 ==========');
                                e.preventDefault();
                                e.stopPropagation();
                                const videoPath = this.getAttribute('data-video-path');
                                const filename = this.getAttribute('data-video-filename');
                                console.log('[DEBUG] 버튼에서 읽은 값:', { videoPath, filename });
                                if (window.selectVideoForUpload) {
                                    window.selectVideoForUpload(videoPath, filename);
                                } else {
                                    console.error('[DEBUG] window.selectVideoForUpload 함수를 찾을 수 없음');
                                    alert('업로드 함수를 찾을 수 없습니다. 페이지를 새로고침해주세요.');
                                }
                            });
                        }
                        
                        container.appendChild(videoItem);
                    });
                } else {
                    container.innerHTML = '<p style="color: #666; text-align: center; padding: 20px;">저장된 영상이 없습니다.</p>';
                }
            } catch (error) {
                container.innerHTML = `<p style="color: #f44336; text-align: center; padding: 20px;">영상 목록을 불러오는데 실패했습니다: ${error.message}</p>`;
            }
        }
        
        // 영상 선택 및 YouTube 업로드 섹션 표시 (전역 함수로 선언)
        window.selectVideoForUpload = async function selectVideoForUpload(videoPath, filename) {
            console.log('[DEBUG] ========== selectVideoForUpload 호출됨 ==========');
            console.log('[DEBUG] videoPath:', videoPath);
            console.log('[DEBUG] filename:', filename);
            
            // 현재 비디오 경로 저장
            currentVideoPath = videoPath;
            console.log('[DEBUG] currentVideoPath 설정됨:', currentVideoPath);
            
            // YouTube 업로드 섹션 표시
            const uploadSection = document.getElementById('youtubeUploadSection');
            if (!uploadSection) {
                console.error('[DEBUG] youtubeUploadSection 요소를 찾을 수 없음');
                alert('업로드 섹션을 찾을 수 없습니다.');
                return;
            }
            
            uploadSection.style.display = 'block';
            console.log('[DEBUG] 업로드 섹션 표시됨');
            
            // 메타데이터 필드 초기화 (파일명 기반 기본값)
            const titleInput = document.getElementById('uploadTitle');
            const descriptionInput = document.getElementById('uploadDescription');
            const tagsInput = document.getElementById('uploadTags');
            
            if (titleInput) {
                titleInput.value = filename.replace('.mp4', '').replace(/_/g, ' ');
            }
            if (descriptionInput) {
                descriptionInput.value = '';
            }
            if (tagsInput) {
                tagsInput.value = 'healing, asmr, nature, relaxation';
            }
            
            // 업로드 버튼 이벤트 리스너 재설정 (중요!)
            const uploadBtn = document.getElementById('uploadYoutubeBtn');
            if (uploadBtn) {
                console.log('[DEBUG] 업로드 버튼 찾음, 이벤트 리스너 재설정 시작');
                
                // 기존 이벤트 리스너 모두 제거
                const newUploadBtn = uploadBtn.cloneNode(true);
                uploadBtn.parentNode.replaceChild(newUploadBtn, uploadBtn);
                
                // 이벤트 리스너 등록 (가장 간단하고 확실한 방법)
                // 기존 모든 이벤트 리스너 제거
                newUploadBtn.removeAttribute('onclick');
                newUploadBtn.onclick = null;
                
                // 가장 간단한 방법: onclick 속성에 직접 함수 할당
                newUploadBtn.onclick = function(e) {
                    console.log('[DEBUG] ========== 버튼 onclick 핸들러 직접 호출됨 ==========');
                    if (e) {
                        e.preventDefault();
                        e.stopPropagation();
                    }
                    if (typeof window.handleYouTubeUpload === 'function') {
                        window.handleYouTubeUpload(e);
                    } else if (typeof window.uploadToYouTube === 'function') {
                        window.uploadToYouTube();
                    } else {
                        console.error('[DEBUG] 업로드 함수를 찾을 수 없음');
                        alert('업로드 함수를 찾을 수 없습니다.');
                    }
                };
                
                // addEventListener도 추가
                newUploadBtn.addEventListener('click', function(e) {
                    console.log('[DEBUG] ========== 버튼 addEventListener 핸들러 호출됨 ==========');
                    if (e) {
                        e.preventDefault();
                        e.stopPropagation();
                    }
                    if (typeof window.handleYouTubeUpload === 'function') {
                        window.handleYouTubeUpload(e);
                    } else if (typeof window.uploadToYouTube === 'function') {
                        window.uploadToYouTube();
                    }
                }, { once: false, capture: false });
                
                newUploadBtn.disabled = false; // 버튼 활성화
                console.log('[DEBUG] 업로드 버튼 이벤트 리스너 재설정 완료');
                console.log('[DEBUG] window.uploadToYouTube 존재 여부:', typeof window.uploadToYouTube);
                console.log('[DEBUG] window.handleYouTubeUpload 존재 여부:', typeof window.handleYouTubeUpload);
                console.log('[DEBUG] 버튼 onclick 속성 타입:', typeof newUploadBtn.onclick);
                console.log('[DEBUG] 버튼 disabled 상태:', newUploadBtn.disabled);
                
                // 버튼 클릭 테스트 (프로그래밍 방식)
                console.log('[DEBUG] 버튼 클릭 테스트를 위해 1초 후 자동 클릭 시도...');
                setTimeout(() => {
                    console.log('[DEBUG] 자동 클릭 테스트 시작');
                    const clickEvent = new MouseEvent('click', {
                        bubbles: true,
                        cancelable: true,
                        view: window
                    });
                    newUploadBtn.dispatchEvent(clickEvent);
                }, 1000);
            } else {
                console.error('[DEBUG] uploadYoutubeBtn 요소를 찾을 수 없음');
            }
            
            // 스크롤하여 업로드 섹션으로 이동
            uploadSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        
        // 페이지 로드 시 초기화
        window.addEventListener('load', () => {
            console.log('[DEBUG] 페이지 로드 완료, 이벤트 리스너 등록 시작');
            connectWebSocket();
            
            // 버튼 이벤트 리스너 등록
            const createBtn = document.getElementById('createBtn');
            const refreshBtn = document.getElementById('refreshVideoListBtn');
            const uploadBtn = document.getElementById('uploadYoutubeBtn');
            
            if (createBtn) {
                createBtn.addEventListener('click', createShorts);
                console.log('[DEBUG] createBtn 이벤트 리스너 등록됨');
            } else {
                console.error('[DEBUG] createBtn을 찾을 수 없음');
            }
            
            if (refreshBtn) {
                refreshBtn.addEventListener('click', loadVideoList);
                console.log('[DEBUG] refreshBtn 이벤트 리스너 등록됨');
            } else {
                console.error('[DEBUG] refreshBtn을 찾을 수 없음');
            }
            
            if (uploadBtn) {
                // 기존 이벤트 리스너 제거 후 재등록
                uploadBtn.onclick = null;
                uploadBtn.addEventListener('click', (e) => {
                    console.log('[DEBUG] ========== uploadYoutubeBtn 클릭 이벤트 발생 ==========');
                    e.preventDefault();
                    e.stopPropagation();
                    uploadToYouTube().catch(err => {
                        console.error('[DEBUG] uploadToYouTube 실행 중 오류:', err);
                    });
                });
                // onclick 속성도 설정 (이중 보험)
                uploadBtn.setAttribute('onclick', 'event.preventDefault(); event.stopPropagation(); uploadToYouTube();');
                console.log('[DEBUG] uploadYoutubeBtn 이벤트 리스너 등록됨 (onclick 속성도 설정)');
            } else {
                console.error('[DEBUG] uploadYoutubeBtn을 찾을 수 없음');
            }
            
            loadVideoList(); // 초기 로드
        });
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)


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
    privacy_status: str = Field(default="unlisted", description="공개 설정 (public, unlisted, private)")


async def process_youtube_upload_with_updates(
    video_path: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    privacy_status: str = "unlisted",
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
