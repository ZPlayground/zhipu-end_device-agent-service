"""
MCP (Model Context Protocol) 客户端
MCP Client for Terminal Device Communication

负责：
1. 与终端设备的MCP服务器通信
2. 调用设备提供的MCP工具
3. 处理MCP协议的请求和响应
4. 管理连接和错误处理
"""
import logging
import asyncio
import json
import time
from typing import Dict, List, Optional, Any, Union
import aiohttp
from datetime import datetime

from config.settings import settings

logger = logging.getLogger(__name__)


class MCPClient:
    """MCP协议客户端"""
    
    def __init__(self, server_url: str, timeout: int = 30):
        """
        初始化MCP客户端
        
        Args:
            server_url: MCP服务器URL
            timeout: 请求超时时间(秒)
        """
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    async def call_tool(
        self, 
        tool_name: str, 
        parameters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        调用MCP工具
        
        Args:
            tool_name: 工具名称
            parameters: 工具参数
            
        Returns:
            Dict[str, Any]: 工具执行结果
        """
        start_time = time.time()
        
        try:
            # 构造MCP请求
            mcp_request = {
                "jsonrpc": "2.0",
                "id": f"call_{int(time.time() * 1000)}",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": parameters or {}
                }
            }
            
            logger.info(f"🔧 调用MCP工具: {tool_name} at {self.server_url}")
            logger.debug(f"📤 MCP请求: {json.dumps(mcp_request, indent=2)}")
            
            # 发送HTTP请求到MCP服务器
            if not self.session:
                raise Exception("MCP客户端未初始化，请使用async with语句")
            
            async with self.session.post(
                self.server_url,  # 直接使用server_url，不再添加/mcp
                json=mcp_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"MCP服务器返回错误状态 {response.status}: {error_text}")
                
                # 获取响应文本用于调试
                response_text = await response.text()
                logger.debug(f"📥 原始MCP响应: {response_text}")
                
                # 解析JSON响应
                try:
                    response_data = json.loads(response_text)
                except json.JSONDecodeError as e:
                    raise Exception(f"MCP响应不是有效的JSON: {response_text}")
                
                if response_data is None:
                    raise Exception(f"MCP响应为空: {response_text}")
                
                execution_time = int((time.time() - start_time) * 1000)
                
                logger.debug(f"📥 解析后的MCP响应: {json.dumps(response_data, indent=2)}")
                
                # 检查MCP响应格式
                if "error" in response_data and response_data["error"] is not None:
                    error_info = response_data["error"]
                    if isinstance(error_info, dict):
                        raise Exception(f"MCP工具执行错误: {error_info.get('message', '未知错误')}")
                    else:
                        raise Exception(f"MCP工具执行错误: {str(error_info)}")
                
                if "result" not in response_data:
                    raise Exception("MCP响应缺少result字段")
                
                result = response_data["result"]
                logger.info(f"✅ MCP工具调用成功: {tool_name} (耗时: {execution_time}ms)")
                
                return {
                    "success": True,
                    "result": result,
                    "execution_time_ms": execution_time,
                    "tool_name": tool_name,
                    "server_url": self.server_url
                }
                
        except asyncio.TimeoutError:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"❌ MCP工具调用超时: {tool_name} (超时: {self.timeout}s)")
            return {
                "success": False,
                "error": f"MCP工具调用超时: {self.timeout}秒",
                "execution_time_ms": execution_time,
                "tool_name": tool_name,
                "server_url": self.server_url
            }
            
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"❌ MCP工具调用失败: {tool_name} - {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": execution_time,
                "tool_name": tool_name,
                "server_url": self.server_url
            }
    
    async def list_tools(self) -> Dict[str, Any]:
        """
        获取MCP服务器支持的工具列表
        
        Returns:
            Dict[str, Any]: 工具列表
        """
        try:
            mcp_request = {
                "jsonrpc": "2.0",
                "id": f"list_{int(time.time() * 1000)}",
                "method": "tools/list",
                "params": {}
            }
            
            if not self.session:
                raise Exception("MCP客户端未初始化")
            
            async with self.session.post(
                self.server_url,  # 直接使用server_url，不再添加/mcp
                json=mcp_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"获取工具列表失败: {response.status} - {error_text}")
                
                response_data = await response.json()
                
                if "error" in response_data and response_data["error"] is not None:
                    raise Exception(f"MCP错误: {response_data['error'].get('message', '未知错误')}")
                
                return {
                    "success": True,
                    "tools": response_data.get("result", {}).get("tools", [])
                }
                
        except Exception as e:
            logger.error(f"❌ 获取MCP工具列表失败: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "tools": []
            }
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        测试MCP服务器连接
        
        Returns:
            Dict[str, Any]: 连接测试结果
        """
        try:
            # 尝试获取工具列表来测试连接
            tools_result = await self.list_tools()
            
            if tools_result["success"]:
                logger.info(f"✅ MCP服务器连接正常: {self.server_url}")
                return {
                    "success": True,
                    "message": "MCP服务器连接正常",
                    "server_url": self.server_url,
                    "available_tools": len(tools_result.get("tools", []))
                }
            else:
                return {
                    "success": False,
                    "error": tools_result.get("error", "连接测试失败"),
                    "server_url": self.server_url
                }
                
        except Exception as e:
            logger.error(f"❌ MCP服务器连接测试失败: {self.server_url} - {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "server_url": self.server_url
            }


class MCPClientManager:
    """MCP客户端管理器"""
    
    def __init__(self):
        self._clients: Dict[str, MCPClient] = {}
        self._client_sessions: Dict[str, aiohttp.ClientSession] = {}
    
    async def get_client(self, server_url: str, timeout: int = 30) -> MCPClient:
        """
        获取或创建MCP客户端
        
        Args:
            server_url: MCP服务器URL
            timeout: 超时时间
            
        Returns:
            MCPClient: MCP客户端实例
        """
        client_key = f"{server_url}:{timeout}"
        
        if client_key not in self._clients:
            self._clients[client_key] = MCPClient(server_url, timeout)
        
        return self._clients[client_key]
    
    async def call_device_tool(
        self,
        device_id: str,
        server_url: str,
        tool_name: str,
        parameters: Dict[str, Any] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        调用指定设备的MCP工具
        
        Args:
            device_id: 设备ID
            server_url: MCP服务器URL
            tool_name: 工具名称
            parameters: 工具参数
            timeout: 超时时间
            
        Returns:
            Dict[str, Any]: 调用结果
        """
        try:
            client = await self.get_client(server_url, timeout)
            
            async with client:
                result = await client.call_tool(tool_name, parameters)
                
                # 添加设备信息到结果中
                result["device_id"] = device_id
                result["timestamp"] = datetime.utcnow().isoformat()
                
                return result
                
        except Exception as e:
            logger.error(f"❌ 调用设备MCP工具失败: {device_id} - {tool_name} - {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "device_id": device_id,
                "tool_name": tool_name,
                "server_url": server_url,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def test_device_connection(self, device_id: str, server_url: str) -> Dict[str, Any]:
        """
        测试设备MCP连接
        
        Args:
            device_id: 设备ID
            server_url: MCP服务器URL
            
        Returns:
            Dict[str, Any]: 连接测试结果
        """
        try:
            client = await self.get_client(server_url)
            
            async with client:
                result = await client.test_connection()
                result["device_id"] = device_id
                return result
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "device_id": device_id,
                "server_url": server_url
            }
    
    async def cleanup(self):
        """清理资源"""
        for session in self._client_sessions.values():
            if not session.closed:
                await session.close()
        
        self._clients.clear()
        self._client_sessions.clear()


# 全局MCP客户端管理器实例
mcp_client_manager = MCPClientManager()
