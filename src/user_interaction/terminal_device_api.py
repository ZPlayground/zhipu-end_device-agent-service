"""
重构的终端设备API
Refactored Terminal Device API

提供：
1. 终端设备注册API (不再暴露为A2A Agent)
2. WebSocket连接管理
3. MCP工具调用接口
4. 设备状态监控
5. EventStream状态查询
6. 意图识别日志查询
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

from src.data_persistence.database import get_db
from src.data_persistence.terminal_device_models import (
    TerminalDeviceType, DataType
    # 移除 MCPCapability，因为MCP标准中没有预定义能力概念
)
from src.core_application.terminal_device_manager import terminal_device_manager
from src.core_application.websocket_data_manager import websocket_data_manager
from src.core_application.event_stream_manager import event_stream_manager
from src.core_application.multimodal_llm_agent import multimodal_llm_agent_manager
from config.settings import settings
import logging


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/terminal-devices", tags=["Terminal Devices"])


# === Pydantic模型定义 ===

class TerminalDeviceRegistration(BaseModel):
    """终端设备注册请求"""
    device_id: str = Field(..., description="设备唯一标识")
    name: str = Field(..., description="设备名称")
    description: str = Field("", description="设备描述")
    device_type: TerminalDeviceType = Field(..., description="设备类型")
    
    # MCP服务器配置（符合MCP标准）
    mcp_server_url: str = Field(..., description="MCP服务器地址")
    mcp_tools: List[str] = Field(default=[], description="MCP工具名称列表（符合MCP标准）")
    
    # WebSocket配置
    websocket_endpoint: Optional[str] = Field(None, description="WebSocket端点")
    supported_data_types: List[DataType] = Field(default=[], description="支持的数据类型")
    max_data_size_mb: int = Field(10, description="最大数据包大小(MB)")
    
    # 意图识别配置
    system_prompt: Optional[str] = Field(None, description="设备特定的系统提示词")
    intent_keywords: List[str] = Field(default=[], description="意图关键词")
    
    # 其他信息
    location: Optional[str] = Field(None, description="设备位置")
    hardware_info: Dict[str, Any] = Field(default={}, description="硬件信息")


class TerminalDeviceResponse(BaseModel):
    """终端设备响应"""
    id: int
    device_id: str
    name: str
    description: str
    device_type: str
    mcp_server_url: str
    mcp_tools: List[str]
    websocket_endpoint: Optional[str]
    supported_data_types: List[str]
    max_data_size_mb: int
    is_connected: bool
    location: Optional[str]
    hardware_info: Dict[str, Any]
    system_prompt: Optional[str]
    intent_keywords: List[str]
    created_at: str
    updated_at: str
    last_seen: Optional[str]
    
    class Config:
        from_attributes = True


class TerminalDeviceUpdate(BaseModel):
    """终端设备更新请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    mcp_server_url: Optional[str] = None
    # 移除 mcp_capabilities，因为MCP标准中没有预定义能力概念
    mcp_tools: Optional[List[str]] = None
    websocket_endpoint: Optional[str] = None
    supported_data_types: Optional[List[DataType]] = None
    max_data_size_mb: Optional[int] = None
    system_prompt: Optional[str] = None
    intent_keywords: Optional[List[str]] = None
    location: Optional[str] = None
    hardware_info: Optional[Dict[str, Any]] = None


class EventStreamStatus(BaseModel):
    """事件流状态"""
    stream_id: str
    device_id: str
    is_active: bool
    current_entries: int
    max_entries: int
    current_size_mb: float
    max_size_mb: float
    total_processed: int
    created_at: str
    last_data_at: Optional[str]
    last_read_at: Optional[str]
    should_persist: bool
    should_release: bool


class MCPToolCallRequest(BaseModel):
    """MCP工具调用请求"""
    device_id: str = Field(..., description="目标设备ID")
    tool_name: str = Field(..., description="工具名称")
    parameters: Dict[str, Any] = Field(default={}, description="工具参数")
    timeout_seconds: int = Field(30, description="超时时间(秒)")


class MCPToolCallResponse(BaseModel):
    """MCP工具调用响应"""
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None


