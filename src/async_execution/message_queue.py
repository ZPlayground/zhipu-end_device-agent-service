"""
Message Queue Service using Redis and Celery
"""
from celery import Celery
from config.settings import settings
from src.config.agent_config import agent_config
import logging

logger = logging.getLogger(__name__)

# 创建Celery应用实例
celery_app = Celery(
    "a2a_agent_service",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.async_execution.tasks"]
)

# Celery配置 - 使用配置文件中的队列路由
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes=agent_config.get_celery_queue_routes(),
    task_default_queue=agent_config.default_queue,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
)


class MessageQueue:
    """消息队列管理器"""
    
    def __init__(self):
        self.celery = celery_app
    
    def send_task(self, task_name: str, args: list = None, kwargs: dict = None, **options):
        """发送任务到队列"""
        try:
            result = self.celery.send_task(
                task_name,
                args=args or [],
                kwargs=kwargs or {},
                **options
            )
            logger.info(f"Task {task_name} sent with ID: {result.id}")
            return result
        except Exception as e:
            logger.error(f"Failed to send task {task_name}: {e}")
            raise
    
    def get_task_result(self, task_id: str):
        """获取任务结果"""
        try:
            result = self.celery.AsyncResult(task_id)
            return {
                "id": task_id,
                "status": result.status,
                "result": result.result if result.ready() else None,
                "error": result.traceback if result.failed() else None
            }
        except Exception as e:
            logger.error(f"Failed to get task result {task_id}: {e}")
            return {
                "id": task_id,
                "status": "ERROR",
                "result": None,
                "error": str(e)
            }
    
    def revoke_task(self, task_id: str, terminate: bool = False):
        """撤销任务"""
        try:
            self.celery.control.revoke(task_id, terminate=terminate)
            logger.info(f"Task {task_id} revoked")
            return True
        except Exception as e:
            logger.error(f"Failed to revoke task {task_id}: {e}")
            return False


# 全局消息队列实例
message_queue = MessageQueue()
