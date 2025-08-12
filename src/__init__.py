"""
A2A Agent Service Package
"""

__version__ = "1.0.0"
__author__ = "Zhipu Intern Team"
__description__ = "A comprehensive Agent-to-Agent service framework"

from src.user_interaction import app
from src.core_application import A2ATaskDispatcher, A2ANotificationReceiver
from src.async_execution import message_queue, worker_manager
from src.data_persistence import create_tables, get_db
from src.external_services import LLMService, zhipu_a2a_server, zhipu_a2a_client

__all__ = [
    "app", "A2ATaskDispatcher", "A2ANotificationReceiver",
    "message_queue", "worker_manager", 
    "create_tables", "get_db",
    "LLMService", "zhipu_a2a_server", "zhipu_a2a_client"
]
