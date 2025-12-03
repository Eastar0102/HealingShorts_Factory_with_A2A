"""
모든 A2A 에이전트 서버를 한 번에 실행하는 스크립트
"""

import subprocess
import sys
import os
import time
import socket
from pathlib import Path

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent


def is_port_in_use(port: int) -> bool:
    """포트가 사용 중인지 확인"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('localhost', port))
            return False
        except OSError:
            return True


def check_server_health(port: int, timeout: int = 2) -> bool:
    """서버 헬스 체크"""
    import urllib.request
    import urllib.error
    try:
        response = urllib.request.urlopen(f"http://localhost:{port}/health", timeout=timeout)
        return response.getcode() == 200
    except:
        return False


def start_agent(module_name: str, port: int, agent_name: str):
    """에이전트 서버 시작"""
    print(f"Starting {agent_name} on port {port}...")
    
    # Python 모듈로 실행 (python -m server.agents.planner_server)
    process = subprocess.Popen(
        [sys.executable, "-m", module_name],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    return process, agent_name


def main():
    """모든 에이전트 서버 시작"""
    print("=" * 60)
    print("Starting all A2A Agent Servers")
    print("=" * 60)
    
    processes = []
    
    # 각 에이전트 서버 시작
    agents = [
        ("server.agents.planner_server", 8001, "PlannerAgent"),
        ("server.agents.reviewer_server", 8002, "ReviewerAgent"),
        ("server.agents.producer_server", 8003, "ProducerAgent"),
        ("server.agents.uploader_server", 8004, "UploaderAgent"),
    ]
    
    for module_name, port, agent_name in agents:
        try:
            # 포트가 이미 사용 중이고 서버가 정상 작동 중인지 확인
            if is_port_in_use(port):
                if check_server_health(port, timeout=1):
                    print(f"✓ {agent_name} already running on port {port} (reusing existing server)")
                    # 기존 서버를 사용하므로 더미 프로세스 추가 (종료 시 제외)
                    processes.append((None, agent_name, port))
                    continue
                else:
                    print(f"⚠ Port {port} is in use but server not responding. Starting new instance...")
            
            process, name = start_agent(module_name, port, agent_name)
            processes.append((process, name, port))
            
            # 서버 시작 대기 (초기 대기)
            time.sleep(2)
            
            # 프로세스가 즉시 종료되었는지 확인 (실제 에러인 경우)
            if process.poll() is not None:
                # 프로세스가 종료된 경우 에러 출력 확인
                try:
                    stdout, _ = process.communicate(timeout=1)
                    # 포트 충돌 에러인지 확인
                    if stdout and ('10048' in stdout or 'address already in use' in stdout.lower() or '이미 사용 중' in stdout):
                        # 포트 충돌이지만 기존 서버가 작동 중일 수 있음
                        if check_server_health(port, timeout=1):
                            print(f"✓ {agent_name} already running on port {port} (port conflict resolved)")
                            # 기존 프로세스 제거하고 None으로 대체
                            if (process, name, port) in processes:
                                processes.remove((process, name, port))
                            processes.append((None, agent_name, port))
                            continue
                    
                    print(f"❌ {agent_name} failed to start!")
                    if stdout:
                        # FutureWarning은 무시하고 실제 에러만 표시
                        error_lines = [line for line in stdout.split('\n') 
                                     if 'Traceback' in line or ('Error' in line and 'FutureWarning' not in line) or 'Exception' in line]
                        if error_lines:
                            print(f"   Error: {error_lines[0][:200]}")
                except:
                    pass
                # 실패한 프로세스 제거
                if (process, name, port) in processes:
                    processes.remove((process, name, port))
                continue
            
            # 헬스 체크로 서버가 실제로 응답하는지 확인 (재시도 포함)
            import urllib.request
            import urllib.error
            health_check_passed = False
            max_retries = 3
            
            for attempt in range(max_retries):
                try:
                    response = urllib.request.urlopen(f"http://localhost:{port}/health", timeout=2)
                    if response.getcode() == 200:
                        health_check_passed = True
                        print(f"✓ {agent_name} started successfully on port {port}")
                        break
                except (urllib.error.URLError, Exception):
                    # 프로세스가 여전히 실행 중이면 재시도
                    if process.poll() is None:
                        if attempt < max_retries - 1:
                            time.sleep(1)  # 재시도 전 대기
                            continue
                        else:
                            # 모든 재시도 실패했지만 프로세스는 실행 중
                            health_check_passed = True
                            print(f"✓ {agent_name} started on port {port} (health check timeout, but process running)")
                            break
                    else:
                        # 프로세스가 종료됨
                        print(f"❌ {agent_name} failed to start (process terminated)")
                        if (process, name, port) in processes:
                            processes.remove((process, name, port))
                        break
            
            # 헬스 체크 실패하고 프로세스도 종료된 경우 제외
            if not health_check_passed and process.poll() is not None:
                if (process, name, port) in processes:
                    processes.remove((process, name, port))
                    
        except Exception as e:
            print(f"❌ Failed to start {agent_name}: {e}")
    
    # 실제로 시작된 서버만 표시 (None은 기존 서버, poll()이 None인 것은 실행 중인 프로세스)
    running_servers = [(p, n, port) for p, n, port in processes if p is None or p.poll() is None]
    
    if not running_servers:
        print("\n❌ No agents started successfully!")
        return
    
    print("\n" + "=" * 60)
    print(f"✓ {len(running_servers)} agent(s) started successfully!")
    print("=" * 60)
    print("\nAgent URLs:")
    for _, name, port in running_servers:
        print(f"  - {name}: http://localhost:{port}")
        print(f"    AgentCard: http://localhost:{port}/a2a/agent_card")
        print(f"    Tasks: http://localhost:{port}/a2a/tasks")
    print("\nPress Ctrl+C to stop all servers...\n")
    
    try:
        # 모든 프로세스가 종료될 때까지 대기 (None인 경우는 기존 서버이므로 대기하지 않음)
        for process, name, _ in running_servers:
            if process is not None:
                process.wait()
    except KeyboardInterrupt:
        print("\n\nStopping all agents...")
        for process, name, _ in running_servers:
            if process is not None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                    print(f"  ✓ {name} stopped")
                except:
                    process.kill()
                    print(f"  ✓ {name} force stopped")
            else:
                print(f"  ⚠ {name} was already running (not stopped by this script)")
        print("\nAll agents stopped.")


if __name__ == "__main__":
    main()