class MCPToolCallByIntentRequest(BaseModel):
    """按意图调用MCP工具请求（符合MCP标准）"""
    intent: str = Field(..., description="用户意图描述")
    tool_name: Optional[str] = Field(None, description="指定工具名称(可选)")
    parameters: Dict[str, Any] = Field(default={}, description="工具参数")
    prefer_device_id: Optional[str] = Field(None, description="优先选择的设备ID")
    timeout_seconds: int = Field(30, description="超时时间(秒)")


class MCPConnectionTestResponse(BaseModel):
    """MCP连接测试响应"""
    success: bool
    device_id: str
    server_url: Optional[str] = None
    available_tools: Optional[int] = None
    error: Optional[str] = None
    message: Optional[str] = None


# === API端点定义 ===

@router.post("/register", response_model=TerminalDeviceResponse)
async def register_terminal_device(
    device_data: TerminalDeviceRegistration,
    db: Session = Depends(get_db)
):
    """
    注册新的终端设备
    
    注意：设备不再暴露为A2A Agent，只注册设备信息到数据库
    在注册前会自动验证MCP服务的可用性和工具列表
    """
    try:
        # 直接使用原始注册方法（已内置MCP验证）
        device = terminal_device_manager.register_device(
            device_id=device_data.device_id,
            name=device_data.name,
            device_type=device_data.device_type,
            mcp_server_url=device_data.mcp_server_url,
            description=device_data.description,
            mcp_tools=device_data.mcp_tools,  # 如果MCP验证成功，将使用服务器返回的工具列表
            supported_data_types=device_data.supported_data_types,
            websocket_endpoint=device_data.websocket_endpoint,
            system_prompt=device_data.system_prompt,
            intent_keywords=device_data.intent_keywords,
            hardware_info=device_data.hardware_info,
            location=device_data.location,
            max_data_size_mb=device_data.max_data_size_mb
        )
        
        # 启动EventStream管理
        event_stream_manager.start_maintenance()
        
        logger.info(f"✅ 终端设备注册成功: {device_data.device_id}")
        
        def normalize_mcp_tools(mcp_tools):
            """确保mcp_tools是字符串数组"""
            if not mcp_tools:
                return []
            if isinstance(mcp_tools, list):
                # 如果是字典列表，提取name字段
                if mcp_tools and isinstance(mcp_tools[0], dict):
                    return [tool.get("name", str(tool)) for tool in mcp_tools if tool.get("name")]
                # 如果是字符串列表，直接返回
                return [str(tool) for tool in mcp_tools]
            return []
        
        return TerminalDeviceResponse(
            id=device.id,
            device_id=device.device_id,
            name=device.name,
            description=device.description or "",
            device_type=device.device_type.value,
            mcp_server_url=device.mcp_server_url,

            mcp_tools=normalize_mcp_tools(device.mcp_tools),
            websocket_endpoint=device.websocket_endpoint,
            supported_data_types=device.supported_data_types,
            max_data_size_mb=device.max_data_size_mb,
            is_connected=device.is_connected,
            location=device.location,
            hardware_info=device.hardware_info,
            system_prompt=device.system_prompt,
            intent_keywords=device.intent_keywords,
            created_at=device.created_at.isoformat(),
            updated_at=device.updated_at.isoformat(),
            last_seen=device.last_seen.isoformat() if device.last_seen else None
        )
        
    except Exception as e:
        logger.error(f"❌ 终端设备注册失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Device registration failed: {str(e)}"
        )


