"""
Agent specific configuration settings
将所有硬编码的Agent相关配置集中管理
"""
from pydantic_settings import BaseSettings
from typing import List, Dict, Any, Optional
from pydantic import Field, ConfigDict


class AgentConfig(BaseSettings):
    """Agent配置类 - 管理所有Agent相关的硬编码配置"""
    
    # ==================== 外部Agent配置 ====================
    
    # AutoGLM Agent配置
    autoglm_agent_url: str = Field(
        default="http://8.141.113.229",
        description="AutoGLM Agent的默认URL"
    )
    autoglm_agent_id: str = Field(
        default="autoglm_agent",
        description="AutoGLM Agent的ID"
    )
    
    # Agent Card配置
    agent_card_endpoint: str = Field(
        default="/.well-known/agent-card.json",
        description="Agent Card的标准端点路径"
    )
    
    # ==================== Worker配置 ====================
    
    # Worker进程配置
    default_worker_count: int = Field(
        default=4,
        description="默认Worker进程数量"
    )
    worker_concurrency: int = Field(
        default=3,
        description="每个Worker进程的并发任务数"
    )
    worker_restart_count: int = Field(
        default=2,
        description="重启时的Worker数量"
    )
    
    # Worker队列配置
    celery_queues: List[str] = Field(
        default=["default", "user_tasks", "a2a_requests", "a2a_responses"],
        description="Celery任务队列列表"
    )
    default_queue: str = Field(
        default="default",
        description="默认任务队列"
    )
    
    # ==================== 超时和重试配置 ====================
    
    # HTTP请求超时配置
    external_agent_timeout: int = Field(
        default=30,
        description="外部Agent请求超时时间(秒)"
    )
    agent_card_timeout: int = Field(
        default=10,
        description="获取Agent Card的超时时间(秒)"
    )
    task_query_timeout: int = Field(
        default=10,
        description="任务状态查询超时时间(秒)"
    )
    push_config_timeout: int = Field(
        default=10,
        description="推送配置请求超时时间(秒)"
    )
    
    # 轮询配置
    polling_max_attempts: int = Field(
        default=30,
        description="任务状态轮询最大尝试次数"
    )
    polling_interval: int = Field(
        default=2,
        description="任务状态轮询间隔(秒)"
    )
    
    # Celery任务重试配置
    celery_max_retries: int = Field(
        default=3,
        description="Celery任务最大重试次数"
    )
    
    # Worker进程管理超时
    worker_termination_timeout: int = Field(
        default=10,
        description="Worker进程终止超时时间(秒)"
    )
    
    # ==================== 任务执行配置 ====================
    
    # 任务结果获取超时
    task_result_timeout_short: int = Field(
        default=30,
        description="短任务结果获取超时时间(秒)"
    )
    task_result_timeout_long: int = Field(
        default=60,
        description="长任务结果获取超时时间(秒)"
    )
    
    # ==================== 测试配置 ====================
    
    # 测试服务URL
    test_base_url: str = Field(
        default="http://localhost:8000",
        description="测试用的基础服务URL"
    )
    test_mcp_url: str = Field(
        default="http://localhost:9001",
        description="测试用的MCP服务URL"
    )
    
    # 测试超时配置
    test_timeout_short: int = Field(
        default=10,
        description="短超时测试时间(秒)"
    )
    test_timeout_medium: int = Field(
        default=30,
        description="中等超时测试时间(秒)"
    )
    test_timeout_long: int = Field(
        default=120,
        description="长超时测试时间(秒)"
    )
    
    # 测试重试配置
    test_max_attempts: int = Field(
        default=5,
        description="测试最大重试次数"
    )
    test_wait_interval: int = Field(
        default=5,
        description="测试重试间隔(秒)"
    )
    
    # ==================== WebSocket配置 ====================
    
    # WebSocket重连配置
    ws_max_retries: int = Field(
        default=10,
        description="WebSocket最大重连次数"
    )
    ws_max_retry_delay: float = Field(
        default=60.0,
        description="WebSocket最大重连延迟(秒)"
    )
    ws_heartbeat_interval: float = Field(
        default=30.0,
        description="WebSocket心跳间隔(秒)"
    )
    ws_connection_timeout: float = Field(
        default=10.0,
        description="WebSocket连接超时(秒)"
    )
    ws_ping_timeout: float = Field(
        default=20.0,
        description="WebSocket ping超时(秒)"
    )
    
    # ==================== 终端设备配置 ====================
    
    # 终端设备数据限制
    terminal_max_data_size_mb: int = Field(
        default=10,
        description="终端设备最大数据包大小(MB)"
    )
    terminal_timeout_seconds: int = Field(
        default=30,
        description="终端设备操作超时时间(秒)"
    )
    
    # ==================== 实用方法 ====================
    
    def get_celery_queue_routes(self) -> Dict[str, Dict[str, str]]:
        """获取Celery队列路由配置"""
        return {
            "src.async_execution.tasks.process_user_task": {"queue": "user_tasks"},
            "src.async_execution.tasks.send_a2a_request": {"queue": "a2a_requests"},
            "src.async_execution.tasks.process_a2a_response": {"queue": "a2a_responses"},
        }
    
    def get_test_websocket_urls(self) -> List[str]:
        """获取测试用的WebSocket URL列表"""
        base_ws_url = self.test_base_url.replace("http://", "ws://").replace("https://", "wss://")
        return [
            f"{base_ws_url}/api/terminal-devices/ws/test_device_1",
            f"{base_ws_url}/api/terminal-devices/ws/test_device_2"
        ]
    
    # Pydantic v2 configuration
    model_config = ConfigDict(
        env_file=".env",
        env_prefix="AGENT_",  # 环境变量前缀
        case_sensitive=False,
        extra="ignore"  # 忽略额外字段，避免与主配置冲突
    )


# 全局配置实例
agent_config = AgentConfig()
