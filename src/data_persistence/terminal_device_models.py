"""
终端设备重构专用数据模型
Terminal Device Refactored Models

重构要点：
1. 终端设备不再暴露为A2A Agent，只注册设备信息到数据库
2. 假设所有终端设备具有MCP Server，作为MCP工具调用
3. 使用WebSocket进行数据互联
4. 每个设备有独立的EventStream实例管理数据
5. 多模态LLM Agent定期读取EventStream进行意图识别
"""
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, 
    ForeignKey, JSON, Enum as SQLEnum, LargeBinary, Float
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
import uuid


Base = declarative_base()


class TerminalDeviceType(str, Enum):
    """终端设备类型"""
    IOT_SENSOR = "iot_sensor"
    SMART_CAMERA = "smart_camera"
    SMART_SPEAKER = "smart_speaker"
    MOBILE_APP = "mobile_app"
    DESKTOP_APP = "desktop_app"
    INDUSTRIAL_PLC = "industrial_plc"
    PRINTER = "printer"
    DISPLAY = "display"
    ROBOT = "robot"
    OTHER = "other"


class DataType(str, Enum):
    """数据类型"""
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    VIDEO = "video"
    SENSOR_DATA = "sensor_data"
    JSON_DATA = "json_data"
    BINARY = "binary"


# 移除 MCPCapability 枚举，因为MCP标准中没有预定义能力概念
# MCP标准直接使用工具名称和描述，由LLM进行语义匹配


class TerminalDevice(Base):
    """重构的终端设备表 - 不暴露为A2A Agent"""
    __tablename__ = "terminal_devices"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(100), unique=True, index=True, nullable=False)  # 设备唯一标识
    name = Column(String(200), nullable=False)  # 设备名称
    description = Column(Text)  # 设备描述
    device_type = Column(SQLEnum(TerminalDeviceType), nullable=False)  # 设备类型
    
    # MCP服务器信息
    mcp_server_url = Column(String(500), nullable=False)  # MCP服务器地址
    mcp_tools = Column(JSON, default=[])  # 可用的MCP工具列表（符合MCP标准）
    # 移除 mcp_capabilities，因为MCP标准中没有预定义能力概念
    # MCP标准直接使用工具名称，由LLM根据工具描述进行语义匹配
    
    # WebSocket连接信息
    websocket_endpoint = Column(String(500))  # WebSocket连接端点
    is_connected = Column(Boolean, default=False)  # 是否在线
    last_ping = Column(DateTime(timezone=True))  # 最后心跳时间
    
    # 设备特性
    supported_data_types = Column(JSON, default=[])  # 支持的数据类型
    max_data_size_mb = Column(Integer, default=10)  # 最大数据包大小(MB)
    location = Column(String(200))  # 设备位置
    hardware_info = Column(JSON, default={})  # 硬件信息
    
    # 系统prompt信息（用于意图识别）
    system_prompt = Column(Text)  # 设备特定的系统提示词
    intent_keywords = Column(JSON, default=[])  # 意图关键词
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_seen = Column(DateTime(timezone=True))  # 最后在线时间
    
    # 关系
    event_streams = relationship("DeviceEventStream", back_populates="device", cascade="all, delete-orphan")
    data_entries = relationship("DeviceDataEntry", back_populates="device", cascade="all, delete-orphan")
    intent_logs = relationship("IntentRecognitionLog", back_populates="device", cascade="all, delete-orphan")
    
    def to_mcp_tool_config(self):
        """转换为MCP工具配置（符合MCP标准）"""
        return {
            "device_id": self.device_id,
            "name": self.name,
            "description": self.description,
            "mcp_server_url": self.mcp_server_url,
            "tools": self.mcp_tools,  # MCP标准：直接使用工具列表
            "data_types": self.supported_data_types,
            "max_data_size_mb": self.max_data_size_mb,
            "system_prompt": self.system_prompt,
            "is_online": self.is_connected
        }


