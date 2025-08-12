"""
Core Application Layer Package

主要组件：
- A2ATaskDispatcher: 完整的A2A协议实现，支持能力匹配和agent发现
- A2AIntentRouter: A2A协议的意图路由器
- A2ANotificationReceiver: A2A通知接收器
- SessionManager: 会话管理器
- SystemStateManager: 系统状态管理器
"""

# A2A协议实现
from .a2a_intent_router import A2AIntentRouter, A2ATaskDispatcher

# 其他组件
from .a2a_receiver import A2ANotificationReceiver
from .state_manager import SessionManager, SystemStateManager

__all__ = [
    # A2A协议实现
    "A2AIntentRouter", "A2ATaskDispatcher",
    
    # 其他组件
    "A2ANotificationReceiver",
    "SessionManager", "SystemStateManager"
]
