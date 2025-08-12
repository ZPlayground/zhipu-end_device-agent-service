"""
A2A Notification Receiver - Webhook Handler
"""
from typing import Dict, Any
from fastapi import HTTPException
from src.data_persistence import (
    get_db, MessageInboxRepository, TaskRepository, 
    MessageType, TaskStatus
)
from src.external_services import zhipu_a2a_client
from config.settings import settings
import logging
import hmac
import hashlib
from datetime import datetime

logger = logging.getLogger(__name__)


class A2ANotificationReceiver:
    """A2A通知接收器 - 处理来自其他Agent的回调"""
    
    def __init__(self):
        self.webhook_secret = settings.a2a_webhook_secret
    
    @staticmethod
    def _validate_a2a_request(request_data: Dict[str, Any]) -> bool:
        """验证A2A请求格式"""
        required_fields = ["correlation_id", "source_agent", "action", "payload"]
        return all(field in request_data for field in required_fields)
    
    @staticmethod
    def _create_a2a_response(correlation_id: str, status: str, result: Any = None, error: str = None) -> Dict[str, Any]:
        """创建A2A响应"""
        response = {
            "correlation_id": correlation_id,
            "status": status,
            "timestamp": str(datetime.now())
        }
        if result is not None:
            response["result"] = result
        if error is not None:
            response["error"] = error
        return response
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """验证Webhook签名"""
        if not signature.startswith("sha256="):
            return False
        
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        received_signature = signature[7:]  # 移除 "sha256=" 前缀
        
        return hmac.compare_digest(expected_signature, received_signature)
    
    async def handle_a2a_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理来自其他Agent的A2A请求"""
        try:
            # 验证请求格式
            if not self._validate_a2a_request(request_data):
                raise ValueError("Invalid A2A request format")
            
            correlation_id = request_data["correlation_id"]
            source_agent = request_data["source_agent"]
            action = request_data["action"]
            payload = request_data["payload"]
            
            logger.info(f"Received A2A request from {source_agent}: {action}")
            
            # 处理不同类型的请求
            if action == "ping":
                response = await self._handle_ping_request(payload)
            elif action == "get_capabilities":
                response = await self._handle_capabilities_request(payload)
            elif action == "execute_task":
                response = await self._handle_task_execution_request(payload, correlation_id)
            elif action == "get_status":
                response = await self._handle_status_request(payload)
            else:
                response = {
                    "status": "error",
                    "error": f"Unknown action: {action}"
                }
            
            # 记录交互
            with get_db() as db:
                from src.data_persistence.repositories import AgentInteractionRepository
                interaction_repo = AgentInteractionRepository(db)
                interaction_repo.create_interaction(
                    correlation_id=correlation_id,
                    source_agent=source_agent,
                    target_agent=settings.app_name,
                    request_data=request_data,
                    status="completed"
                )
            
            return self._create_a2a_response(
                correlation_id=correlation_id,
                status="success",
                result=response
            )
            
        except Exception as e:
            logger.error(f"A2A request handling failed: {e}")
            return self._create_a2a_response(
                correlation_id=request_data.get("correlation_id", "unknown"),
                status="error",
                error=str(e)
            )
    
    async def handle_a2a_response(self, response_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理来自其他Agent的A2A响应"""
        try:
            correlation_id = response_data["correlation_id"]
            status = response_data["status"]
            result = response_data.get("result")
            error = response_data.get("error")
            
            logger.info(f"Received A2A response for correlation_id: {correlation_id}")
            
            # 查找相关任务并更新状态
            with get_db() as db:
                task_repo = TaskRepository(db)
                
                # 通过correlation_id查找任务
                task = db.query(task_repo.Task).filter(
                    task_repo.Task.correlation_id == correlation_id
                ).first()
                
                if task:
                    if status == "success" and result:
                        task_repo.update_task_status(
                            task.id,
                            TaskStatus.COMPLETED,
                            output_data=result
                        )
                        
                        # 将结果放入用户消息收件箱
                        message_repo = MessageInboxRepository(db)
                        message_repo.create_message(
                            user_id=task.user_id,
                            message_type=MessageType.A2A_RESPONSE,
                            content=self._format_a2a_result(result),
                            metadata={
                                "task_id": task.id,
                                "correlation_id": correlation_id,
                                "source_agent": response_data.get("source_agent"),
                                "result": result
                            },
                            source_agent=response_data.get("source_agent"),
                            correlation_id=correlation_id
                        )
                    else:
                        task_repo.update_task_status(
                            task.id,
                            TaskStatus.FAILED,
                            error_message=error or "Unknown error"
                        )
                        
                        # 通知用户任务失败
                        message_repo = MessageInboxRepository(db)
                        message_repo.create_message(
                            user_id=task.user_id,
                            message_type=MessageType.NOTIFICATION,
                            content=f"任务执行失败: {error or 'Unknown error'}",
                            metadata={
                                "task_id": task.id,
                                "correlation_id": correlation_id,
                                "error": error
                            }
                        )
                
                # 更新交互记录
                from src.data_persistence.repositories import AgentInteractionRepository
                interaction_repo = AgentInteractionRepository(db)
                interaction_repo.update_interaction_response(
                    correlation_id=correlation_id,
                    response_data=response_data,
                    status="completed"
                )
            
            return {"status": "success", "message": "Response processed"}
            
        except Exception as e:
            logger.error(f"A2A response handling failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def handle_webhook_notification(
        self, 
        payload: bytes, 
        signature: str = None
    ) -> Dict[str, Any]:
        """处理Webhook通知"""
        try:
            # 验证签名（如果提供）
            if signature and not self.verify_webhook_signature(payload, signature):
                raise HTTPException(status_code=401, detail="Invalid signature")
            
            import json
            data = json.loads(payload.decode())
            
            message_type = data.get("message_type")
            
            if message_type == "request":
                return await self.handle_a2a_request(data)
            elif message_type == "response":
                return await self.handle_a2a_response(data)
            else:
                raise ValueError(f"Unknown message type: {message_type}")
                
        except Exception as e:
            logger.error(f"Webhook notification handling failed: {e}")
            raise HTTPException(status_code=400, detail=str(e))
    
    async def _handle_ping_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理ping请求"""
        return {
            "pong": True,
            "timestamp": payload.get("timestamp"),
            "agent_name": settings.app_name
        }
    
    async def _handle_capabilities_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理能力查询请求"""
        return {
            "capabilities": [
                "chat",
                "task_management", 
                "user_interaction",
                "intent_analysis"
            ],
            "agent_name": settings.app_name,
            "version": settings.app_version,
            "description": "A2A终端设备代理服务"
        }
    
    async def _handle_task_execution_request(
        self, 
        payload: Dict[str, Any], 
        correlation_id: str
    ) -> Dict[str, Any]:
        """处理任务执行请求"""
        # 这里可以根据需要实现任务执行逻辑
        # 目前只是示例实现
        task_type = payload.get("task_type")
        
        if task_type == "echo":
            return {
                "result": payload.get("data"),
                "processed_by": settings.app_name
            }
        else:
            return {
                "status": "error",
                "error": f"Unsupported task type: {task_type}"
            }
    
    async def _handle_status_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理状态查询请求"""
        return {
            "status": "running",
            "agent_name": settings.app_name,
            "version": settings.app_version,
            "uptime": "unknown",  # 可以添加真实的运行时间
            "active_connections": 0  # 可以添加真实的连接数
        }
    
    def _format_a2a_result(self, result: Dict[str, Any]) -> str:
        """格式化A2A结果为用户友好的消息"""
        if isinstance(result, dict):
            if "content" in result:
                return result["content"]
            elif "message" in result:
                return result["message"]
            else:
                return f"任务完成，结果: {result}"
        else:
            return str(result)
