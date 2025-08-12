"""
A2A推送通知服务
使用官方a2a-python SDK的NotificationClient实现
"""
import logging
from typing import Dict, Any

from a2a.client import NotificationClient
from a2a.types import Task

logger = logging.getLogger(__name__)

class A2ANotificationService:
    """
    A2A推送通知服务
    负责在任务状态更新时，向请求方Agent主动推送通知
    """

    @staticmethod
    async def send_task_update_notification(notification_url: str, task_data: Dict[str, Any]):
        """
        发送任务更新通知

        Args:
            notification_url: 接收通知的Agent端点URL
            task_data: 更新后的任务数据字典
        """
        if not notification_url:
            logger.debug("No notification_url provided, skipping notification.")
            return

        try:
            # 验证task_data是否可以序列化为Task模型
            task = Task(**task_data)
            
            logger.info(f"🚀 Sending task update notification for task {task.id} to {notification_url}")
            
            # 使用官方SDK的NotificationClient
            notification_client = NotificationClient(notification_url)
            
            # A2A协议规定，通知是没有响应的
            # 'tasks/update' 是一个建议的方法名，具体取决于接收方的实现
            await notification_client.notify('tasks/update', {'task': task.model_dump(mode='json')})
            
            logger.info(f"✅ Successfully sent notification for task {task.id}")

        except Exception as e:
            logger.error(f"❌ Failed to send A2A notification for task {task.id} to {notification_url}: {e}")
            # 在生产环境中，这里可能需要加入重试逻辑

# 创建一个单例
a2a_notification_service = A2ANotificationService()
