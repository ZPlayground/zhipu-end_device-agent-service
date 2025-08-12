"""
Data Persistence Layer Package
"""

# 数据库管理
from .database import DatabaseManager, get_db, create_tables

# 直接从.py文件导入模型
from .models import (
    User, UserSession, MessageInbox, Task, A2AAgent, 
    AgentInteraction, MessageType, TaskStatus, Base  # TerminalAgent已重构为TerminalDevice
)

# 直接从.py文件导入Repository
from .repositories import (
    UserRepository, MessageInboxRepository, TaskRepository,
    A2AAgentRepository, AgentInteractionRepository  # TerminalAgentRepository已重构为TerminalDeviceManager
)

__all__ = [
    # 数据库工具
    "DatabaseManager", "get_db", "create_tables",
    # 数据模型
    "User", "UserSession", "MessageInbox", "Task", "A2AAgent", 
    "AgentInteraction",  # TerminalAgent已重构为TerminalDevice
    # 枚举类型
    "MessageType", "TaskStatus", "Base",
    # Repository层
    "UserRepository", "MessageInboxRepository", "TaskRepository",
    "A2AAgentRepository", "AgentInteractionRepository"  # TerminalAgentRepository已重构为TerminalDeviceManager
]
