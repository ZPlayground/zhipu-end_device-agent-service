"""
Background Worker Manager
"""
import subprocess
import signal
import os
import logging
from typing import List, Dict, Any
from config.settings import settings
from src.config.agent_config import agent_config

logger = logging.getLogger(__name__)


class WorkerManager:
    """后台Worker管理器"""
    
    def __init__(self):
        self.worker_processes: List[subprocess.Popen] = []
        self.is_running = False
    
    def start_workers(self, worker_count: int = None, queues: List[str] = None):
        """启动Worker进程"""
        if self.is_running:
            logger.warning("Workers are already running")
            return
        
        # 使用配置文件中的默认值
        worker_count = worker_count or agent_config.default_worker_count
        queues = queues or agent_config.celery_queues
        
        try:
            for i in range(worker_count):
                worker_name = f"worker_{i+1}"
                
                # 构建Celery worker命令 - 使用worker_app模块确保任务被正确导入
                # 使用配置文件中的并发度设置
                cmd = [
                    "celery",
                    "-A", "src.async_execution.worker_app:celery_app",
                    "worker",
                    "--loglevel=info",
                    f"--hostname={worker_name}@%h",
                    f"--queues={','.join(queues)}",
                    f"--concurrency={agent_config.worker_concurrency}"  # 使用配置文件中的并发设置
                ]
                
                # 启动Worker进程
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                self.worker_processes.append(process)
                logger.info(f"Started worker {worker_name} with PID {process.pid}")
            
            self.is_running = True
            logger.info(f"Started {worker_count} workers successfully")
            
        except Exception as e:
            logger.error(f"Failed to start workers: {e}")
            self.stop_workers()
            raise
    
    def stop_workers(self):
        """停止所有Worker进程"""
        if not self.is_running:
            return
        
        for process in self.worker_processes:
            try:
                if process.poll() is None:  # 进程还在运行
                    process.terminate()
                    logger.info(f"Terminated worker with PID {process.pid}")
            except Exception as e:
                logger.error(f"Failed to terminate worker {process.pid}: {e}")
        
        # 等待进程结束
        for process in self.worker_processes:
            try:
                process.wait(timeout=agent_config.worker_termination_timeout)
            except subprocess.TimeoutExpired:
                logger.warning(f"Force killing worker {process.pid}")
                process.kill()
        
        self.worker_processes.clear()
        self.is_running = False
        logger.info("All workers stopped")
    
    def restart_workers(self, worker_count: int = None):
        """重启Worker"""
        logger.info("Restarting workers...")
        # 使用配置文件中的默认重启数量
        worker_count = worker_count or agent_config.worker_restart_count
        self.stop_workers()
        self.start_workers(worker_count)
    
    def get_worker_status(self) -> Dict[str, Any]:
        """获取Worker状态"""
        active_workers = []
        dead_workers = []
        
        for i, process in enumerate(self.worker_processes):
            worker_info = {
                "id": i + 1,
                "pid": process.pid,
                "status": "running" if process.poll() is None else "dead"
            }
            
            if worker_info["status"] == "running":
                active_workers.append(worker_info)
            else:
                dead_workers.append(worker_info)
        
        return {
            "is_running": self.is_running,
            "total_workers": len(self.worker_processes),
            "active_workers": active_workers,
            "dead_workers": dead_workers,
            "active_count": len(active_workers),
            "dead_count": len(dead_workers)
        }
    
    def health_check(self) -> bool:
        """健康检查"""
        if not self.is_running:
            return False
        
        active_count = sum(1 for p in self.worker_processes if p.poll() is None)
        return active_count > 0


# 全局Worker管理器实例
worker_manager = WorkerManager()