@router.put("/{device_id}", response_model=TerminalDeviceResponse)
async def update_terminal_device(
    device_id: str,
    update_data: TerminalDeviceUpdate,
    db: Session = Depends(get_db)
):
    """更新终端设备信息"""
    try:
        device = terminal_device_manager.get_device(device_id)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device not found: {device_id}"
            )
        
        # 更新设备信息
        update_dict = update_data.dict(exclude_unset=True)
        if update_dict:
            # 重新注册以更新信息
            terminal_device_manager.register_device(
                device_id=device_id,
                name=update_dict.get("name", device.name),
                device_type=device.device_type,
                mcp_server_url=update_dict.get("mcp_server_url", device.mcp_server_url),
                description=update_dict.get("description", device.description),
                # 移除 mcp_capabilities，使用 mcp_tools
                mcp_tools=update_dict.get("mcp_tools", device.mcp_tools),
                supported_data_types=[DataType(dt) for dt in update_dict.get("supported_data_types", device.supported_data_types)],
                websocket_endpoint=update_dict.get("websocket_endpoint", device.websocket_endpoint),
                system_prompt=update_dict.get("system_prompt", device.system_prompt),
                intent_keywords=update_dict.get("intent_keywords", device.intent_keywords),
                hardware_info=update_dict.get("hardware_info", device.hardware_info),
                location=update_dict.get("location", device.location),
                max_data_size_mb=update_dict.get("max_data_size_mb", device.max_data_size_mb)
            )
            
            # 重新获取更新后的设备
            device = terminal_device_manager.get_device(device_id)
        
        def normalize_mcp_tools(mcp_tools):
            """确保mcp_tools是字符串数组"""
            if not mcp_tools:
                return []
            if isinstance(mcp_tools, list):
                # 如果是字典列表，提取name字段
                if mcp_tools and isinstance(mcp_tools[0], dict):
                    return [tool.get("name", str(tool)) for tool in mcp_tools if tool.get("name")]
                # 如果是字符串列表，直接返回
                return [str(tool) for tool in mcp_tools]
            return []
        
        return TerminalDeviceResponse(
            id=device.id,
            device_id=device.device_id,
            name=device.name,
            description=device.description or "",
            device_type=device.device_type.value,
            mcp_server_url=device.mcp_server_url,

            mcp_tools=normalize_mcp_tools(device.mcp_tools),
            websocket_endpoint=device.websocket_endpoint,
            supported_data_types=device.supported_data_types,
            max_data_size_mb=device.max_data_size_mb,
            is_connected=device.is_connected,
            location=device.location,
            hardware_info=device.hardware_info,
            system_prompt=device.system_prompt,
            intent_keywords=device.intent_keywords,
            created_at=device.created_at.isoformat(),
            updated_at=device.updated_at.isoformat(),
            last_seen=device.last_seen.isoformat() if device.last_seen else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 更新终端设备失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Device update failed: {str(e)}"
        )


@router.get("/", response_model=List[TerminalDeviceResponse])
async def get_terminal_devices(
    online_only: bool = False,
    device_type: Optional[TerminalDeviceType] = None,
    tool_name: Optional[str] = None,  # 使用工具名称而不是能力
    db: Session = Depends(get_db)
):
    """获取终端设备列表"""
    try:
        if tool_name:
            devices = terminal_device_manager.get_devices_by_tool(tool_name)
        else:
            devices = terminal_device_manager.get_all_devices(online_only=online_only)
        
        # 按设备类型过滤
        if device_type:
            devices = [d for d in devices if d.device_type == device_type]
        
        def normalize_mcp_tools(mcp_tools):
            """确保mcp_tools是字符串数组"""
            if not mcp_tools:
                return []
            if isinstance(mcp_tools, list):
                # 如果是字典列表，提取name字段
                if mcp_tools and isinstance(mcp_tools[0], dict):
                    return [tool.get("name", str(tool)) for tool in mcp_tools if tool.get("name")]
                # 如果是字符串列表，直接返回
                return [str(tool) for tool in mcp_tools]
            return []
        
        return [
            TerminalDeviceResponse(
                id=device.id,
                device_id=device.device_id,
                name=device.name,
                description=device.description or "",
                device_type=device.device_type.value,
                mcp_server_url=device.mcp_server_url,
    
                mcp_tools=normalize_mcp_tools(device.mcp_tools),
                websocket_endpoint=device.websocket_endpoint,
                supported_data_types=device.supported_data_types,
                max_data_size_mb=device.max_data_size_mb,
                is_connected=device.is_connected,
                location=device.location,
                hardware_info=device.hardware_info,
                system_prompt=device.system_prompt,
                intent_keywords=device.intent_keywords,
                created_at=device.created_at.isoformat(),
                updated_at=device.updated_at.isoformat(),
                last_seen=device.last_seen.isoformat() if device.last_seen else None
            )
            for device in devices
        ]
        
    except Exception as e:
        logger.error(f"❌ 获取终端设备列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get devices: {str(e)}"
        )


