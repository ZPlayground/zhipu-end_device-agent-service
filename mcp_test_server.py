#!/usr/bin/env python3
"""
MCP测试服务器
模拟终端设备的MCP服务器，用于演示A2A→LLM→MCP完整流程
"""
import json
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional, Union
import uvicorn

# 导入配置
from config.settings import settings

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="MCP Test Server", description="模拟终端设备的MCP服务器", version="1.0.0")

class MCPRequest(BaseModel):
    """MCP请求模型"""
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    method: str
    params: Optional[Dict[str, Any]] = None

class MCPResponse(BaseModel):
    """MCP响应模型"""
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

# 模拟设备数据
DEVICE_DATA = {
    "device_id": "camera_001",
    "name": "智能摄像头",
    "location": "办公室",
    "status": "online",
    "temperature": 25.6,
    "humidity": 60.2,
    "battery_level": 85,
    "last_image": f"image_captured_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
    "scene_analysis": "办公室环境，光线充足，有2个人在工作"
}

# 支持的MCP工具
MCP_TOOLS = [
    {
        "name": "capture_image",
        "description": "拍摄图像",
        "inputSchema": {
            "type": "object",
            "properties": {
                "resolution": {"type": "string", "description": "图像分辨率", "default": "1920x1080"},
                "format": {"type": "string", "description": "图像格式", "default": "jpg"}
            }
        }
    },
    {
        "name": "analyze_scene",
        "description": "分析当前场景",
        "inputSchema": {
            "type": "object",
            "properties": {
                "detail_level": {"type": "string", "description": "分析详细程度", "enum": ["basic", "detailed"], "default": "basic"}
            }
        }
    },
    {
        "name": "read_sensor_data",
        "description": "读取传感器数据",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sensor_type": {"type": "string", "description": "传感器类型", "enum": ["temperature", "humidity", "battery", "all"], "default": "all"}
            }
        }
    }
]

@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "MCP Test Server",
        "version": "1.0.0",
        "device": DEVICE_DATA["name"],
        "status": "running",
        "mcp_endpoint": "/mcp",
        "supported_tools": [tool["name"] for tool in MCP_TOOLS]
    }

@app.post("/mcp")
async def mcp_endpoint(request: MCPRequest):
    """MCP协议端点"""
    try:
        logger.info(f"🔧 收到MCP请求: {request.method}")
        
        if request.method == "tools/list":
            # 返回支持的工具列表
            return MCPResponse(
                id=request.id,
                result={
                    "tools": MCP_TOOLS
                }
            ).dict()
        
        elif request.method == "tools/call":
            # 调用工具
            if not request.params:
                raise HTTPException(status_code=400, detail="缺少工具调用参数")
            
            tool_name = request.params.get("name")
            arguments = request.params.get("arguments", {})
            
            logger.info(f"🛠️ 调用工具: {tool_name}, 参数: {arguments}")
            
            # 执行工具逻辑
            if tool_name == "capture_image":
                result = await execute_capture_image(arguments)
            elif tool_name == "analyze_scene":
                result = await execute_analyze_scene(arguments)
            elif tool_name == "read_sensor_data":
                result = await execute_read_sensor_data(arguments)
            else:
                raise HTTPException(status_code=400, detail=f"不支持的工具: {tool_name}")
            
            return MCPResponse(
                id=request.id,
                result=result
            ).dict()
        
        else:
            raise HTTPException(status_code=400, detail=f"不支持的方法: {request.method}")
    
    except Exception as e:
        logger.error(f"❌ MCP请求处理失败: {e}")
        return MCPResponse(
            id=request.id,
            error={
                "code": -32603,
                "message": "Internal error",
                "data": str(e)
            }
        ).dict()

