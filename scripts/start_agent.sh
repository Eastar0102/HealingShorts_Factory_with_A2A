#!/bin/bash
# 개별 에이전트 서버 실행 스크립트

AGENT_NAME=$1
PORT=$2

if [ -z "$AGENT_NAME" ] || [ -z "$PORT" ]; then
    echo "Usage: ./start_agent.sh <agent_name> <port>"
    echo "Example: ./start_agent.sh planner 8001"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVER_DIR="$PROJECT_ROOT/server/agents"

case $AGENT_NAME in
    planner)
        python "$SERVER_DIR/planner_server.py"
        ;;
    reviewer)
        python "$SERVER_DIR/reviewer_server.py"
        ;;
    producer)
        python "$SERVER_DIR/producer_server.py"
        ;;
    uploader)
        python "$SERVER_DIR/uploader_server.py"
        ;;
    *)
        echo "Unknown agent: $AGENT_NAME"
        echo "Available agents: planner, reviewer, producer, uploader"
        exit 1
        ;;
esac




