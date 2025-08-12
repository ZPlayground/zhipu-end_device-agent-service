#!/usr/bin/env python3
"""
WebSocket重连管理器
WebSocket Reconnection Manager

提供可靠的WebSocket连接管理，包括：
1. 自动断线重连
2. 指数退避重试机制
3. 连接状态监控
4. 连接健康检查
"""
import asyncio
import json
import logging
import time
import websockets
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """连接状态枚举"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    STOPPED = "stopped"


class ConnectionStats:
    """连接统计信息"""
    
    def __init__(self):
        self.total_connections = 0
        self.successful_connections = 0
        self.failed_connections = 0
        self.total_reconnections = 0
        self.current_connection_start = None
        self.last_disconnect_time = None
        self.total_uptime = timedelta()
        self.data_sent_count = 0
        self.data_received_count = 0
        self.bytes_sent = 0
        self.bytes_received = 0
    
    def connection_started(self):
        """记录连接开始"""
        self.total_connections += 1
        self.current_connection_start = datetime.now()
    
    def connection_success(self):
        """记录连接成功"""
        self.successful_connections += 1
    
    def connection_failed(self):
        """记录连接失败"""
        self.failed_connections += 1
    
    def reconnection_attempt(self):
        """记录重连尝试"""
        self.total_reconnections += 1
    
    def connection_ended(self):
        """记录连接结束"""
        if self.current_connection_start:
            uptime = datetime.now() - self.current_connection_start
            self.total_uptime += uptime
            self.current_connection_start = None
        self.last_disconnect_time = datetime.now()
    
    def data_sent(self, size: int):
        """记录发送数据"""
        self.data_sent_count += 1
        self.bytes_sent += size
    
    def data_received(self, size: int):
        """记录接收数据"""
        self.data_received_count += 1
        self.bytes_received += size
    
    def get_stats_dict(self) -> Dict[str, Any]:
        """获取统计信息字典"""
        current_uptime = timedelta()
        if self.current_connection_start:
            current_uptime = datetime.now() - self.current_connection_start
        
        total_uptime = self.total_uptime + current_uptime
        
        return {
            "total_connections": self.total_connections,
            "successful_connections": self.successful_connections,
            "failed_connections": self.failed_connections,
            "success_rate": (
                self.successful_connections / max(self.total_connections, 1) * 100
            ),
            "total_reconnections": self.total_reconnections,
            "current_uptime_seconds": current_uptime.total_seconds(),
            "total_uptime_seconds": total_uptime.total_seconds(),
            "last_disconnect": (
                self.last_disconnect_time.isoformat() 
                if self.last_disconnect_time else None
            ),
            "data_sent_count": self.data_sent_count,
            "data_received_count": self.data_received_count,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "avg_bytes_per_send": (
                self.bytes_sent / max(self.data_sent_count, 1)
            ),
            "avg_bytes_per_receive": (
                self.bytes_received / max(self.data_received_count, 1)
            )
        }


class WebSocketReconnector:
    """WebSocket断线重连管理器"""
    
    def __init__(
        self,
        url: str,
        max_retries: int = 10,
        initial_retry_delay: float = 1.0,
        max_retry_delay: float = 60.0,
        backoff_multiplier: float = 2.0,
        heartbeat_interval: float = 30.0,
        connection_timeout: float = 10.0,
        ping_timeout: float = 20.0
    ):
        """
        初始化重连管理器
        
        Args:
            url: WebSocket连接URL
            max_retries: 最大重试次数
            initial_retry_delay: 初始重试延迟（秒）
            max_retry_delay: 最大重试延迟（秒）
            backoff_multiplier: 退避倍数
            heartbeat_interval: 心跳间隔（秒）
            connection_timeout: 连接超时（秒）
            ping_timeout: ping超时（秒）
        """
        self.url = url
        self.max_retries = max_retries
        self.initial_retry_delay = initial_retry_delay
        self.max_retry_delay = max_retry_delay
        self.backoff_multiplier = backoff_multiplier
        self.heartbeat_interval = heartbeat_interval
        self.connection_timeout = connection_timeout
        self.ping_timeout = ping_timeout
        
        # 连接状态
        self.state = ConnectionState.DISCONNECTED
        self.websocket: Optional[websockets.WebSocketServerProtocol] = None
        self.retry_count = 0
        self.should_reconnect = True
        self.is_manual_disconnect = False
        
        # 统计信息
        self.stats = ConnectionStats()
        
        # 回调函数
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_message: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None
        self.on_state_changed: Optional[Callable[[ConnectionState], None]] = None
        
        # 任务管理
        self.connection_task: Optional[asyncio.Task] = None
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.message_queue = asyncio.Queue()
        self.send_task: Optional[asyncio.Task] = None
        
        logger.info(f"🔧 WebSocket重连管理器初始化")
        logger.info(f"   URL: {self.url}")
        logger.info(f"   最大重试: {self.max_retries}")
        logger.info(f"   重试延迟: {self.initial_retry_delay}s - {self.max_retry_delay}s")
        logger.info(f"   心跳间隔: {self.heartbeat_interval}s")
    
    def _set_state(self, new_state: ConnectionState):
        """设置连接状态"""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            logger.info(f"🔄 连接状态变更: {old_state.value} → {new_state.value}")
            
            if self.on_state_changed:
                try:
                    self.on_state_changed(new_state)
                except Exception as e:
                    logger.error(f"❌ 状态变更回调异常: {e}")
    
    async def connect(self) -> bool:
        """启动连接（带重连机制）"""
        if self.connection_task and not self.connection_task.done():
            logger.warning("⚠️ 连接任务已在运行")
            return False
        
        self.should_reconnect = True
        self.is_manual_disconnect = False
        self.connection_task = asyncio.create_task(self._connection_loop())
        
        # 等待首次连接尝试完成
        try:
            await asyncio.wait_for(self._wait_for_connection(), timeout=30.0)
            return self.state == ConnectionState.CONNECTED
        except asyncio.TimeoutError:
            logger.error("❌ 连接超时")
            return False
    
    async def _wait_for_connection(self):
        """等待连接建立"""
        while self.state in [ConnectionState.DISCONNECTED, ConnectionState.CONNECTING]:
            await asyncio.sleep(0.1)
    
    async def disconnect(self):
        """主动断开连接"""
        logger.info("🔌 主动断开连接")
        self.should_reconnect = False
        self.is_manual_disconnect = True
        
        # 停止所有任务
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self.send_task:
            self.send_task.cancel()
            try:
                await self.send_task
            except asyncio.CancelledError:
                pass
        
        # 关闭WebSocket连接
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error(f"❌ 关闭WebSocket异常: {e}")
        
        # 停止连接循环
        if self.connection_task:
            self.connection_task.cancel()
            try:
                await self.connection_task
            except asyncio.CancelledError:
                pass
        
        self._set_state(ConnectionState.STOPPED)
        logger.info("✅ 连接已断开")
    
    async def _connection_loop(self):
        """连接循环（包含重连逻辑）"""
        while self.should_reconnect:
            try:
                await self._connect_once()
                
                if self.state == ConnectionState.CONNECTED:
                    # 重置重试计数
                    self.retry_count = 0
                    
                    # 启动相关任务
                    self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                    self.send_task = asyncio.create_task(self._send_loop())
                    
                    # 等待连接断开
                    await self._handle_connection()
                    
                    # 清理任务
                    if self.heartbeat_task:
                        self.heartbeat_task.cancel()
                    if self.send_task:
                        self.send_task.cancel()
                    
                    self.stats.connection_ended()
                
                # 如果需要重连且未达到最大重试次数
                if self.should_reconnect and not self.is_manual_disconnect:
                    if self.retry_count < self.max_retries:
                        delay = self._calculate_retry_delay()
                        logger.info(f"🔄 {delay:.1f}秒后尝试重连 (尝试 {self.retry_count + 1}/{self.max_retries})")
                        
                        self._set_state(ConnectionState.RECONNECTING)
                        await asyncio.sleep(delay)
                        
                        self.retry_count += 1
                        self.stats.reconnection_attempt()
                    else:
                        logger.error(f"❌ 重连失败，已达到最大重试次数: {self.max_retries}")
                        self._set_state(ConnectionState.FAILED)
                        break
                else:
                    break
                    
            except asyncio.CancelledError:
                logger.info("🛑 连接循环被取消")
                break
            except Exception as e:
                logger.error(f"❌ 连接循环异常: {e}")
                await asyncio.sleep(5)
    
    def _calculate_retry_delay(self) -> float:
        """计算重试延迟（指数退避）"""
        delay = self.initial_retry_delay * (self.backoff_multiplier ** self.retry_count)
        return min(delay, self.max_retry_delay)
    
    async def _connect_once(self):
        """单次连接尝试"""
        try:
            self._set_state(ConnectionState.CONNECTING)
            self.stats.connection_started()
            
            logger.info(f"🔗 连接WebSocket: {self.url}")
            
            # 建立WebSocket连接
            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    self.url,
                    ping_interval=self.heartbeat_interval,
                    ping_timeout=self.ping_timeout,
                    close_timeout=10
                ),
                timeout=self.connection_timeout
            )
            
            # 等待连接确认
            confirmation = await asyncio.wait_for(
                self.websocket.recv(),
                timeout=10.0
            )
            
            confirm_data = json.loads(confirmation)
            if confirm_data.get("type") == "connection_established":
                self._set_state(ConnectionState.CONNECTED)
                self.stats.connection_success()
                self.stats.data_received(len(confirmation))
                
                logger.info(f"✅ WebSocket连接成功!")
                logger.info(f"   服务器时间: {confirm_data.get('server_time')}")
                logger.info(f"   支持数据类型: {confirm_data.get('supported_data_types')}")
                
                # 调用连接成功回调
                if self.on_connected:
                    try:
                        await self.on_connected()
                    except Exception as e:
                        logger.error(f"❌ 连接成功回调异常: {e}")
            else:
                raise Exception(f"连接确认失败: {confirm_data}")
                
        except Exception as e:
            self.stats.connection_failed()
            logger.error(f"❌ WebSocket连接失败: {e}")
            
            if self.websocket:
                try:
                    await self.websocket.close()
                except:
                    pass
                self.websocket = None
            
            self._set_state(ConnectionState.DISCONNECTED)
            
            if self.on_error:
                try:
                    self.on_error(e)
                except Exception as callback_e:
                    logger.error(f"❌ 错误回调异常: {callback_e}")
    
    async def _handle_connection(self):
        """处理已建立的连接"""
        try:
            while self.websocket and not self.websocket.closed:
                try:
                    # 接收消息
                    message = await self.websocket.recv()
                    self.stats.data_received(len(message))
                    
                    # 处理消息
                    if self.on_message:
                        try:
                            await self.on_message(message)
                        except Exception as e:
                            logger.error(f"❌ 消息处理回调异常: {e}")
                    
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("🔴 WebSocket连接已关闭")
                    break
                except Exception as e:
                    logger.error(f"❌ 消息接收异常: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"❌ 连接处理异常: {e}")
        finally:
            if not self.is_manual_disconnect and self.on_disconnected:
                try:
                    await self.on_disconnected()
                except Exception as e:
                    logger.error(f"❌ 断开连接回调异常: {e}")
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        try:
            while self.websocket and not self.websocket.closed:
                await asyncio.sleep(self.heartbeat_interval)
                
                if self.websocket and not self.websocket.closed:
                    try:
                        # 发送自定义心跳消息
                        heartbeat_msg = {
                            "type": "client_heartbeat",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "stats": self.stats.get_stats_dict()
                        }
                        await self.send_message(json.dumps(heartbeat_msg))
                        logger.debug("💓 发送心跳")
                    except Exception as e:
                        logger.error(f"❌ 心跳发送失败: {e}")
                        break
        except asyncio.CancelledError:
            logger.debug("💓 心跳任务被取消")
        except Exception as e:
            logger.error(f"❌ 心跳循环异常: {e}")
    
    async def _send_loop(self):
        """发送消息循环"""
        try:
            while self.websocket and not self.websocket.closed:
                try:
                    # 从队列获取要发送的消息
                    message = await asyncio.wait_for(
                        self.message_queue.get(),
                        timeout=1.0
                    )
                    
                    if self.websocket and not self.websocket.closed:
                        await self.websocket.send(message)
                        self.stats.data_sent(len(message))
                        logger.debug(f"📤 发送消息: {len(message)} bytes")
                        
                except asyncio.TimeoutError:
                    # 队列为空，继续循环
                    continue
                except Exception as e:
                    logger.error(f"❌ 消息发送失败: {e}")
                    break
                    
        except asyncio.CancelledError:
            logger.debug("📤 发送任务被取消")
        except Exception as e:
            logger.error(f"❌ 发送循环异常: {e}")
    
    async def send_message(self, message: str):
        """发送消息（异步队列）"""
        if self.state == ConnectionState.CONNECTED:
            await self.message_queue.put(message)
        else:
            logger.warning(f"⚠️ 连接未建立，消息已丢弃: {len(message)} bytes")
    
    async def send_data(self, data: bytes):
        """发送二进制数据"""
        if self.state == ConnectionState.CONNECTED:
            await self.message_queue.put(data)
        else:
            logger.warning(f"⚠️ 连接未建立，数据已丢弃: {len(data)} bytes")
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        stats = self.stats.get_stats_dict()
        stats.update({
            "current_state": self.state.value,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "should_reconnect": self.should_reconnect,
            "is_manual_disconnect": self.is_manual_disconnect,
            "next_retry_delay": (
                self._calculate_retry_delay() if self.retry_count < self.max_retries else None
            )
        })
        return stats
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.state == ConnectionState.CONNECTED
    
    def is_healthy(self) -> bool:
        """检查连接是否健康"""
        return (
            self.state == ConnectionState.CONNECTED and
            self.websocket and
            not self.websocket.closed
        )
