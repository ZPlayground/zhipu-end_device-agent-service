"""
Redis 配置管理
Redis Configuration Management

用于Redis Streams的配置设置
"""
import os
from typing import Optional
from urllib.parse import urlparse


class RedisConfig:
    """Redis 配置类"""
    
    def __init__(self):
        # 首先检查是否有REDIS_URL环境变量
        redis_url = os.getenv("REDIS_URL")
        
        if redis_url:
            # 解析REDIS_URL
            parsed = urlparse(redis_url)
            self.host = parsed.hostname or "localhost"
            self.port = parsed.port or 6379
            self.db = int(parsed.path.lstrip('/')) if parsed.path and parsed.path != '/' else 0
            self.password = parsed.password
        else:
            # 使用独立的环境变量
            self.host = os.getenv("REDIS_HOST", "localhost")
            self.port = int(os.getenv("REDIS_PORT", "6379"))
            self.db = int(os.getenv("REDIS_DB", "0"))
            self.password = os.getenv("REDIS_PASSWORD", None)
        
        # 连接池配置
        self.max_connections = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))
        self.connection_timeout = int(os.getenv("REDIS_CONNECTION_TIMEOUT", "10"))
        
        # Stream 配置
        self.stream_prefix = os.getenv("REDIS_STREAM_PREFIX", "device_stream:")
        self.consumer_group = os.getenv("REDIS_CONSUMER_GROUP", "llm_agents")
        
        # 数据保留配置
        self.data_retention_hours = int(os.getenv("REDIS_DATA_RETENTION_HOURS", "24"))
        self.cleanup_interval_minutes = int(os.getenv("REDIS_CLEANUP_INTERVAL_MINUTES", "60"))
        
        # 文件存储配置
        self.max_redis_size_mb = float(os.getenv("REDIS_MAX_SIZE_MB", "1"))  # 1MB
        self.file_storage_dir = os.getenv("FILE_STORAGE_DIR", "data/device_files")
    
    @property
    def max_redis_size_bytes(self) -> int:
        """Redis最大存储字节数"""
        return int(self.max_redis_size_mb * 1024 * 1024)
    
    def get_connection_params(self) -> dict:
        """获取Redis连接参数"""
        params = {
            "host": self.host,
            "port": self.port,
            "db": self.db,
            "max_connections": self.max_connections,
            "socket_timeout": self.connection_timeout,
        }
        
        if self.password:
            params["password"] = self.password
        
        return params


# 全局配置实例
redis_config = RedisConfig()
