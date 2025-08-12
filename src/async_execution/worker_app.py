"""
Celery Worker Application Entry Point
确保所有任务都被正确导入和注册
"""
from .message_queue import celery_app

# 显式导入所有任务模块以确保它们被注册
from . import tasks

# 确保所有任务都被注册到celery_app
def register_tasks():
    """注册所有任务到Celery应用"""
    # 这个函数确保所有任务模块都被导入
    # Celery会自动发现使用@celery_app.task装饰器的函数
    pass

# 在模块加载时注册任务
register_tasks()

# 导出celery_app供worker使用
__all__ = ['celery_app']
