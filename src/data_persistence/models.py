"""
Database Models for A2A Agent Service
"""
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, 
    ForeignKey, JSON, Enum as SQLEnum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
import uuid


Base = declarative_base()


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing" 
    COMPLETED = "completed"
    FAILED = "failed"


class MessageType(str, Enum):
    USER_INPUT = "user_input"
    SYSTEM_RESPONSE = "system_response"
    A2A_REQUEST = "a2a_request"
    A2A_RESPONSE = "a2a_response"
    NOTIFICATION = "notification"
    SYSTEM_NOTIFICATION = "system_notification"


# 导入重构的终端设备模型
from src.data_persistence.terminal_device_models import (
    TerminalDevice, DeviceEventStream, DeviceDataEntry,
    IntentRecognitionLog, MultimodalLLMAgent,
    TerminalDeviceType, DataType
    # 移除 MCPCapability，因为MCP标准中没有预定义能力概念
)


class User(Base):
    """用户表"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # 关系
    sessions = relationship("UserSession", back_populates="user")
    messages = relationship("MessageInbox", back_populates="user")
    tasks = relationship("Task", back_populates="user")


class UserSession(Base):
    """用户会话表"""
    __tablename__ = "user_sessions"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_token = Column(String(255), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    # 关系
    user = relationship("User", back_populates="sessions")


class MessageInbox(Base):
    """消息收件箱 - 核心组件"""
    __tablename__ = "message_inbox"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_type = Column(SQLEnum(MessageType), nullable=False)
    content = Column(Text, nullable=False)
    metadata_json = Column(JSON, default={})
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    read_at = Column(DateTime(timezone=True), nullable=True)
    
    # A2A相关字段
    source_agent = Column(String(100), nullable=True)  # 来源Agent
    correlation_id = Column(String(36), nullable=True)  # 关联ID
    
    # 关系
    user = relationship("User", back_populates="messages")


class Task(Base):
    """任务表"""
    __tablename__ = "tasks"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_type = Column(String(50), nullable=False)  # 任务类型
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    input_data = Column(JSON, nullable=False)  # 输入数据
    output_data = Column(JSON, nullable=True)  # 输出数据
    error_message = Column(Text, nullable=True)
    
    # A2A相关字段
    target_agent = Column(String(100), nullable=True)  # 目标Agent
    correlation_id = Column(String(36), nullable=True)  # 关联ID
    webhook_url = Column(String(500), nullable=True)  # 回调URL
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # 关系
    user = relationship("User", back_populates="tasks")


class A2AAgent(Base):
    """A2A Agent注册表"""
    __tablename__ = "a2a_agents"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    endpoint_url = Column(String(500), nullable=False)
    api_key = Column(String(255), nullable=True)
    capabilities = Column(JSON, default=[])  # Agent能力列表
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AgentInteraction(Base):
    """Agent交互记录"""
    __tablename__ = "agent_interactions"
    
    id = Column(Integer, primary_key=True, index=True)
    correlation_id = Column(String(36), nullable=False, index=True)
    source_agent = Column(String(100), nullable=False)
    target_agent = Column(String(100), nullable=False)
    request_data = Column(JSON, nullable=False)
    response_data = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False)  # success, failed, pending
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


# TerminalAgent模型已重构为TerminalDevice模型
# 旧的TerminalAgent类已删除，请使用新的terminal_device_models.py中的TerminalDevice
