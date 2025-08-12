"""
WebSocket数据传输管理器
WebSocket Data Transmission Manager

负责：
1. 管理终端设备的WebSocket连接
2. 实时接收文本/音频/图片/视频数据
3. 数据缓存和分发到EventStream
4. 多媒体数据处理和存储
"""
import asyncio
import json
import logging
import base64
import mimetypes
import os
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from pathlib import Path

from src.data_persistence.terminal_device_models import DataType
from src.core_application.terminal_device_manager import terminal_device_manager
from src.core_application.event_stream_manager import event_stream_manager
from config.settings import settings


logger = logging.getLogger(__name__)


class DeviceWebSocketConnection:
    """设备WebSocket连接"""
    
    def __init__(self, websocket: WebSocket, device_id: str):
        self.websocket = websocket
        self.device_id = device_id
        self.connected_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
        self.data_received_count = 0
        self.total_bytes_received = 0
    
    async def send_json(self, data: Dict[str, Any]):
        """发送JSON消息"""
        try:
            await self.websocket.send_text(json.dumps(data))
            self.last_activity = datetime.utcnow()
        except Exception as e:
            logger.error(f"❌ 发送消息失败 {self.device_id}: {e}")
            raise
    
    async def receive_json(self) -> Dict[str, Any]:
        """接收JSON消息"""
        try:
            data = await self.websocket.receive_text()
            self.last_activity = datetime.utcnow()
            self.data_received_count += 1
            self.total_bytes_received += len(data.encode('utf-8'))
            return json.loads(data)
        except Exception as e:
            logger.error(f"❌ 接收消息失败 {self.device_id}: {e}")
            raise
    
    async def receive_bytes(self) -> bytes:
        """接收二进制数据"""
        try:
            data = await self.websocket.receive_bytes()
            self.last_activity = datetime.utcnow()
            self.data_received_count += 1
            self.total_bytes_received += len(data)
            return data
        except Exception as e:
            logger.error(f"❌ 接收二进制数据失败 {self.device_id}: {e}")
            raise


