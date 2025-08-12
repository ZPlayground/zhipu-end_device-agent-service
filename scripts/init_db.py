#!/usr/bin/env python3
"""
数据库初始化脚本
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 首先导入models以确保Base包含所有模型
from src.data_persistence.models import Base, User, A2AAgent
from src.data_persistence import DatabaseManager
from src.data_persistence.repositories import UserRepository, A2AAgentRepository
from src.data_persistence.database import sync_engine
from sqlalchemy.orm import sessionmaker
from config.settings import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建同步session maker
SyncSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


def create_tables():
    """创建所有表"""
    try:
        # 使用同步引擎创建表
        Base.metadata.create_all(bind=sync_engine)
        logger.info("Database tables created successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        return False


def init_database():
    """初始化数据库"""
    try:
        print("🔧 初始化数据库...")
        
        # 创建表
        if create_tables():
            print("✅ 数据库表创建成功")
        else:
            print("❌ 数据库表创建失败")
            return False
        
        # 检查数据库连接
        db_manager = DatabaseManager()
        if db_manager.health_check():
            print("✅ 数据库连接正常")
        else:
            print("❌ 数据库连接失败")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        print(f"❌ 数据库初始化失败: {e}")
        return False


def create_demo_user():
    """创建演示用户"""
    try:
        print("👤 创建演示用户...")
        
        with SyncSessionLocal() as db:
            user_repo = UserRepository(db)
            
            # 检查是否已存在
            existing_user = user_repo.get_user_by_username("demo")
            if existing_user:
                print("ℹ️  演示用户已存在")
                return True
            
            # 创建用户
            demo_password_hash = "$2b$12$DEMO.HASH.FOR.TESTING.ONLY.NOT.REAL.PASSWORD"
            user = user_repo.create_user(
                username="demo",
                email="demo@example.com",
                hashed_password=demo_password_hash  # 演示用密码哈希，非真实密码
            )
            
            db.commit()  # 提交事务
            print(f"✅ 演示用户创建成功 (ID: {user.id})")
            print("   用户名: demo")
            print("   密码: demo123")
            return True
            
    except Exception as e:
        logger.error(f"创建演示用户失败: {e}")
        print(f"❌ 创建演示用户失败: {e}")
        return False


def register_demo_agents():
    """注册演示A2A Agent"""
    try:
        print("🤖 注册演示A2A Agent...")
        
        demo_agents = [
            {
                "name": "code-generator",
                "description": "代码生成Agent",
                "endpoint_url": "http://localhost:8001",
                "capabilities": ["code_generation", "programming_help"]
            },
            {
                "name": "data-analyzer", 
                "description": "数据分析Agent",
                "endpoint_url": "http://localhost:8002",
                "capabilities": ["data_analysis", "visualization", "statistics"]
            },
            {
                "name": "file-processor",
                "description": "文件处理Agent", 
                "endpoint_url": "http://localhost:8003",
                "capabilities": ["file_processing", "format_conversion"]
            }
        ]
        
        with SyncSessionLocal() as db:
            agent_repo = A2AAgentRepository(db)
            
            created_count = 0
            for agent_data in demo_agents:
                # 检查是否已存在
                existing = agent_repo.get_agent_by_name(agent_data["name"])
                if existing:
                    print(f"ℹ️  Agent '{agent_data['name']}' 已存在")
                    continue
                
                # 创建Agent
                agent = agent_repo.create_agent(**agent_data)
                created_count += 1
                print(f"✅ 注册Agent: {agent.name}")
            
            db.commit()  # 提交事务
            print(f"✅ 共注册了 {created_count} 个演示Agent")
            return True
            
    except Exception as e:
        logger.error(f"注册演示Agent失败: {e}")
        print(f"❌ 注册演示Agent失败: {e}")
        return False


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Initialization Script")
    parser.add_argument(
        "--with-demo-data",
        action="store_true",
        help="创建演示数据（用户和Agent）"
    )
    
    args = parser.parse_args()
    
    print("🚀 A2A Agent Service - 数据库初始化")
    print(f"📊 数据库URL: {settings.database_url}")
    print("-" * 50)
    
    # 初始化数据库
    if not init_database():
        sys.exit(1)
    
    # 创建演示数据
    if args.with_demo_data:
        print("\n📝 创建演示数据...")
        
        if not create_demo_user():
            sys.exit(1)
        
        if not register_demo_agents():
            sys.exit(1)
        
        print("\n🎉 演示数据创建完成！")
        print("您可以使用以下凭据登录:")
        print("  用户名: demo")
        print("  密码: demo123")
    
    print("\n✅ 数据库初始化完成！")
    print("💡 现在可以启动服务: python scripts/start.py start")


if __name__ == "__main__":
    main()