@router.get("/{device_id}", response_model=TerminalDeviceResponse)
async def get_terminal_device(device_id: str, db: Session = Depends(get_db)):
    """获取单个终端设备信息"""
    try:
        device = terminal_device_manager.get_device(device_id)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device not found: {device_id}"
            )
        
        def normalize_mcp_tools(mcp_tools):
            """确保mcp_tools是字符串数组"""
            if not mcp_tools:
                return []
            if isinstance(mcp_tools, list):
                # 如果是字典列表，提取name字段
                if mcp_tools and isinstance(mcp_tools[0], dict):
                    return [tool.get("name", str(tool)) for tool in mcp_tools if tool.get("name")]
                # 如果是字符串列表，直接返回
                return [str(tool) for tool in mcp_tools]
            return []
        
        return TerminalDeviceResponse(
            id=device.id,
            device_id=device.device_id,
            name=device.name,
            description=device.description or "",
            device_type=device.device_type.value,
            mcp_server_url=device.mcp_server_url,

            mcp_tools=normalize_mcp_tools(device.mcp_tools),
            websocket_endpoint=device.websocket_endpoint,
            supported_data_types=device.supported_data_types,
            max_data_size_mb=device.max_data_size_mb,
            is_connected=device.is_connected,
            location=device.location,
            hardware_info=device.hardware_info,
            system_prompt=device.system_prompt,
            intent_keywords=device.intent_keywords,
            created_at=device.created_at.isoformat(),
            updated_at=device.updated_at.isoformat(),
            last_seen=device.last_seen.isoformat() if device.last_seen else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取终端设备失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get device: {str(e)}"
        )


@router.delete("/{device_id}")
async def unregister_terminal_device(device_id: str, db: Session = Depends(get_db)):
    """注销终端设备"""
    try:
        success = terminal_device_manager.unregister_device(device_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device not found: {device_id}"
            )
        
        # 清理相关资源
        # event_stream_manager.remove_device_stream(device_id)  # 方法不存在，暂时注释
        
        return {"message": f"Device unregistered successfully: {device_id}"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 注销终端设备失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Device unregistration failed: {str(e)}"
        )


@router.post("/{device_id}/heartbeat")
async def device_heartbeat(device_id: str, db: Session = Depends(get_db)):
    """设备心跳"""
    try:
        success = terminal_device_manager.heartbeat_device(device_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device not found: {device_id}"
            )
        
        return {
            "device_id": device_id,
            "heartbeat_time": datetime.utcnow().isoformat(),
            "status": "ok"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 设备心跳失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Heartbeat failed: {str(e)}"
        )


@router.get("/{device_id}/stream-status", response_model=EventStreamStatus)
async def get_device_stream_status(device_id: str, db: Session = Depends(get_db)):
    """获取设备EventStream状态"""
    try:
        status_data = event_stream_manager.get_stream_status(device_id)
        if not status_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stream not found for device: {device_id}"
            )
        
        return EventStreamStatus(**status_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 获取流状态失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stream status: {str(e)}"
        )


@router.get("/streams/status")
async def get_all_streams_status():
    """获取所有设备的EventStream状态"""
    try:
        all_status = event_stream_manager.get_all_streams_status()
        return {
            "total_streams": len(all_status),
            "streams": all_status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ 获取所有流状态失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get streams status: {str(e)}"
        )


@router.post("/{device_id}/mcp-call", response_model=MCPToolCallResponse)
async def call_mcp_tool(
    device_id: str,
    call_request: MCPToolCallRequest,
    db: Session = Depends(get_db)
):
    """调用设备的MCP工具"""
    try:
        # 验证设备存在
        device = terminal_device_manager.get_device(device_id)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device not found: {device_id}"
            )
        
        if not device.is_connected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Device is offline: {device_id}"
            )
        
        logger.info(f"🔧 收到MCP工具调用请求: {device_id} -> {call_request.tool_name}")
        
        # 调用实际的MCP工具
        result = await terminal_device_manager.call_device_mcp_tool(
            device_id=device_id,
            tool_name=call_request.tool_name,
            parameters=call_request.parameters,
            timeout=call_request.timeout_seconds
        )
        
        if result["success"]:
            logger.info(f"✅ MCP工具调用成功: {device_id} -> {call_request.tool_name}")
            return MCPToolCallResponse(
                success=True,
                result=result.get("result", {}),
                execution_time_ms=result.get("execution_time_ms", 0)
            )
        else:
            logger.warning(f"⚠️ MCP工具调用失败: {device_id} -> {call_request.tool_name} - {result.get('error')}")
            return MCPToolCallResponse(
                success=False,
                error=result.get("error", "Unknown error"),
                execution_time_ms=result.get("execution_time_ms", 0)
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ MCP工具调用失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MCP tool call failed: {str(e)}"
        )