class WebSocketDataManager:
    """WebSocket数据传输管理器"""
    
    def __init__(self):
        self.active_connections: Dict[str, DeviceWebSocketConnection] = {}
        self.data_upload_dir = Path("data/uploads")
        self.data_upload_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_size_mb = 50  # 最大文件大小
        
        logger.info("✅ WebSocket数据管理器初始化完成")
    
    async def connect_device(self, websocket: WebSocket, device_id: str):
        """连接设备WebSocket"""
        try:
            await websocket.accept()
            
            # 验证设备是否已注册
            device = terminal_device_manager.get_device(device_id)
            if not device:
                await websocket.close(code=4001, reason="Device not registered")
                return False
            
            # 创建连接
            connection = DeviceWebSocketConnection(websocket, device_id)
            self.active_connections[device_id] = connection
            
            # 更新设备状态
            terminal_device_manager.update_device_status(device_id, True)
            
            # 发送连接确认
            await connection.send_json({
                "type": "connection_established",
                "device_id": device_id,
                "server_time": datetime.utcnow().isoformat(),
                "supported_data_types": device.supported_data_types,
                "max_data_size_mb": device.max_data_size_mb
            })
            
            logger.info(f"✅ 设备连接成功: {device_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 设备连接失败 {device_id}: {e}")
            return False
    
    async def disconnect_device(self, device_id: str):
        """断开设备连接"""
        try:
            if device_id in self.active_connections:
                connection = self.active_connections.pop(device_id)
                
                # 更新设备状态
                terminal_device_manager.update_device_status(device_id, False)
                
                logger.info(f"🔴 设备断开连接: {device_id}")
                
        except Exception as e:
            logger.error(f"❌ 设备断开连接失败 {device_id}: {e}")
    
    async def handle_device_data(self, device_id: str):
        """处理设备数据传输"""
        connection = self.active_connections.get(device_id)
        if not connection:
            logger.error(f"❌ 连接不存在: {device_id}")
            return
        
        try:
            while True:
                try:
                    # 尝试接收消息
                    message = await asyncio.wait_for(
                        connection.websocket.receive(),
                        timeout=30.0  # 30秒超时
                    )
                    
                    if message.get("type") == "websocket.disconnect":
                        break
                    
                    # 处理不同类型的消息
                    if "text" in message:
                        await self._handle_text_data(device_id, message["text"])
                    elif "bytes" in message:
                        await self._handle_binary_data(device_id, message["bytes"])
                    
                    # 发送心跳确认
                    if connection.data_received_count % 10 == 0:
                        await connection.send_json({
                            "type": "heartbeat",
                            "received_count": connection.data_received_count,
                            "total_bytes": connection.total_bytes_received
                        })
                    
                except asyncio.TimeoutError:
                    # 发送心跳检查
                    await connection.send_json({
                        "type": "ping",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
                except WebSocketDisconnect:
                    logger.info(f"🔴 设备主动断开: {device_id}")
                    break
                    
        except Exception as e:
            logger.error(f"❌ 处理设备数据失败 {device_id}: {e}")
        finally:
            await self.disconnect_device(device_id)
    
    async def _handle_text_data(self, device_id: str, text_data: str):
        """处理文本数据"""
        try:
            # 尝试解析JSON
            try:
                data = json.loads(text_data)
                data_type = data.get("type", "text")
                content = data.get("content", text_data)
                metadata = data.get("metadata", {})
            except json.JSONDecodeError:
                # 纯文本数据
                data_type = "text"
                content = text_data
                metadata = {}
            
            # 确定数据类型
            if data_type in ["sensor_data", "json_data"]:
                data_type_enum = DataType.JSON_DATA
                content_json = data if isinstance(data, dict) else {"text": content}
                content_text = json.dumps(content_json, ensure_ascii=False)
            else:
                data_type_enum = DataType.TEXT
                content_json = metadata
                content_text = str(content)
            
            # 发送到事件流
            await event_stream_manager.add_data_to_stream(
                device_id=device_id,
                data_type=data_type_enum,
                content_text=content_text,
                content_json=content_json,
                metadata={
                    "source": "websocket",
                    "original_type": data_type,
                    **metadata
                }
            )
            
            logger.debug(f"📝 处理文本数据: {device_id}, 长度: {len(content_text)}")
            
        except Exception as e:
            logger.error(f"❌ 处理文本数据失败 {device_id}: {e}")
    
    async def _handle_binary_data(self, device_id: str, binary_data: bytes):
        """处理二进制数据"""
        try:
            # 尝试解析包头（前256字节）
            header_size = min(256, len(binary_data))
            header = binary_data[:header_size]
            
            # 检查是否是多媒体数据包
            if header.startswith(b'MEDIA:'):
                await self._handle_media_data(device_id, binary_data)
            else:
                # 通用二进制数据
                await self._handle_generic_binary(device_id, binary_data)
            
        except Exception as e:
            logger.error(f"❌ 处理二进制数据失败 {device_id}: {e}")
    
    async def _handle_media_data(self, device_id: str, media_data: bytes):
        """处理多媒体数据"""
        try:
            # 解析媒体数据包格式: MEDIA:TYPE:FILENAME:SIZE:DATA
            header_end = media_data.find(b'\n')
            if header_end == -1:
                raise ValueError("Invalid media data format")
            
            header = media_data[:header_end].decode('utf-8')
            data_content = media_data[header_end + 1:]
            
            parts = header.split(':')
            if len(parts) < 4 or parts[0] != 'MEDIA':
                raise ValueError("Invalid media header format")
            
            media_type = parts[1]  # audio, image, video
            filename = parts[2]
            declared_size = int(parts[3])
            
            if len(data_content) != declared_size:
                logger.warning(f"⚠️ 数据大小不匹配: 声明{declared_size}, 实际{len(data_content)}")
            
            # 检查文件大小限制
            if len(data_content) > self.max_file_size_mb * 1024 * 1024:
                raise ValueError(f"File too large: {len(data_content)} bytes")
            
            # 确定数据类型
            data_type_map = {
                "audio": DataType.AUDIO,
                "image": DataType.IMAGE,
                "video": DataType.VIDEO
            }
            data_type = data_type_map.get(media_type.lower(), DataType.BINARY)
            
            # 保存文件
            file_path = await self._save_media_file(device_id, filename, data_content)
            
            # 检测MIME类型
            mime_type = mimetypes.guess_type(filename)[0] or f"{media_type}/unknown"
            
            # 发送原始媒体数据到事件流（不在此阶段进行音频转录）
            await event_stream_manager.add_data_to_stream(
                device_id=device_id,
                data_type=data_type,
                content_binary=data_content,
                file_path=str(file_path),
                metadata={
                    "source": "websocket",
                    "media_type": media_type,
                    "filename": filename,
                    "mime_type": mime_type,
                    "size_bytes": len(data_content)
                }
            )
            
            logger.info(f"📁 处理多媒体数据: {device_id}, {media_type}, {filename}, {len(data_content)} bytes")
            
        except Exception as e:
            logger.error(f"❌ 处理多媒体数据失败 {device_id}: {e}")
    
    async def _handle_generic_binary(self, device_id: str, binary_data: bytes):
        """处理通用二进制数据"""
        try:
            # 发送到事件流
            await event_stream_manager.add_data_to_stream(
                device_id=device_id,
                data_type=DataType.BINARY,
                content_binary=binary_data,
                metadata={
                    "source": "websocket",
                    "size_bytes": len(binary_data)
                }
            )
            
            logger.debug(f"📦 处理二进制数据: {device_id}, {len(binary_data)} bytes")
            
        except Exception as e:
            logger.error(f"❌ 处理通用二进制数据失败 {device_id}: {e}")
    
    async def _save_media_file(self, device_id: str, filename: str, data: bytes) -> Path:
        """保存多媒体文件"""
        try:
            # 创建设备专用目录
            device_dir = self.data_upload_dir / device_id
            device_dir.mkdir(exist_ok=True)
            
            # 生成唯一文件名
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            file_ext = Path(filename).suffix
            unique_filename = f"{timestamp}_{filename}"
            file_path = device_dir / unique_filename
            
            # 异步写入文件
            with open(file_path, 'wb') as f:
                f.write(data)
            
            return file_path
            
        except Exception as e:
            logger.error(f"❌ 保存媒体文件失败 {device_id}: {e}")
            raise
    
    async def send_to_device(self, device_id: str, message: Dict[str, Any]) -> bool:
        """向设备发送消息"""
        connection = self.active_connections.get(device_id)
        if not connection:
            logger.warning(f"⚠️ 设备未连接: {device_id}")
            return False
        
        try:
            await connection.send_json(message)
            return True
        except Exception as e:
            logger.error(f"❌ 发送消息到设备失败 {device_id}: {e}")
            return False
    
    async def broadcast_to_devices(self, message: Dict[str, Any], device_ids: List[str] = None):
        """广播消息到设备"""
        target_connections = self.active_connections
        if device_ids:
            target_connections = {
                device_id: conn for device_id, conn in self.active_connections.items()
                if device_id in device_ids
            }
        
        failed_devices = []
        for device_id, connection in target_connections.items():
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"❌ 广播到设备失败 {device_id}: {e}")
                failed_devices.append(device_id)
        
        if failed_devices:
            logger.warning(f"⚠️ 广播失败的设备: {failed_devices}")
    
    def get_connection_status(self) -> Dict[str, Any]:
        """获取连接状态"""
        return {
            "total_connections": len(self.active_connections),
            "connected_devices": list(self.active_connections.keys()),
            "connection_details": {
                device_id: {
                    "connected_at": conn.connected_at.isoformat(),
                    "last_activity": conn.last_activity.isoformat(),
                    "data_received_count": conn.data_received_count,
                    "total_bytes_received": conn.total_bytes_received
                }
                for device_id, conn in self.active_connections.items()
            }
        }
    
    async def cleanup_inactive_connections(self, inactive_threshold_minutes: int = 10):
        """清理不活跃的连接"""
        from datetime import timedelta
        
        threshold_time = datetime.utcnow() - timedelta(minutes=inactive_threshold_minutes)
        inactive_devices = []
        
        for device_id, connection in self.active_connections.items():
            if connection.last_activity < threshold_time:
                inactive_devices.append(device_id)
        
        for device_id in inactive_devices:
            logger.info(f"🧹 清理不活跃连接: {device_id}")
            await self.disconnect_device(device_id)
        
        return len(inactive_devices)


# 全局实例
websocket_data_manager = WebSocketDataManager()
