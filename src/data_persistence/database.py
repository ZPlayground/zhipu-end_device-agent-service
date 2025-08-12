"""
Database Connection and Session Management
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from typing import Generator
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

# 创建数据库引擎
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
)

# 为数据库初始化创建同步引擎
sync_database_url = settings.database_url.replace("sqlite+aiosqlite", "sqlite")
sync_engine = create_engine(
    sync_database_url,
    pool_pre_ping=True,
    pool_recycle=300,
)

# 创建会话工厂 - 使用同步引擎
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

# 基础模型类
Base = declarative_base()


def create_tables():
    """创建所有表"""
    try:
        # 导入所有模型以确保它们被注册到Base.metadata
        from .models import (
            User, UserSession, MessageInbox, Task, A2AAgent, 
            AgentInteraction  # TerminalAgent已重构为TerminalDevice
        )
        
        # 导入重构的终端设备模型
        from .terminal_device_models import (
            TerminalDevice, DeviceEventStream, DeviceDataEntry,
            IntentRecognitionLog, MultimodalLLMAgent
        )
        
        # 使用同步引擎创建表
        Base.metadata.create_all(bind=sync_engine)
        
        # 为重构的模型创建表
        from .terminal_device_models import Base as TerminalBase
        TerminalBase.metadata.create_all(bind=sync_engine)
        
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise


def get_db() -> Generator[Session, None, None]:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self):
        self.engine = engine
        self.SessionLocal = SessionLocal
    
    def create_session(self) -> Session:
        """创建新的数据库会话"""
        return self.SessionLocal()
    
    def health_check(self) -> bool:
        """数据库健康检查"""
        try:
            # 使用同步引擎进行健康检查
            with sync_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
