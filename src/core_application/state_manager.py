"""
State Management Service
"""
from typing import Dict, Any, List, Optional
from src.data_persistence import (
    get_db, UserRepository, MessageInboxRepository, 
    TaskRepository, UserSession, MessageType
)
from datetime import datetime, timedelta
import logging
import uuid

logger = logging.getLogger(__name__)


class SessionManager:
    """会话管理器"""
    
    def __init__(self):
        self.session_timeout = timedelta(hours=24)  # 24小时会话超时
    
    def create_session(self, user_id: int) -> str:
        """创建用户会话"""
        try:
            with get_db() as db:
                session_token = str(uuid.uuid4())
                expires_at = datetime.utcnow() + self.session_timeout
                
                session = UserSession(
                    user_id=user_id,
                    session_token=session_token,
                    expires_at=expires_at
                )
                
                db.add(session)
                db.commit()
                db.refresh(session)
                
                logger.info(f"Created session for user {user_id}: {session.id}")
                return session_token
                
        except Exception as e:
            logger.error(f"Failed to create session for user {user_id}: {e}")
            raise
    
    def validate_session(self, session_token: str) -> Optional[int]:
        """验证会话并返回用户ID"""
        try:
            with get_db() as db:
                session = db.query(UserSession).filter(
                    UserSession.session_token == session_token,
                    UserSession.is_active == True,
                    UserSession.expires_at > datetime.utcnow()
                ).first()
                
                if session:
                    return session.user_id
                return None
                
        except Exception as e:
            logger.error(f"Session validation failed: {e}")
            return None
    
    def invalidate_session(self, session_token: str) -> bool:
        """使会话无效"""
        try:
            with get_db() as db:
                session = db.query(UserSession).filter(
                    UserSession.session_token == session_token
                ).first()
                
                if session:
                    session.is_active = False
                    db.commit()
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Failed to invalidate session: {e}")
            return False
    
    def cleanup_expired_sessions(self) -> int:
        """清理过期会话"""
        try:
            with get_db() as db:
                expired_count = db.query(UserSession).filter(
                    UserSession.expires_at < datetime.utcnow()
                ).update({"is_active": False})
                
                db.commit()
                logger.info(f"Cleaned up {expired_count} expired sessions")
                return expired_count
                
        except Exception as e:
            logger.error(f"Session cleanup failed: {e}")
            return 0


class SystemStateManager:
    """系统状态管理器"""
    
    def __init__(self):
        pass
    
    def get_system_health(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        try:
            # 数据库健康检查
            from src.data_persistence import DatabaseManager
            db_manager = DatabaseManager()
            db_healthy = db_manager.health_check()
            
            # Worker健康检查
            from src.async_execution import worker_manager
            worker_status = worker_manager.get_worker_status()
            
            # Redis健康检查（消息队列）
            redis_healthy = self._check_redis_health()
            
            return {
                "database": {
                    "healthy": db_healthy,
                    "status": "connected" if db_healthy else "disconnected"
                },
                "workers": {
                    "healthy": worker_status["active_count"] > 0,
                    "active_count": worker_status["active_count"],
                    "total_count": worker_status["total_workers"]
                },
                "message_queue": {
                    "healthy": redis_healthy,
                    "status": "connected" if redis_healthy else "disconnected"
                },
                "overall_status": "healthy" if all([
                    db_healthy, 
                    worker_status["active_count"] > 0, 
                    redis_healthy
                ]) else "unhealthy"
            }
            
        except Exception as e:
            logger.error(f"System health check failed: {e}")
            return {
                "overall_status": "error",
                "error": str(e)
            }
    
    def _check_redis_health(self) -> bool:
        """检查Redis健康状态"""
        try:
            import redis
            from config.settings import settings
            
            # 解析Redis URL
            r = redis.from_url(settings.redis_url)
            r.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """获取系统指标"""
        try:
            with get_db() as db:
                # 用户统计
                user_count = db.query(UserRepository.User).count()
                
                # 消息统计
                from src.data_persistence.models import MessageInbox
                total_messages = db.query(MessageInbox).count()
                unread_messages = db.query(MessageInbox).filter(
                    MessageInbox.is_read == False
                ).count()
                
                # 任务统计
                from src.data_persistence.models import Task
                total_tasks = db.query(Task).count()
                pending_tasks = db.query(Task).filter(
                    Task.status == "pending"
                ).count()
                
                return {
                    "users": {
                        "total": user_count
                    },
                    "messages": {
                        "total": total_messages,
                        "unread": unread_messages
                    },
                    "tasks": {
                        "total": total_tasks,
                        "pending": pending_tasks
                    }
                }
                
        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            return {}
