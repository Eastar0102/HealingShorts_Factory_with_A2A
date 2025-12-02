@echo off
REM Windows용 개별 에이전트 서버 실행 스크립트

set AGENT_NAME=%1
set PORT=%2

if "%AGENT_NAME%"=="" (
    echo Usage: start_agent.bat ^<agent_name^> ^<port^>
    echo Example: start_agent.bat planner 8001
    exit /b 1
)

set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..
set SERVER_DIR=%PROJECT_ROOT%\server\agents

if "%AGENT_NAME%"=="planner" (
    python "%SERVER_DIR%\planner_server.py"
) else if "%AGENT_NAME%"=="reviewer" (
    python "%SERVER_DIR%\reviewer_server.py"
) else if "%AGENT_NAME%"=="producer" (
    python "%SERVER_DIR%\producer_server.py"
) else if "%AGENT_NAME%"=="uploader" (
    python "%SERVER_DIR%\uploader_server.py"
) else (
    echo Unknown agent: %AGENT_NAME%
    echo Available agents: planner, reviewer, producer, uploader
    exit /b 1
)




