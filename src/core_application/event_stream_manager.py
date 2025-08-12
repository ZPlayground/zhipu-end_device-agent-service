"""
Redis Streams 事件流管理器
Redis Streams Event Stream Manager

负责：
1. 使用Redis Streams管理设备数据流
2. 音视频图片等大文件单独存储在文件系统
3. 为LLM Agent提供数据读取接口
4. 自动清理过期数据
"""
import asyncio
import logging
import uuid
import os
import json
import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

from src.data_persistence.terminal_device_models import DataType
from config.settings import settings
from config.redis_config import redis_config

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as redis
except ImportError:
    import redis
    redis.Redis = redis.StrictRedis


class RedisStreamsManager:
    """Redis Streams 事件流管理器"""
    
    def __init__(self):
        # 使用Redis配置
        self.redis_host = redis_config.host
        self.redis_port = redis_config.port
        self.redis_db = redis_config.db
        self.redis_password = redis_config.password
        
        self.redis: Optional[redis.Redis] = None
        self._connected = False
        
        # 文件存储配置
        self.file_storage_dir = Path(redis_config.file_storage_dir)
        self.file_storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 存储策略配置
        self.max_redis_size = redis_config.max_redis_size_bytes
        
        # 流管理
        self.stream_prefix = redis_config.stream_prefix
        self.consumer_group = redis_config.consumer_group
        self.consumer_name = f"agent_{uuid.uuid4().hex[:8]}"
        
        # 清理配置
        self.data_retention_hours = redis_config.data_retention_hours
        self.cleanup_interval_minutes = redis_config.cleanup_interval_minutes
        
        self._cleanup_task = None
        self._running = False
        
        logger.info("✅ Redis Streams 管理器初始化完成")
    
    async def initialize(self):
        """初始化Redis连接"""
        try:
            self.redis = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
                decode_responses=False  # 保持二进制数据
            )
            
            # 测试连接
            await self.redis.ping()
            self._connected = True
            
            # 启动清理任务
            await self.start_cleanup_task()
            
            logger.info(f"✅ Redis Streams 连接成功: {self.redis_host}:{self.redis_port}")
            
        except Exception as e:
            logger.error(f"❌ Redis 连接失败: {e}")
            self._connected = False
            raise
    
    async def close(self):
        """关闭连接"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
        
        if self.redis:
            await self.redis.close()
            self._connected = False
        
        logger.info("🔴 Redis Streams 管理器已关闭")
    
    def start_maintenance(self):
        """启动维护任务（同步方法，用于兼容现有代码）"""
        try:
            logger.info("🔧 启动Redis Streams维护任务...")
            # 异步启动清理任务
            asyncio.create_task(self._start_maintenance_async())
            logger.info("✅ Redis Streams维护任务已启动")
        except Exception as e:
            logger.error(f"❌ 启动维护任务失败: {e}")
    
    async def _start_maintenance_async(self):
        """异步启动维护任务"""
        try:
            # 确保Redis连接已建立
            if not self._connected:
                await self.initialize()
            
            # 启动清理任务
            await self.start_cleanup_task()
            
        except Exception as e:
            logger.error(f"❌ 异步启动维护任务失败: {e}")
    
    def _get_stream_key(self, device_id: str) -> str:
        """获取设备流键名"""
        return f"{self.stream_prefix}{device_id}"
    
    async def add_data_to_stream(
        self,
        device_id: str,
        data_type: DataType,
        content_text: Optional[str] = None,
        content_binary: Optional[bytes] = None,
        content_json: Optional[Dict[str, Any]] = None,
        metadata: Dict[str, Any] = None,
        mime_type: Optional[str] = None
    ) -> bool:
        """添加数据到Redis Stream"""
        if not self._connected:
            logger.error("❌ Redis 未连接，无法添加数据")
            return False
        
        try:
            stream_key = self._get_stream_key(device_id)
            entry_id = str(uuid.uuid4())
            
            # 构建基础数据
            stream_data = {
                "entry_id": entry_id,
                "device_id": device_id,
                "data_type": data_type.value,
                "created_at": datetime.utcnow().isoformat(),
                "metadata": json.dumps(metadata or {})
            }
            
            # 处理不同类型的内容
            if content_text:
                stream_data["content_text"] = content_text
                
            elif content_json:
                stream_data["content_json"] = json.dumps(content_json)
                
            elif content_binary:
                # 大文件检查
                if len(content_binary) > self.max_redis_size:
                    # 存储到文件系统
                    file_info = await self._store_large_file(
                        device_id, entry_id, content_binary, data_type, mime_type
                    )
                    stream_data.update(file_info)
                else:
                    # 小文件直接存储到Redis
                    stream_data["content_binary"] = content_binary
                    if mime_type:
                        stream_data["mime_type"] = mime_type
            
            # 添加到流
            message_id = await self.redis.xadd(stream_key, stream_data)
            
            # 确保消费者组存在
            await self._ensure_consumer_group(stream_key)
            
            logger.debug(f"📝 添加数据到Redis Stream: {device_id}, ID: {message_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 添加数据到Redis Stream失败: {e}")
            return False
    
    async def _store_large_file(
        self,
        device_id: str,
        entry_id: str,
        content: bytes,
        data_type: DataType,
        mime_type: Optional[str]
    ) -> Dict[str, str]:
        """存储大文件到文件系统，返回文件信息"""
        try:
            # 生成文件路径
            file_hash = hashlib.md5(content).hexdigest()
            device_dir = self.file_storage_dir / device_id
            device_dir.mkdir(exist_ok=True)
            
            # 确定文件扩展名
            ext = self._get_file_extension(mime_type, data_type)
            file_path = device_dir / f"{entry_id}_{file_hash}{ext}"
            
            # 保存原文件
            with open(file_path, "wb") as f:
                f.write(content)
            
            file_info = {
                "file_path": str(file_path),
                "file_size": len(content),
                "file_hash": file_hash
            }
            
            if mime_type:
                file_info["mime_type"] = mime_type
            
            logger.info(f"💾 大文件存储: {device_id}, {len(content)}B -> {file_path}")
            return file_info
            
        except Exception as e:
            logger.error(f"❌ 存储大文件失败: {e}")
            return {"error": str(e)}
    
    def _get_file_extension(self, mime_type: Optional[str], data_type: DataType) -> str:
        """根据MIME类型和数据类型确定文件扩展名"""
        if mime_type:
            ext_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "image/webp": ".webp",
                "audio/mpeg": ".mp3",
                "audio/wav": ".wav",
                "audio/ogg": ".ogg",
                "video/mp4": ".mp4",
                "video/webm": ".webm",
                "video/avi": ".avi"
            }
            return ext_map.get(mime_type, ".bin")
        
        # 根据数据类型推断
        type_ext_map = {
            DataType.IMAGE: ".jpg",
            DataType.AUDIO: ".wav",
            DataType.VIDEO: ".mp4"
        }
        return type_ext_map.get(data_type, ".bin")
    
    async def _ensure_consumer_group(self, stream_key: str):
        """确保消费者组存在"""
        try:
            await self.redis.xgroup_create(
                stream_key, self.consumer_group, id="0", mkstream=True
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                logger.error(f"❌ 创建消费者组失败: {e}")
    
    async def read_stream_data(
        self,
        device_id: str,
        count: int = 10,
        block_ms: int = 1000
    ) -> List[Dict[str, Any]]:
        """从Redis Stream读取数据"""
        if not self._connected:
            return []
        
        try:
            stream_key = self._get_stream_key(device_id)
            
            # 确保消费者组存在
            await self._ensure_consumer_group(stream_key)
            
            # 读取数据
            messages = await self.redis.xreadgroup(
                self.consumer_group,
                self.consumer_name,
                {stream_key: ">"},
                count=count,
                block=block_ms
            )
            
            result = []
            for stream, msgs in messages:
                for msg_id, fields in msgs:
                    # 解析消息
                    data = await self._parse_stream_message(fields)
                    data["message_id"] = msg_id.decode()
                    result.append(data)
                    
                    # 确认消息处理
                    await self.redis.xack(stream_key, self.consumer_group, msg_id)
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 读取Stream数据失败: {e}")
            return []
    
    async def _parse_stream_message(self, fields: Dict) -> Dict[str, Any]:
        """解析Stream消息"""
        try:
            data = {}
            
            # 基础字段
            for key, value in fields.items():
                key_str = key.decode() if isinstance(key, bytes) else key
                
                if key_str in ["entry_id", "device_id", "created_at", "mime_type", "file_path"]:
                    data[key_str] = value.decode() if isinstance(value, bytes) else value
                elif key_str == "data_type":
                    data[key_str] = DataType(value.decode() if isinstance(value, bytes) else value)
                elif key_str in ["metadata", "content_json"]:
                    json_str = value.decode() if isinstance(value, bytes) else value
                    data[key_str] = json.loads(json_str)
                elif key_str == "content_text":
                    data[key_str] = value.decode() if isinstance(value, bytes) else value
                elif key_str == "content_binary":
                    data[key_str] = value  # 保持bytes格式
                elif key_str in ["file_size"]:
                    data[key_str] = int(value.decode() if isinstance(value, bytes) else value)
                else:
                    data[key_str] = value.decode() if isinstance(value, bytes) else value
            
            # 如果有文件路径，读取文件内容
            if "file_path" in data:
                try:
                    with open(data["file_path"], "rb") as f:
                        data["file_content"] = f.read()
                except Exception as e:
                    logger.error(f"❌ 读取文件内容失败: {e}")
                    data["file_error"] = str(e)
            
            return data
            
        except Exception as e:
            logger.error(f"❌ 解析消息失败: {e}")
            return {"error": str(e)}
    
    async def get_stream_info(self, device_id: str) -> Dict[str, Any]:
        """获取流信息"""
        if not self._connected:
            return {}
        
        try:
            stream_key = self._get_stream_key(device_id)
            info = await self.redis.xinfo_stream(stream_key)
            
            return {
                "stream_key": stream_key,
                "length": info[b"length"],
                "radix_tree_keys": info[b"radix-tree-keys"],
                "radix_tree_nodes": info[b"radix-tree-nodes"],
                "groups": info[b"groups"],
                "last_generated_id": info[b"last-generated-id"].decode(),
                "first_entry": info[b"first-entry"],
                "last_entry": info[b"last-entry"]
            }
            
        except Exception as e:
            logger.error(f"❌ 获取流信息失败: {e}")
            return {"error": str(e)}
    
    async def start_cleanup_task(self):
        """启动清理任务"""
        if not self._running:
            self._running = True
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("✅ 启动Redis数据清理任务")
    
    async def _cleanup_loop(self):
        """清理循环"""
        while self._running:
            try:
                await self._cleanup_expired_data()
                await asyncio.sleep(self.cleanup_interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 清理任务异常: {e}")
                await asyncio.sleep(60)
    
    async def _cleanup_expired_data(self):
        """清理过期数据"""
        try:
            # 获取所有设备流
            pattern = f"{self.stream_prefix}*"
            stream_keys = await self.redis.keys(pattern)
            
            cleanup_count = 0
            file_cleanup_count = 0
            
            cutoff_time = datetime.utcnow() - timedelta(hours=self.data_retention_hours)
            cutoff_timestamp = int(cutoff_time.timestamp() * 1000)
            
            for stream_key in stream_keys:
                try:
                    # 获取过期消息
                    messages = await self.redis.xrange(
                        stream_key, min="-", max=cutoff_timestamp
                    )
                    
                    for msg_id, fields in messages:
                        # 删除关联的文件
                        if b"file_path" in fields:
                            file_path = Path(fields[b"file_path"].decode())
                            if file_path.exists():
                                file_path.unlink()
                                file_cleanup_count += 1
                        
                        # 从流中删除消息
                        await self.redis.xdel(stream_key, msg_id)
                        cleanup_count += 1
                        
                except Exception as e:
                    logger.error(f"❌ 清理流失败 {stream_key}: {e}")
            
            if cleanup_count > 0:
                logger.info(f"🧹 清理完成: {cleanup_count} 条消息, {file_cleanup_count} 个文件")
                
        except Exception as e:
            logger.error(f"❌ 清理过期数据失败: {e}")


# 全局实例
event_stream_manager = RedisStreamsManager()
