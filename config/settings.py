"""
Application Configuration Settings
"""
from pydantic_settings import BaseSettings
from typing import Optional, Tuple


class Settings(BaseSettings):
    # 应用基础配置
    app_name: str = "A2A Agent Service"
    app_version: str = "1.0.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    
    # 数据库配置
    # database_url: str = "postgresql://user:password@localhost/a2a_agent_db"
    # SQLite 替代方案（Docker和宿主机兼容）
    database_url: str = "sqlite+aiosqlite:///./data/a2a_agent.db"
    
    # Redis配置 (消息队列)
    redis_url: str = "redis://localhost:6379"
    
    # JWT配置
    secret_key: str = "change-this-secret-key-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # LLM服务配置
    openai_api_key: Optional[str] = None
    # 替换Anthropic为智谱AI
    zhipu_api_key: Optional[str] = None

    # 模型与开关（集中配置）
    enable_gpt5_preview: bool = False  # 通过环境变量 ENABLE_GPT5_PREVIEW 启用
    openai_chat_model: str = "gpt-4"
    openai_intent_model: str = "gpt-4.1"
    # 预览模型名称，可通过环境变量覆盖（如 OPENAI_CHAT_MODEL_PREVIEW）
    openai_chat_model_preview: Optional[str] = "gpt-5-preview"
    openai_intent_model_preview: Optional[str] = "gpt-5-preview"
    
    # A2A Agent配置
    a2a_webhook_secret: str = "change-this-webhook-secret-in-production"
    a2a_base_url: str = "http://localhost:8000"
    
    # 事件流配置
    event_stream_backend: str = "memory"  # memory, redis, rabbitmq, kafka
    event_stream_max_size_mb: float = 100.0
    event_stream_max_entries: int = 1000
    event_stream_ttl_days: int = 7
    event_stream_maintenance_interval: int = 300  # 秒
    
    # RabbitMQ配置 (如果使用rabbitmq后端)
    rabbitmq_url: str = "amqp://localhost/"
    
    # MCP测试服务配置
    mcp_test_port: int = 9001
    mcp_test_host: str = "localhost"
    
    # 日志配置
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        # 自动将环境变量转换为小写
        case_sensitive = False

    # 实用方法：根据开关返回OpenAI模型
    def get_openai_models(self) -> Tuple[str, str]:
        chat = self.openai_chat_model
        intent = self.openai_intent_model
        if self.enable_gpt5_preview:
            chat = (self.openai_chat_model_preview or chat)
            intent = (self.openai_intent_model_preview or intent)
        return chat, intent
    
    # 获取完整的MCP测试服务URL
    def get_mcp_test_url(self) -> str:
        return f"http://{self.mcp_test_host}:{self.mcp_test_port}"


settings = Settings()