@router.get("/mcp-tools/config")
async def get_mcp_tools_config():
    """获取所有设备的MCP工具配置"""
    try:
        mcp_tools = terminal_device_manager.get_mcp_tools_config()
        return {
            "total_devices": len(mcp_tools),
            "mcp_tools": mcp_tools,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ 获取MCP工具配置失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get MCP tools config: {str(e)}"
        )


@router.post("/mcp-call-by-intent", response_model=MCPToolCallResponse)
async def call_mcp_tool_by_intent(
    call_request: MCPToolCallByIntentRequest,
    db: Session = Depends(get_db)
):
    """根据意图调用MCP工具（使用LLM智能选择设备和工具）"""
    try:
        logger.info(f"🎯 收到按意图调用MCP工具请求: {call_request.intent} -> {call_request.tool_name or 'auto-select'}")
        
        # 使用MCP标准的工具发现和选择
        result = await terminal_device_manager.discover_and_select_tool(
            intent=call_request.intent,
            tool_name=call_request.tool_name,
            parameters=call_request.parameters,
            prefer_device_id=call_request.prefer_device_id
        )
        
        if result["success"]:
            logger.info(f"✅ 按意图调用MCP工具成功: {call_request.intent} -> {result.get('tool_name')} (设备: {result.get('selected_device')})")
            return MCPToolCallResponse(
                success=True,
                result=result.get("result", {}),
                execution_time_ms=result.get("execution_time_ms", 0)
            )
        else:
            logger.warning(f"⚠️ 按意图调用MCP工具失败: {call_request.intent} - {result.get('error')}")
            return MCPToolCallResponse(
                success=False,
                error=result.get("error", "Unknown error"),
                execution_time_ms=result.get("execution_time_ms", 0)
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 按能力调用MCP工具失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MCP tool call by capability failed: {str(e)}"
        )


@router.post("/{device_id}/mcp-test", response_model=MCPConnectionTestResponse)
async def test_device_mcp_connection(
    device_id: str,
    db: Session = Depends(get_db)
):
    """测试设备MCP连接"""
    try:
        # 验证设备存在
        device = terminal_device_manager.get_device(device_id)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device not found: {device_id}"
            )
        
        logger.info(f"🔍 测试设备MCP连接: {device_id}")
        
        # 测试连接
        result = await terminal_device_manager.test_device_mcp_connection(device_id)
        
        if result["success"]:
            logger.info(f"✅ 设备MCP连接正常: {device_id}")
        else:
            logger.warning(f"⚠️ 设备MCP连接失败: {device_id} - {result.get('error')}")
        
        return MCPConnectionTestResponse(
            success=result["success"],
            device_id=device_id,
            server_url=result.get("server_url"),
            available_tools=result.get("available_tools"),
            error=result.get("error"),
            message=result.get("message")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 测试设备MCP连接失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"MCP connection test failed: {str(e)}"
        )


@router.get("/websocket/status")
async def get_websocket_status():
    """获取WebSocket连接状态"""
    try:
        status_data = websocket_data_manager.get_connection_status()
        return status_data
        
    except Exception as e:
        logger.error(f"❌ 获取WebSocket状态失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get WebSocket status: {str(e)}"
        )


@router.get("/intent-analysis/status")
async def get_intent_analysis_status():
    """获取意图识别状态"""
    try:
        stats = multimodal_llm_agent_manager.get_overall_statistics()
        return stats
        
    except Exception as e:
        logger.error(f"❌ 获取意图识别状态失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get intent analysis status: {str(e)}"
        )


# === WebSocket端点 ===

@router.websocket("/ws/{device_id}")
async def websocket_device_data(websocket: WebSocket, device_id: str):
    """
    设备数据传输WebSocket端点
    
    支持实时传输文本/音频/图片/视频数据
    """
    try:
        # 连接设备
        success = await websocket_data_manager.connect_device(websocket, device_id)
        if not success:
            return
        
        # 处理数据传输
        await websocket_data_manager.handle_device_data(device_id)
        
    except WebSocketDisconnect:
        logger.info(f"🔴 设备WebSocket断开: {device_id}")
    except Exception as e:
        logger.error(f"❌ 设备WebSocket异常 {device_id}: {e}")
    finally:
        await websocket_data_manager.disconnect_device(device_id)