async def execute_capture_image(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """执行图像拍摄"""
    resolution = arguments.get("resolution", "1920x1080")
    format_type = arguments.get("format", "jpg")
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    image_filename = f"capture_{timestamp}.{format_type}"
    
    # 模拟拍摄过程
    logger.info(f"📸 拍摄图像: {resolution}, 格式: {format_type}")
    
    # 更新设备数据
    DEVICE_DATA["last_image"] = image_filename
    
    return {
        "success": True,
        "message": "图像拍摄成功",
        "data": {
            "filename": image_filename,
            "resolution": resolution,
            "format": format_type,
            "timestamp": timestamp,
            "file_path": f"/data/uploads/{image_filename}",
            "device_id": DEVICE_DATA["device_id"],
            "location": DEVICE_DATA["location"]
        },
        "execution_time": "0.8秒"
    }

async def execute_analyze_scene(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """执行场景分析"""
    detail_level = arguments.get("detail_level", "basic")
    
    logger.info(f"🔍 分析场景: 详细程度={detail_level}")
    
    if detail_level == "detailed":
        analysis = {
            "environment": "办公室环境",
            "lighting": "自然光充足，色温约5000K",
            "objects_detected": ["桌子", "椅子", "电脑", "文档"],
            "people_count": 2,
            "people_activities": ["使用电脑", "阅读文档"],
            "noise_level": "低",
            "temperature_estimate": "舒适 (23-26°C)",
            "safety_status": "安全",
            "recommendations": ["保持当前照明", "注意定时休息"]
        }
    else:
        analysis = {
            "environment": "办公室",
            "people_count": 2,
            "lighting": "充足",
            "status": "正常工作状态"
        }
    
    # 更新设备数据
    DEVICE_DATA["scene_analysis"] = f"最新分析: {analysis.get('environment')}, {analysis.get('people_count')}人"
    
    return {
        "success": True,
        "message": "场景分析完成",
        "data": {
            "analysis": analysis,
            "timestamp": datetime.now().isoformat(),
            "device_id": DEVICE_DATA["device_id"],
            "location": DEVICE_DATA["location"],
            "detail_level": detail_level
        },
        "execution_time": "1.2秒"
    }

async def execute_read_sensor_data(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """执行传感器数据读取"""
    sensor_type = arguments.get("sensor_type", "all")
    
    logger.info(f"📊 读取传感器数据: {sensor_type}")
    
    # 模拟传感器数据更新
    import random
    DEVICE_DATA["temperature"] = round(25.0 + random.uniform(-2, 2), 1)
    DEVICE_DATA["humidity"] = round(60.0 + random.uniform(-5, 5), 1)
    DEVICE_DATA["battery_level"] = max(20, DEVICE_DATA["battery_level"] + random.randint(-2, 1))
    
    if sensor_type == "temperature":
        sensor_data = {"temperature": DEVICE_DATA["temperature"], "unit": "°C"}
    elif sensor_type == "humidity":
        sensor_data = {"humidity": DEVICE_DATA["humidity"], "unit": "%"}
    elif sensor_type == "battery":
        sensor_data = {"battery_level": DEVICE_DATA["battery_level"], "unit": "%"}
    else:  # all
        sensor_data = {
            "temperature": {"value": DEVICE_DATA["temperature"], "unit": "°C"},
            "humidity": {"value": DEVICE_DATA["humidity"], "unit": "%"},
            "battery_level": {"value": DEVICE_DATA["battery_level"], "unit": "%"},
            "device_status": DEVICE_DATA["status"]
        }
    
    return {
        "success": True,
        "message": f"传感器数据读取成功 ({sensor_type})",
        "data": {
            "sensor_data": sensor_data,
            "timestamp": datetime.now().isoformat(),
            "device_id": DEVICE_DATA["device_id"],
            "location": DEVICE_DATA["location"],
            "sensor_type": sensor_type
        },
        "execution_time": "0.3秒"
    }

@app.get("/status")
async def get_device_status():
    """获取设备状态"""
    return {
        "device": DEVICE_DATA,
        "supported_tools": [tool["name"] for tool in MCP_TOOLS],
        "server_status": "running",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/tools")
async def get_tools():
    """获取支持的工具（简化版本）"""
    return {
        "tools": MCP_TOOLS,
        "count": len(MCP_TOOLS)
    }

if __name__ == "__main__":
    print("🚀 启动MCP测试服务器...")
    print("📋 支持的工具:")
    for tool in MCP_TOOLS:
        print(f"   🔹 {tool['name']}: {tool['description']}")
    print(f"🌐 服务器地址: {settings.get_mcp_test_url()}")
    print(f"🔧 MCP端点: {settings.get_mcp_test_url()}/mcp")
    print("=" * 50)
    
    uvicorn.run(
        "mcp_test_server:app",
        host=settings.mcp_test_host,
        port=settings.mcp_test_port,
        log_level="info",
        reload=False
    )