class DeviceEventStream(Base):
    """设备事件流实例 - 内存中的数据流缓存"""
    __tablename__ = "device_event_streams"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(100), ForeignKey("terminal_devices.device_id"), nullable=False)
    stream_id = Column(String(100), unique=True, nullable=False)  # 流实例ID
    
    # 流状态
    is_active = Column(Boolean, default=True)
    current_size_mb = Column(Float, default=0.0)  # 当前流大小(MB)
    max_size_mb = Column(Float, default=100.0)  # 最大流大小(MB)
    entry_count = Column(Integer, default=0)  # 当前条目数
    max_entries = Column(Integer, default=1000)  # 最大条目数
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_data_at = Column(DateTime(timezone=True))  # 最后数据时间
    last_read_at = Column(DateTime(timezone=True))  # 最后读取时间
    
    # 关系
    device = relationship("TerminalDevice", back_populates="event_streams")
    
    def should_persist_to_db(self):
        """判断是否应该持久化到数据库"""
        return (
            self.current_size_mb >= self.max_size_mb * 0.8 or  # 达到80%大小
            self.entry_count >= self.max_entries * 0.8  # 达到80%条目数
        )
    
    def should_release_memory(self):
        """判断是否应该释放内存"""
        return (
            self.current_size_mb >= self.max_size_mb or  # 达到100%大小
            self.entry_count >= self.max_entries  # 达到100%条目数
        )


class DeviceDataEntry(Base):
    """设备数据条目 - 持久化的数据记录"""
    __tablename__ = "device_data_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(100), ForeignKey("terminal_devices.device_id"), nullable=False)
    entry_id = Column(String(100), unique=True, nullable=False)  # 条目唯一标识
    
    # 数据信息
    data_type = Column(SQLEnum(DataType), nullable=False)
    content_text = Column(Text)  # 文本内容
    content_binary = Column(LargeBinary)  # 二进制内容
    content_json = Column(JSON)  # JSON内容
    file_path = Column(String(500))  # 文件路径（大文件）
    
    # 元数据
    size_bytes = Column(Integer, default=0)  # 数据大小
    mime_type = Column(String(100))  # MIME类型
    encoding = Column(String(50))  # 编码方式
    
    # 处理状态
    is_processed = Column(Boolean, default=False)  # 是否已被LLM处理
    processed_at = Column(DateTime(timezone=True))  # 处理时间
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))  # 过期时间（自动清理）
    
    # 关系
    device = relationship("TerminalDevice", back_populates="data_entries")


class IntentRecognitionLog(Base):
    """意图识别日志"""
    __tablename__ = "intent_recognition_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(100), ForeignKey("terminal_devices.device_id"), nullable=False)
    log_id = Column(String(100), unique=True, nullable=False)
    
    # 输入数据
    input_data_summary = Column(Text)  # 输入数据摘要
    data_count = Column(Integer, default=0)  # 数据条目数
    data_types = Column(JSON, default=[])  # 数据类型列表
    time_window_start = Column(DateTime(timezone=True))  # 时间窗口开始
    time_window_end = Column(DateTime(timezone=True))  # 时间窗口结束
    
    # LLM分析结果
    intent_detected = Column(Boolean, default=False)  # 是否检测到意图
    intent_type = Column(String(100))  # 意图类型
    confidence_score = Column(Float)  # 置信度分数
    reasoning = Column(Text)  # 推理过程
    
    # 任务创建
    task_created = Column(Boolean, default=False)  # 是否创建了任务
    task_id = Column(String(100))  # 任务ID
    task_description = Column(Text)  # 任务描述
    a2a_request_data = Column(JSON)  # A2A请求数据
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 关系
    device = relationship("TerminalDevice", back_populates="intent_logs")


class MultimodalLLMAgent(Base):
    """多模态LLM代理配置"""
    __tablename__ = "multimodal_llm_agents"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String(100), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    
    # 运行配置
    is_active = Column(Boolean, default=True)
    scan_interval_seconds = Column(Integer, default=30)  # 扫描间隔
    max_devices_per_scan = Column(Integer, default=10)  # 每次扫描最大设备数
    
    # LLM配置
    llm_provider = Column(String(50), default="openai")  # LLM提供商
    llm_model = Column(String(100), default="gpt-4o")  # 模型名称
    max_tokens = Column(Integer, default=2000)  # 最大token数
    temperature = Column(Float, default=0.3)  # 温度参数
    
    # 系统prompt
    base_system_prompt = Column(Text)  # 基础系统提示词
    intent_detection_prompt = Column(Text)  # 意图检测提示词
    
    # 统计信息
    total_scans = Column(Integer, default=0)
    total_intents_detected = Column(Integer, default=0)
    total_tasks_created = Column(Integer, default=0)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_scan_at = Column(DateTime(timezone=True))
    
    def to_config(self):
        """转换为配置字典"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "scan_interval_seconds": self.scan_interval_seconds,
            "max_devices_per_scan": self.max_devices_per_scan,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "base_system_prompt": self.base_system_prompt,
            "intent_detection_prompt": self.intent_detection_prompt
        }
