"""
A2A 에이전트 설정
각 에이전트의 URL 및 포트 설정을 관리합니다.
"""

import os
from typing import Dict, Optional


class A2AConfig:
    """A2A 에이전트 설정"""
    
    # 기본 포트 설정
    DEFAULT_PLANNER_PORT = 8001
    DEFAULT_REVIEWER_PORT = 8002
    DEFAULT_PRODUCER_PORT = 8003
    DEFAULT_UPLOADER_PORT = 8004
    DEFAULT_ORCHESTRATOR_PORT = 8000
    
    # 기본 호스트
    DEFAULT_HOST = "0.0.0.0"
    
    @staticmethod
    def get_planner_url() -> str:
        """PlannerAgent URL 반환"""
        base_url = os.getenv("PLANNER_AGENT_URL")
        if base_url:
            return base_url
        port = int(os.getenv("PLANNER_PORT", A2AConfig.DEFAULT_PLANNER_PORT))
        return f"http://localhost:{port}"
    
    @staticmethod
    def get_reviewer_url() -> str:
        """ReviewerAgent URL 반환"""
        base_url = os.getenv("REVIEWER_AGENT_URL")
        if base_url:
            return base_url
        port = int(os.getenv("REVIEWER_PORT", A2AConfig.DEFAULT_REVIEWER_PORT))
        return f"http://localhost:{port}"
    
    @staticmethod
    def get_producer_url() -> str:
        """ProducerAgent URL 반환"""
        base_url = os.getenv("PRODUCER_AGENT_URL")
        if base_url:
            return base_url
        port = int(os.getenv("PRODUCER_PORT", A2AConfig.DEFAULT_PRODUCER_PORT))
        return f"http://localhost:{port}"
    
    @staticmethod
    def get_uploader_url() -> str:
        """UploaderAgent URL 반환"""
        base_url = os.getenv("UPLOADER_AGENT_URL")
        if base_url:
            return base_url
        port = int(os.getenv("UPLOADER_PORT", A2AConfig.DEFAULT_UPLOADER_PORT))
        return f"http://localhost:{port}"
    
    @staticmethod
    def get_all_agent_urls() -> Dict[str, str]:
        """모든 에이전트 URL 반환"""
        return {
            "planner": A2AConfig.get_planner_url(),
            "reviewer": A2AConfig.get_reviewer_url(),
            "producer": A2AConfig.get_producer_url(),
            "uploader": A2AConfig.get_uploader_url()
        }




