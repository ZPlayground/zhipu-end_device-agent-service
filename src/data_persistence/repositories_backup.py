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
        AgentInteraction, MessageType, TaskStatus, TerminalAgent
    )
else:
    # 运行时导入
    from .models import (
        User, UserSession, MessageInbox, Task, A2AAgent, 
        AgentInteraction, MessageType, TaskStatus, TerminalAgent
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


class TerminalAgentRepository:
    """终端Agent数据访问层"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def register_terminal_agent(
        self, 
        agent_id: str,
        name: str,
        description: str = "",
        device_type: str = "terminal",
        capabilities: List[str] = None,
        endpoint_url: str = None,
        metadata: Dict = None
    ) -> TerminalAgent:
        """注册新的终端Agent"""
        
        # 检查是否已存在
        existing = self.get_terminal_agent_by_id(agent_id)
        if existing:
            # 更新现有Agent
            return self.update_terminal_agent(
                agent_id, 
                name=name,
                description=description,
                device_type=device_type,
                capabilities=capabilities,
                endpoint_url=endpoint_url,
                metadata=metadata
            )
        
        agent = TerminalAgent(
            agent_id=agent_id,
            name=name,
            description=description,
            device_type=device_type,
            capabilities=capabilities or [],
            endpoint_url=endpoint_url,
            agent_metadata=metadata or {},
            status="active"
        )
        
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)
        
        return agent
    
    def get_terminal_agent_by_id(self, agent_id: str) -> Optional[TerminalAgent]:
        """根据Agent ID获取终端Agent"""
        return self.db.query(TerminalAgent).filter(
            TerminalAgent.agent_id == agent_id
        ).first()
    
    def update_terminal_agent(
        self,
        agent_id: str,
        name: str = None,
        description: str = None,
        device_type: str = None,
        capabilities: List[str] = None,
        endpoint_url: str = None,
        metadata: Dict = None,
        status: str = None
    ) -> Optional[TerminalAgent]:
        """更新终端Agent信息"""
        
        agent = self.get_terminal_agent_by_id(agent_id)
        if not agent:
            return None
        
        if name is not None:
            agent.name = name
        if description is not None:
            agent.description = description
        if device_type is not None:
            agent.device_type = device_type
        if capabilities is not None:
            agent.capabilities = capabilities
        if endpoint_url is not None:
            agent.endpoint_url = endpoint_url
        if metadata is not None:
            agent.agent_metadata = metadata
        if status is not None:
            agent.status = status
        
        self.db.commit()
        self.db.refresh(agent)
        
        return agent
    
    def get_all_terminal_agents(
        self, 
        device_type: str = None,
        status: str = None,
        limit: int = 100
    ) -> List[TerminalAgent]:
        """获取所有终端Agent"""
        
        query = self.db.query(TerminalAgent)
        
        if device_type:
            query = query.filter(TerminalAgent.device_type == device_type)
        if status:
            query = query.filter(TerminalAgent.status == status)
        
        return query.order_by(TerminalAgent.last_seen.desc()).limit(limit).all()
    
    def update_last_seen(self, agent_id: str) -> bool:
        """更新Agent最后在线时间"""
        agent = self.get_terminal_agent_by_id(agent_id)
        if agent:
            agent.last_seen = datetime.utcnow()
            agent.status = "active"
            self.db.commit()
            return True
        return False
    
    def get_agent_registry_summary(self) -> Dict[str, Any]:
        """获取Agent注册表摘要统计"""
        try:
            # 统计总数
            total_agents = self.db.query(TerminalAgent).count()
            
            # 统计活跃Agent
            active_agents = self.db.query(TerminalAgent).filter(
                TerminalAgent.status == "active"
            ).count()
            
            # 统计离线Agent
            offline_agents = self.db.query(TerminalAgent).filter(
                TerminalAgent.status != "active"
            ).count()
            
            # 统计设备类型分布
            device_type_counts = {}
            agents = self.db.query(TerminalAgent).all()
            for agent in agents:
                device_type = agent.device_type or "unknown"
                device_type_counts[device_type] = device_type_counts.get(device_type, 0) + 1
            
            # 统计能力分布
            capabilities_count = {}
            for agent in agents:
                if agent.capabilities:
                    for capability in agent.capabilities:
                        capabilities_count[capability] = capabilities_count.get(capability, 0) + 1
            
            return {
                "status": "success",
                "total_agents": total_agents,
                "active_agents": active_agents,
                "offline_agents": offline_agents,
                "device_types": device_type_counts,
                "capabilities": capabilities_count,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def delete_terminal_agent(self, agent_id: str) -> bool:
        """删除终端Agent"""
        try:
            agent = self.get_terminal_agent_by_id(agent_id)
            if agent:
                self.db.delete(agent)
                self.db.commit()
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to delete terminal agent {agent_id}: {e}")
            return False
