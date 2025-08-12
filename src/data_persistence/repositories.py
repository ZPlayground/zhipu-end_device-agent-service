"""
Repository pattern for data access
"""
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from sqlalchemy.orm import Session
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .models import (
        User, UserSession, MessageInbox, Task, A2AAgent, 
        AgentInteraction, MessageType, TaskStatus  # TerminalAgent已重构为TerminalDevice
    )
else:
    # 运行时导入
    from .models import (
        User, UserSession, MessageInbox, Task, A2AAgent, 
        AgentInteraction, MessageType, TaskStatus  # TerminalAgent已重构为TerminalDevice
    )
import uuid


class UserRepository:
    """用户数据访问层"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_user(self, username: str, email: str, hashed_password: str) -> "User":
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
    
    def get_user_by_id(self, user_id: int) -> Optional["User"]:
        return self.db.query(User).filter(User.id == user_id).first()
    
    def get_user_by_username(self, username: str) -> Optional["User"]:
        return self.db.query(User).filter(User.username == username).first()
    
    def get_user_by_email(self, email: str) -> Optional["User"]:
        return self.db.query(User).filter(User.email == email).first()
    
    def get_all_users(self, limit: int = 100, offset: int = 0) -> List["User"]:
        """获取所有用户"""
        return self.db.query(User).offset(offset).limit(limit).all()
    
    def update_user(self, user_id: int, **kwargs) -> Optional["User"]:
        """更新用户信息"""
        user = self.get_user_by_id(user_id)
        if user:
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            self.db.commit()
            self.db.refresh(user)
        return user
    
    def delete_user(self, user_id: int) -> bool:
        """删除用户"""
        user = self.get_user_by_id(user_id)
        if user:
            self.db.delete(user)
            self.db.commit()
            return True
        return False


class MessageInboxRepository:
    """消息收件箱数据访问层"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_message(
        self, 
        user_id: int,
        message_type: MessageType,
        content: str,
        metadata: Dict[str, Any] = None,
        source_agent: str = None,
        correlation_id: str = None
    ) -> MessageInbox:
        message = MessageInbox(
            user_id=user_id,
            message_type=message_type,
            content=content,
            metadata_json=metadata or {},
            source_agent=source_agent,
            correlation_id=correlation_id
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message
    
    def get_user_messages(
        self, 
        user_id: int, 
        limit: int = 50, 
        offset: int = 0,
        unread_only: bool = False
    ) -> List[MessageInbox]:
        query = self.db.query(MessageInbox).filter(MessageInbox.user_id == user_id)
        
        if unread_only:
            query = query.filter(MessageInbox.is_read == False)
        
        return query.order_by(MessageInbox.created_at.desc()).offset(offset).limit(limit).all()
    
    def get_messages_since(
        self, 
        user_id: int, 
        since: datetime, 
        limit: int = 100
    ) -> List[MessageInbox]:
        """获取指定时间之后的消息（用于断线重连同步）"""
        return self.db.query(MessageInbox).filter(
            MessageInbox.user_id == user_id,
            MessageInbox.created_at > since
        ).order_by(MessageInbox.created_at.asc()).limit(limit).all()
    
    def mark_as_read(self, message_id: int, user_id: int) -> bool:
        message = self.db.query(MessageInbox).filter(
            MessageInbox.id == message_id,
            MessageInbox.user_id == user_id
        ).first()
        
        if message:
            message.is_read = True
            message.read_at = datetime.utcnow()
            self.db.commit()
            return True
        return False


class TaskRepository:
    """任务数据访问层"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_task(
        self,
        user_id: int,
        task_type: str,
        input_data: Dict[str, Any],
        target_agent: str = None,
        correlation_id: str = None,
        webhook_url: str = None
    ) -> Task:
        task = Task(
            id=str(uuid.uuid4()),
            user_id=user_id,
            task_type=task_type,
            input_data=input_data,
            target_agent=target_agent,
            correlation_id=correlation_id or str(uuid.uuid4()),
            webhook_url=webhook_url
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task
    
    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        return self.db.query(Task).filter(Task.id == task_id).first()
    
    def update_task_status(
        self, 
        task_id: str, 
        status: TaskStatus, 
        output_data: Dict[str, Any] = None,
        error_message: str = None
    ) -> bool:
        task = self.db.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = status
            if output_data:
                task.output_data = output_data
            if error_message:
                task.error_message = error_message
            if status == TaskStatus.PROCESSING and not task.started_at:
                task.started_at = datetime.utcnow()
            elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                task.completed_at = datetime.utcnow()
            
            self.db.commit()
            return True
        return False
    
    def get_user_tasks(self, user_id: int, limit: int = 50) -> List[Task]:
        return self.db.query(Task).filter(
            Task.user_id == user_id
        ).order_by(Task.created_at.desc()).limit(limit).all()


class A2AAgentRepository:
    """A2A Agent数据访问层"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_agent(
        self,
        name: str,
        endpoint_url: str,
        description: str = None,
        api_key: str = None,
        capabilities: List[str] = None
    ) -> A2AAgent:
        agent = A2AAgent(
            name=name,
            description=description,
            endpoint_url=endpoint_url,
            api_key=api_key,
            capabilities=capabilities or []
        )
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)
        return agent
    
    def get_active_agents(self) -> List[A2AAgent]:
        return self.db.query(A2AAgent).filter(A2AAgent.is_active == True).all()
    
    def get_all_agents(self) -> List[A2AAgent]:
        """获取所有Agent，包括活跃和非活跃的"""
        return self.db.query(A2AAgent).all()
    
    def get_agent_by_name(self, name: str) -> Optional[A2AAgent]:
        return self.db.query(A2AAgent).filter(A2AAgent.name == name).first()
    
    def find_agents_by_capability(self, capability: str) -> List[A2AAgent]:
        return self.db.query(A2AAgent).filter(
            A2AAgent.capabilities.contains([capability]),
            A2AAgent.is_active == True
        ).all()


class AgentInteractionRepository:
    """Agent交互记录数据访问层"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_interaction(
        self,
        correlation_id: str,
        source_agent: str,
        target_agent: str,
        request_data: Dict[str, Any],
        status: str = "pending"
    ) -> AgentInteraction:
        interaction = AgentInteraction(
            correlation_id=correlation_id,
            source_agent=source_agent,
            target_agent=target_agent,
            request_data=request_data,
            status=status
        )
        self.db.add(interaction)
        self.db.commit()
        self.db.refresh(interaction)
        return interaction
    
    def update_interaction_response(
        self,
        correlation_id: str,
        response_data: Dict[str, Any],
        status: str
    ) -> bool:
        interaction = self.db.query(AgentInteraction).filter(
            AgentInteraction.correlation_id == correlation_id
        ).first()
        
        if interaction:
            interaction.response_data = response_data
            interaction.status = status
            interaction.completed_at = datetime.utcnow()
            self.db.commit()
            return True
        return False


# TerminalAgentRepository已重构为TerminalDeviceManager
# 请使用src.core_application.terminal_device_manager.TerminalDeviceManager
