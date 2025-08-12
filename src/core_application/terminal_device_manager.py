"""
终端设备注册管理器
Terminal Device Registration Manager

负责：
1. 终端设备注册到数据库
2. 将设备能力添加到服务器Agent Card
3. MCP工具配置管理
4. 设备在线状态管理
5. MCP服务验证
"""
import logging
import json
import requests
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import String

from src.data_persistence.terminal_device_models import (
    TerminalDevice, TerminalDeviceType, DataType
)
from src.data_persistence.database import DatabaseManager
from src.external_services.mcp_client import mcp_client_manager
from config.settings import settings


logger = logging.getLogger(__name__)


class TerminalDeviceManager:
    """终端设备管理器"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self._registered_devices: Dict[str, TerminalDevice] = {}
        self._device_capabilities: Dict[str, List[str]] = {}
        
        # 从数据库加载现有设备到内存缓存
        self._load_existing_devices()
    
    def _load_existing_devices(self):
        """从数据库加载现有设备到内存缓存"""
        try:
            devices = self.get_all_devices()
            for device in devices:
                self._registered_devices[device.device_id] = device
                self._device_capabilities[device.device_id] = device.mcp_tools or []
            
            logger.info(f"✅ 从数据库加载了 {len(devices)} 个现有设备到内存缓存")
            
            # 初始化时更新Agent Card
            if devices:
                self._update_server_agent_card()
                
        except Exception as e:
            logger.error(f"❌ 加载现有设备失败: {e}")
    
    def _validate_mcp_service(self, mcp_server_url: str, timeout: int = 10) -> Tuple[bool, List[str], str]:
        """
        验证MCP服务的可用性和工具列表
        
        Args:
            mcp_server_url: MCP服务器URL
            timeout: 超时时间（秒）
            
        Returns:
            Tuple[bool, List[str], str]: (是否可用, 工具列表, 错误信息)
        """
        try:
            logger.info(f"🔍 验证MCP服务: {mcp_server_url}")
            
            # 确保URL格式正确
            if not mcp_server_url.startswith(('http://', 'https://')):
                return False, [], "MCP服务器URL格式无效，必须以http://或https://开头"
            
            # MCP服务器URL就是端点本身，不需要额外添加路径
            mcp_endpoint_url = mcp_server_url.rstrip('/')
            
            # 构造符合MCP标准的JSON-RPC 2.0请求
            mcp_request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": "validation_request"
            }
            
            # 发送HTTP POST请求验证MCP服务
            response = requests.post(
                mcp_endpoint_url,
                json=mcp_request,
                headers={"Content-Type": "application/json"},
                timeout=timeout
            )
            
            if response.status_code != 200:
                error_msg = f"MCP服务响应状态码异常: {response.status_code}"
                logger.warning(f"⚠️ {error_msg}")
                return False, [], error_msg
            
            response_data = response.json()
            
            # 验证JSON-RPC 2.0响应格式
            if "jsonrpc" not in response_data or response_data["jsonrpc"] != "2.0":
                error_msg = f"MCP服务响应不是有效的JSON-RPC 2.0格式: {response_data}"
                logger.warning(f"⚠️ {error_msg}")
                return False, [], error_msg
            
            if "result" not in response_data:
                # 检查是否有错误信息
                if "error" in response_data:
                    error_info = response_data["error"]
                    error_msg = f"MCP服务返回错误: {error_info.get('message', 'Unknown error')}"
                else:
                    error_msg = f"MCP服务响应格式无效，缺少result字段: {response_data}"
                logger.warning(f"⚠️ {error_msg}")
                return False, [], error_msg
            
            # 提取工具列表
            tools_result = response_data["result"]
            tools = tools_result.get("tools", [])
            
            # 提取工具名称列表
            tool_names = []
            for tool in tools:
                if isinstance(tool, dict) and "name" in tool:
                    tool_names.append(tool["name"])
                elif isinstance(tool, str):
                    tool_names.append(tool)
            
            logger.info(f"✅ MCP服务验证成功，发现 {len(tool_names)} 个工具: {tool_names}")
            return True, tool_names, ""
                    
        except requests.exceptions.Timeout:
            error_msg = f"MCP服务连接超时 ({timeout}秒)"
            logger.warning(f"⚠️ {error_msg}")
            return False, [], error_msg
            
        except requests.exceptions.RequestException as e:
            error_msg = f"MCP服务连接失败: {str(e)}"
            logger.warning(f"⚠️ {error_msg}")
            return False, [], error_msg
            
        except Exception as e:
            error_msg = f"MCP服务验证异常: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return False, [], error_msg

    def register_device(
        self,
        device_id: str,
        name: str,
        device_type: TerminalDeviceType,
        mcp_server_url: str,
        description: str = "",
        mcp_tools: List[str] = None,  # 改为工具名称列表，符合MCP标准
        supported_data_types: List[DataType] = None,
        websocket_endpoint: str = None,
        system_prompt: str = None,
        intent_keywords: List[str] = None,
        hardware_info: Dict[str, Any] = None,
        location: str = None,
        max_data_size_mb: int = 10
    ) -> TerminalDevice:
        """
        注册新的终端设备
        
        Args:
            device_id: 设备唯一标识
            name: 设备名称
            device_type: 设备类型
            mcp_server_url: MCP服务器地址
            description: 设备描述
            mcp_capabilities: MCP能力列表
            mcp_tools: MCP工具配置
            supported_data_types: 支持的数据类型
            websocket_endpoint: WebSocket端点
            system_prompt: 系统提示词
            intent_keywords: 意图关键词
            hardware_info: 硬件信息
            location: 设备位置
            max_data_size_mb: 最大数据包大小
        """
        try:
            # 验证MCP服务并获取真实的工具列表
            logger.info(f"🔍 注册设备前验证MCP服务: {device_id} -> {mcp_server_url}")
            is_valid, available_tools, error_msg = self._validate_mcp_service(mcp_server_url, timeout=10)
            
            if not is_valid:
                error_message = f"MCP服务验证失败，无法注册设备 {device_id}: {error_msg}"
                logger.error(f"❌ {error_message}")
                raise ValueError(error_message)
            
            # 使用从MCP服务器获取的真实工具列表
            validated_tools = available_tools if available_tools else (mcp_tools or [])
            logger.info(f"✅ MCP服务验证成功，使用工具列表: {validated_tools}")
            
            with self.db_manager.create_session() as db:
                # 检查设备是否已存在
                existing_device = db.query(TerminalDevice).filter(
                    TerminalDevice.device_id == device_id
                ).first()
                
                if existing_device:
                    # 更新现有设备
                    existing_device.name = name
                    existing_device.description = description
                    existing_device.device_type = device_type
                    existing_device.mcp_server_url = mcp_server_url
                    existing_device.mcp_tools = validated_tools  # 使用验证后的工具列表
                    existing_device.supported_data_types = [dt.value for dt in (supported_data_types or [])]
                    existing_device.websocket_endpoint = websocket_endpoint
                    existing_device.system_prompt = system_prompt
                    existing_device.intent_keywords = intent_keywords or []
                    existing_device.hardware_info = hardware_info or {}
                    existing_device.location = location
                    existing_device.max_data_size_mb = max_data_size_mb
                    existing_device.updated_at = datetime.utcnow()
                    existing_device.last_seen = datetime.utcnow()
                    existing_device.is_connected = True
                    
                    db.commit()
                    device = existing_device
                    logger.info(f"✅ 更新终端设备: {device_id}")
                else:
                    # 创建新设备
                    device = TerminalDevice(
                        device_id=device_id,
                        name=name,
                        description=description,
                        device_type=device_type,
                        mcp_server_url=mcp_server_url,
                        mcp_tools=validated_tools,  # 使用验证后的工具列表
                        supported_data_types=[dt.value for dt in (supported_data_types or [])],
                        websocket_endpoint=websocket_endpoint,
                        system_prompt=system_prompt,
                        intent_keywords=intent_keywords or [],
                        hardware_info=hardware_info or {},
                        location=location,
                        max_data_size_mb=max_data_size_mb,
                        is_connected=True,
                        last_seen=datetime.utcnow()
                    )
                    
                    db.add(device)
                    db.commit()
                    db.refresh(device)
                    logger.info(f"✅ 注册新终端设备: {device_id}")
                
                # 缓存设备信息
                self._registered_devices[device_id] = device
                self._device_capabilities[device_id] = device.mcp_tools or []
                
                # 更新服务器Agent Card
                self._update_server_agent_card()
                
                return device
                
        except Exception as e:
            logger.error(f"❌ 注册终端设备失败 {device_id}: {e}")
            raise
    
    def unregister_device(self, device_id: str) -> bool:
        """
        注销终端设备 - 完全删除设备
        
        Args:
            device_id: 设备ID
            
        Returns:
            bool: 是否成功注销
        """
        try:
            with self.db_manager.create_session() as db:
                device = db.query(TerminalDevice).filter(
                    TerminalDevice.device_id == device_id
                ).first()
                
                if device:
                    # 完全删除设备而不是标记为离线
                    db.delete(device)
                    db.commit()
                    
                    # 从缓存中移除
                    self._registered_devices.pop(device_id, None)
                    self._device_capabilities.pop(device_id, None)
                    
                    # 更新服务器Agent Card
                    self._update_server_agent_card()
                    
                    logger.info(f"✅ 注销终端设备: {device_id}")
                    return True
                else:
                    logger.warning(f"⚠️ 设备未找到: {device_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ 注销终端设备失败 {device_id}: {e}")
            return False
    
    def get_device(self, device_id: str) -> Optional[TerminalDevice]:
        """获取设备信息"""
        try:
            with self.db_manager.create_session() as db:
                device = db.query(TerminalDevice).filter(
                    TerminalDevice.device_id == device_id
                ).first()
                return device
        except Exception as e:
            logger.error(f"❌ 获取设备信息失败 {device_id}: {e}")
            return None
    
    def get_all_devices(self, online_only: bool = False) -> List[TerminalDevice]:
        """获取所有设备"""
        try:
            with self.db_manager.create_session() as db:
                query = db.query(TerminalDevice)
                if online_only:
                    query = query.filter(TerminalDevice.is_connected == True)
                return query.all()
        except Exception as e:
            logger.error(f"❌ 获取设备列表失败: {e}")
            return []

    def list_connected_devices(self) -> List[TerminalDevice]:
        """获取所有已连接的设备（符合MCP标准）"""
        return self.get_all_devices(online_only=True)

    def list_devices(self) -> List[TerminalDevice]:
        """获取所有设备"""
        return self.get_all_devices(online_only=False)

    def list_devices(self) -> List[TerminalDevice]:
        """列出所有设备（别名方法）"""
        return self.get_all_devices()

    def list_connected_devices(self) -> List[TerminalDevice]:
        """获取所有已连接的设备"""
        try:
            with self.db_manager.create_session() as db:
                devices = db.query(TerminalDevice).filter(
                    TerminalDevice.is_connected == True
                ).all()
                logger.info(f"📱 找到 {len(devices)} 个已连接设备")
                return devices
        except Exception as e:
            logger.error(f"❌ 获取已连接设备失败: {e}")
            return []
    
    def get_devices_by_tool(self, tool_name: str) -> List[TerminalDevice]:
        """根据工具名称获取设备（符合MCP标准）"""
        try:
            with self.db_manager.create_session() as db:
                logger.info(f"🔍 查找支持工具 '{tool_name}' 的设备...")
                
                # 使用LIKE查询来匹配JSON数组中的工具名称
                tool_pattern = f'%"{tool_name}"%'
                
                all_capable_devices = db.query(TerminalDevice).filter(
                    TerminalDevice.mcp_tools.cast(String).like(tool_pattern)
                ).all()
                
                logger.info(f"📋 找到 {len(all_capable_devices)} 个支持该工具的设备")
                
                for device in all_capable_devices:
                    logger.info(f"   🔹 {device.device_id}: connected={device.is_connected}, tools={device.mcp_tools}")
                
                # 然后筛选已连接的设备
                connected_devices = [d for d in all_capable_devices if d.is_connected]
                logger.info(f"✅ 其中 {len(connected_devices)} 个设备已连接")
                
                if not connected_devices:
                    logger.warning(f"⚠️ 没有找到已连接且支持 '{tool_name}' 工具的设备")
                    # 如果没有已连接的设备，但有具备该工具的设备，尝试使用第一个（可能是连接状态更新延迟）
                    if all_capable_devices:
                        logger.info(f"🔄 尝试使用第一个支持该工具的设备: {all_capable_devices[0].device_id}")
                        # 更新设备连接状态
                        all_capable_devices[0].is_connected = True
                        all_capable_devices[0].last_seen = datetime.utcnow()
                        db.commit()
                        return [all_capable_devices[0]]
                
                return connected_devices
        except Exception as e:
            logger.error(f"❌ 根据工具获取设备失败: {e}")
            import traceback
            logger.error(f"❌ 详细错误: {traceback.format_exc()}")
            return []
    
    def update_device_status(self, device_id: str, is_connected: bool) -> bool:
        """更新设备在线状态"""
        try:
            with self.db_manager.create_session() as db:
                device = db.query(TerminalDevice).filter(
                    TerminalDevice.device_id == device_id
                ).first()
                
                if device:
                    device.is_connected = is_connected
                    device.last_seen = datetime.utcnow()
                    if is_connected:
                        device.last_ping = datetime.utcnow()
                    db.commit()
                    return True
                return False
        except Exception as e:
            logger.error(f"❌ 更新设备状态失败 {device_id}: {e}")
            return False
    
    def heartbeat_device(self, device_id: str) -> bool:
        """设备心跳"""
        try:
            with self.db_manager.create_session() as db:
                device = db.query(TerminalDevice).filter(
                    TerminalDevice.device_id == device_id
                ).first()
                
                if device:
                    device.last_ping = datetime.utcnow()
                    device.last_seen = datetime.utcnow()
                    device.is_connected = True
                    db.commit()
                    return True
                return False
        except Exception as e:
            logger.error(f"❌ 设备心跳失败 {device_id}: {e}")
            return False
    
    def get_mcp_tools_config(self) -> List[Dict[str, Any]]:
        """获取所有设备的MCP工具配置"""
        devices = self.get_all_devices(online_only=True)
        mcp_tools = []
        
        for device in devices:
            tool_config = device.to_mcp_tool_config()
            mcp_tools.append(tool_config)
        
        return mcp_tools
    
    async def call_device_mcp_tool(
        self,
        device_id: str,
        tool_name: str,
        parameters: Dict[str, Any] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        调用指定设备的MCP工具
        
        Args:
            device_id: 设备ID
            tool_name: 工具名称
            parameters: 工具参数
            timeout: 超时时间(秒)
            
        Returns:
            Dict[str, Any]: 调用结果
        """
        try:
            # 获取设备信息
            device = self.get_device(device_id)
            if not device:
                return {
                    "success": False,
                    "error": f"设备不存在: {device_id}",
                    "device_id": device_id,
                    "tool_name": tool_name
                }
            
            if not device.is_connected:
                return {
                    "success": False,
                    "error": f"设备离线: {device_id}",
                    "device_id": device_id,
                    "tool_name": tool_name
                }
            
            # 检查设备是否支持该工具
            # 兼容处理：支持字符串列表和字典列表两种格式
            if isinstance(device.mcp_tools, list) and device.mcp_tools:
                if isinstance(device.mcp_tools[0], str):
                    # 字符串列表格式
                    device_tools = device.mcp_tools
                else:
                    # 字典列表格式
                    device_tools = [tool.get("name") for tool in device.mcp_tools]
            else:
                device_tools = []
                
            if tool_name not in device_tools:
                return {
                    "success": False,
                    "error": f"设备不支持工具 '{tool_name}'，支持的工具: {device_tools}",
                    "device_id": device_id,
                    "tool_name": tool_name,
                    "available_tools": device_tools
                }
            
            # 调用MCP工具
            logger.info(f"🔧 调用设备MCP工具: {device_id} -> {tool_name}")
            result = await mcp_client_manager.call_device_tool(
                device_id=device_id,
                server_url=device.mcp_server_url,
                tool_name=tool_name,
                parameters=parameters or {},
                timeout=timeout
            )
            
            # 更新设备最后活跃时间
            if result.get("success"):
                self.heartbeat_device(device_id)
                logger.info(f"✅ MCP工具调用成功: {device_id} -> {tool_name}")
            else:
                logger.warning(f"⚠️ MCP工具调用失败: {device_id} -> {tool_name} - {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 调用设备MCP工具异常: {device_id} -> {tool_name} - {str(e)}")
            return {
                "success": False,
                "error": f"调用异常: {str(e)}",
                "device_id": device_id,
                "tool_name": tool_name
            }
    
    async def test_device_mcp_connection(self, device_id: str) -> Dict[str, Any]:
        """
        测试设备MCP连接
        
        Args:
            device_id: 设备ID
            
        Returns:
            Dict[str, Any]: 连接测试结果
        """
        try:
            device = self.get_device(device_id)
            if not device:
                return {
                    "success": False,
                    "error": f"设备不存在: {device_id}",
                    "device_id": device_id
                }
            
            result = await mcp_client_manager.test_device_connection(
                device_id=device_id,
                server_url=device.mcp_server_url
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 测试设备MCP连接异常: {device_id} - {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "device_id": device_id
            }
    
    async def call_mcp_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any] = None,
        prefer_device_id: str = None
    ) -> Dict[str, Any]:
        """
        调用MCP工具（符合MCP标准的方法）
        
        Args:
            tool_name: 工具名称
            parameters: 工具参数
            prefer_device_id: 优先选择的设备ID
            
        Returns:
            Dict[str, Any]: 调用结果
        """
        try:
            # 获取支持指定工具的设备
            capable_devices = self.get_devices_by_tool(tool_name)
            
            if not capable_devices:
                return {
                    "success": False,
                    "error": f"没有设备支持工具: {tool_name}",
                    "tool_name": tool_name
                }
            
            # 优先选择指定设备
            selected_device = None
            if prefer_device_id:
                for device in capable_devices:
                    if device.device_id == prefer_device_id:
                        selected_device = device
                        break
            
            # 如果没有指定设备或指定设备不可用，选择第一个可用设备
            if not selected_device:
                selected_device = capable_devices[0]
            
            logger.info(f"🎯 选择设备调用工具 '{tool_name}': {selected_device.device_id}")
            
            # 调用设备MCP工具
            result = await self.call_device_mcp_tool(
                device_id=selected_device.device_id,
                tool_name=tool_name,
                parameters=parameters
            )
            
            # 添加选择信息
            result["selected_device"] = selected_device.device_id
            result["tool_used"] = tool_name
            result["available_devices"] = [d.device_id for d in capable_devices]
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 调用MCP工具异常: {tool_name} - {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "tool_name": tool_name
            }
    
    def _update_server_agent_card(self):
        """更新服务器的Agent Card，添加所有设备能力"""
        try:
            # 收集所有设备的能力（使用所有设备，不只是在线设备）
            all_capabilities = set()
            device_types = set()
            
            all_devices = self.get_all_devices(online_only=False)  # 获取所有设备
            for device in all_devices:
                # 确保mcp_tools是字符串列表，处理可能的字典格式
                if device.mcp_tools:
                    for tool in device.mcp_tools:
                        if isinstance(tool, dict):
                            # 如果是字典，提取name字段
                            tool_name = tool.get("name")
                            if tool_name:
                                all_capabilities.add(tool_name)
                        elif isinstance(tool, str):
                            # 如果是字符串，直接添加
                            all_capabilities.add(tool)
                device_types.add(device.device_type.value)
            
            device_count = len(all_devices)  # 使用实际数据库查询的设备数量
            
            # 读取现有的Agent Card
            agent_card_path = "config/agent_card.json"
            try:
                with open(agent_card_path, 'r', encoding='utf-8') as f:
                    agent_card = json.load(f)
            except FileNotFoundError:
                # 创建默认Agent Card
                agent_card = {
                    "protocolVersion": "0.3.0",
                    "name": "终端设备A2A服务",
                    "description": "智能终端设备代理服务，支持A2A协议的多设备终端管理和意图路由",
                    "skills": []
                }
            
            # 添加终端设备管理技能
            terminal_skill = {
                "id": "terminal_device_management",
                "name": "终端设备管理",
                "description": f"管理 {device_count} 个终端设备，支持多种设备类型和MCP工具调用",
                "tags": ["terminal", "device", "mcp", "management"] + list(device_types),
                "examples": [
                    f"调用 {device_count} 个已注册终端设备的MCP工具",
                    "实时处理设备传感器数据和多媒体内容",
                    "基于设备能力进行智能任务分派"
                ],
                "capabilities": list(all_capabilities)
            }
            
            # 更新或添加技能
            skills = agent_card.get("skills", [])
            # 移除旧的终端设备管理技能
            skills = [s for s in skills if s.get("id") != "terminal_device_management"]
            # 添加新的技能
            skills.append(terminal_skill)
            agent_card["skills"] = skills
            
            # 更新描述
            agent_card["description"] = (
                f"智能终端设备代理服务，当前管理 {device_count} 个终端设备，"
                f"支持 {len(all_capabilities)} 种MCP能力和A2A协议的多设备终端管理与意图路由"
            )
            
            # 写回文件
            with open(agent_card_path, 'w', encoding='utf-8') as f:
                json.dump(agent_card, f, ensure_ascii=False, indent=2)
            
            logger.info(f"✅ 更新Agent Card: {device_count} 设备, {len(all_capabilities)} 能力")
            
        except Exception as e:
            logger.error(f"❌ 更新Agent Card失败: {e}")
    
    def cleanup_offline_devices(self, offline_threshold_minutes: int = 30):
        """清理长时间离线的设备"""
        try:
            threshold_time = datetime.utcnow() - timedelta(minutes=offline_threshold_minutes)
            
            with self.db_manager.create_session() as db:
                offline_devices = db.query(TerminalDevice).filter(
                    TerminalDevice.last_ping < threshold_time,
                    TerminalDevice.is_connected == True
                ).all()
                
                for device in offline_devices:
                    device.is_connected = False
                    logger.info(f"🔴 设备离线: {device.device_id}")
                
                if offline_devices:
                    db.commit()
                    self._update_server_agent_card()
                    
                return len(offline_devices)
                
        except Exception as e:
            logger.error(f"❌ 清理离线设备失败: {e}")
            return 0

    async def discover_and_select_tool(
        self,
        intent: str,
        tool_name: Optional[str] = None,
        parameters: Dict[str, Any] = None,
        prefer_device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        根据意图发现和选择合适的MCP工具（符合MCP标准）
        
        Args:
            intent: 用户意图描述
            tool_name: 指定的工具名称（可选）
            parameters: 工具参数
            prefer_device_id: 优先选择的设备ID
            
        Returns:
            Dict[str, Any]: 包含执行结果的字典
        """
        try:
            import time
            start_time = time.time()
            
            if parameters is None:
                parameters = {}
            
            logger.info(f"🎯 工具发现和选择: intent='{intent}', tool_name={tool_name}")
            
            # 1. 获取所有已连接的设备
            connected_devices = self.list_connected_devices()
            
            if not connected_devices:
                return {
                    "success": False,
                    "error": "没有已连接的设备",
                    "execution_time_ms": int((time.time() - start_time) * 1000)
                }
            
            # 2. 如果指定了工具名称，直接查找支持该工具的设备
            if tool_name:
                matching_devices = self.get_devices_by_tool(tool_name)
                
                if not matching_devices:
                    return {
                        "success": False,
                        "error": f"没有设备支持工具 '{tool_name}'",
                        "execution_time_ms": int((time.time() - start_time) * 1000)
                    }
                
                # 选择设备（优先选择指定设备）
                selected_device = None
                if prefer_device_id:
                    for device in matching_devices:
                        if device.device_id == prefer_device_id:
                            selected_device = device
                            break
                
                if not selected_device:
                    selected_device = matching_devices[0]  # 选择第一个匹配的设备
                
                # 调用工具
                result = await self.call_device_mcp_tool(
                    device_id=selected_device.device_id,
                    tool_name=tool_name,
                    parameters=parameters
                )
                
                if result["success"]:
                    result.update({
                        "selected_device": selected_device.name,
                        "device_id": selected_device.device_id,
                        "tool_name": tool_name,
                        "execution_time_ms": int((time.time() - start_time) * 1000)
                    })
                
                return result
            
            # 3. 如果没有指定工具名称，使用LLM进行语义匹配
            # 收集所有可用工具信息
            all_available_tools = []
            
            for device in connected_devices:
                if device.mcp_tools:
                    for tool in device.mcp_tools:
                        tool_info = {
                            "device_id": device.device_id,
                            "device_name": device.name,
                            "tool_name": tool,
                            "tool_description": f"设备 {device.name} 的 {tool} 工具"
                        }
                        all_available_tools.append(tool_info)
            
            if not all_available_tools:
                return {
                    "success": False,
                    "error": "没有可用的工具",
                    "execution_time_ms": int((time.time() - start_time) * 1000)
                }
            
            # 使用LLM选择最合适的工具
            selected_tool_info = await self._llm_select_tool_for_intent(intent, all_available_tools)
            
            if not selected_tool_info:
                return {
                    "success": False,
                    "error": "LLM无法为该意图找到合适的工具",
                    "execution_time_ms": int((time.time() - start_time) * 1000)
                }
            
            # 调用选定的工具
            result = await self.call_device_mcp_tool(
                device_id=selected_tool_info["device_id"],
                tool_name=selected_tool_info["tool_name"],
                parameters=parameters
            )
            
            if result["success"]:
                result.update({
                    "selected_device": selected_tool_info["device_name"],
                    "device_id": selected_tool_info["device_id"],
                    "tool_name": selected_tool_info["tool_name"],
                    "execution_time_ms": int((time.time() - start_time) * 1000)
                })
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 工具发现和选择失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return {
                "success": False,
                "error": f"工具发现和选择失败: {str(e)}",
                "execution_time_ms": int((time.time() - start_time) * 1000) if 'start_time' in locals() else 0
            }

    async def _llm_select_tool_for_intent(self, intent: str, available_tools: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        使用LLM根据意图选择最合适的工具
        
        Args:
            intent: 用户意图
            available_tools: 可用工具列表
            
        Returns:
            Optional[Dict[str, Any]]: 选择的工具信息
        """
        try:
            from src.external_services.llm_service import LLMService
            
            llm_service = LLMService()
            
            # 构造工具描述
            tools_description = []
            for i, tool in enumerate(available_tools):
                tool_desc = f"""
工具 {i+1}:
- 设备: {tool['device_name']} (ID: {tool['device_id']})
- 工具名: {tool['tool_name']}
- 描述: {tool['tool_description']}
"""
                tools_description.append(tool_desc)
            
            # 使用LLM进行工具选择
            selection_prompt = f"""
用户意图: {intent}

以下是当前可用的工具：
{chr(10).join(tools_description)}

请分析用户意图，选择最合适的工具。返回工具的序号 (1-{len(available_tools)})，如果没有合适的工具请返回 0。

只返回数字，不要其他解释。
"""
            
            selection_response = await llm_service.generate_response(selection_prompt)
            
            try:
                tool_index = int(selection_response.strip()) - 1
                
                if 0 <= tool_index < len(available_tools):
                    selected_tool = available_tools[tool_index]
                    logger.info(f"🤖 LLM选择了工具: {selected_tool['device_name']}.{selected_tool['tool_name']}")
                    return selected_tool
                else:
                    logger.warning(f"⚠️ LLM返回了无效的工具索引: {tool_index + 1}")
                    return None
                    
            except ValueError:
                logger.warning(f"⚠️ LLM返回了非数字响应: {selection_response}")
                return None
                
        except Exception as e:
            logger.error(f"❌ LLM工具选择失败: {e}")
            return None


# 全局实例
terminal_device_manager = TerminalDeviceManager()
