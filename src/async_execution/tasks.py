"""
Background Tasks for Async Execution
"""
from celery import current_task
from .message_queue import celery_app
from src.config.agent_config import agent_config
from src.external_services import LLMService, zhipu_a2a_client
from src.data_persistence import (
    get_db, TaskRepository, MessageInboxRepository, 
    TaskStatus, MessageType
)
from typing import Dict, Any
import logging
import asyncio
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


def serialize_for_json(obj):
    """递归序列化对象为JSON兼容的格式"""
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    elif hasattr(obj, '__dict__'):
        # 自定义对象转换为字典
        return serialize_for_json(obj.__dict__)
    elif hasattr(obj, 'value'):
        # 枚举类型
        return obj.value
    elif isinstance(obj, (str, int, float, bool, type(None))):
        # 基本类型
        return obj
    else:
        # 其他类型转换为字符串
        return str(obj)


@celery_app.task(bind=True, max_retries=agent_config.celery_max_retries)
def process_a2a_request(self, request_data: Dict[str, Any]):
    """处理A2A协议请求的Celery任务 - 完整实现所有功能"""
    try:
        method = request_data.get("method")
        params = request_data.get("params", {})
        request_id = request_data.get("request_id")
        
        logger.info(f"🚀 Processing A2A request in Worker: {method} with request_id: {request_id}")
        
        # 在Celery Worker中运行异步代码
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 导入并初始化所有必要的组件
            from src.external_services.zhipu_a2a_server import zhipu_a2a_server
            from src.external_services.llm_service import LLMService
            from src.data_persistence import get_db
            from config.settings import settings
            
            # 确保request_handler正确初始化
            request_handler = zhipu_a2a_server.request_handler
            
            # 验证关键组件
            if not request_handler:
                raise Exception("request_handler not initialized")
            
            logger.info(f"✅ Worker components initialized for method: {method}")
            
            result = None
            
            if method == "message/send":
                logger.info("📨 Processing message/send request")
                
                try:
                    # 调用request_handler处理消息
                    response = loop.run_until_complete(
                        request_handler.on_message_send(params)
                    )
                    
                    logger.info(f"✅ Message send completed, response type: {type(response)}")
                    
                    # 检查返回的是Message还是Task对象
                    if hasattr(response, 'role') and hasattr(response, 'parts'):
                        # Message对象 - 提取文本内容并简化返回格式
                        text_content = ""
                        for part in response.parts:
                            if hasattr(part, 'root') and hasattr(part.root, 'text'):
                                text_content += part.root.text
                            elif hasattr(part, 'text'):
                                text_content += part.text
                            elif isinstance(part, dict) and part.get('type') == 'text':
                                text_content += part.get('text', '')
                        
                        result = {
                            "jsonrpc": "2.0",
                            "result": {
                                "message": {
                                    "role": response.role.value if hasattr(response.role, 'value') else str(response.role),
                                    "content": text_content,
                                    "parts": [{"type": "text", "text": text_content}]
                                },
                                "timestamp": datetime.utcnow().isoformat()
                            },
                            "id": request_id
                        }
                        logger.info("📤 Returning Message response")
                        
                    elif hasattr(response, 'id') and hasattr(response, 'status'):
                        # Task对象 - 异步响应，安全序列化
                        serialized_response = serialize_for_json(response)
                        result = {
                            "jsonrpc": "2.0",
                            "result": serialized_response,
                            "id": request_id
                        }
                        logger.info("📤 Returning Task response")
                        
                    elif isinstance(response, dict):
                        # 字典响应
                        result = {
                            "jsonrpc": "2.0",
                            "result": response,
                            "id": request_id
                        }
                        logger.info("📤 Returning dict response")
                        
                    else:
                        # 其他类型，尝试作为Message处理
                        logger.warning(f"⚠️ Unknown response type: {type(response)}, converting to text")
                        result = {
                            "jsonrpc": "2.0",
                            "result": {
                                "message": {
                                    "role": "agent",
                                    "content": str(response),
                                    "parts": [{"type": "text", "text": str(response)}]
                                },
                                "timestamp": datetime.utcnow().isoformat()
                            },
                            "id": request_id
                        }
                        
                except Exception as msg_error:
                    logger.error(f"❌ Message processing error: {msg_error}")
                    # 如果request_handler失败，尝试直接使用LLM服务
                    try:
                        logger.info("🔄 Falling back to direct LLM processing")
                        llm_service = LLMService()
                        
                        # 提取用户消息
                        message = params.get("message", {})
                        parts = message.get("parts", [])
                        user_text = ""
                        for part in parts:
                            if part.get("type") == "text":
                                user_text += part.get("text", "")
                        
                        if user_text:
                            llm_response = loop.run_until_complete(
                                llm_service.generate_response(user_text)
                            )
                            
                            result = {
                                "jsonrpc": "2.0",
                                "result": {
                                    "message": {
                                        "role": "agent",
                                        "parts": [{"type": "text", "text": llm_response}]
                                    },
                                    "timestamp": datetime.utcnow().isoformat()
                                },
                                "id": request_id
                            }
                            logger.info("✅ LLM fallback successful")
                        else:
                            raise Exception("No text found in message parts")
                            
                    except Exception as fallback_error:
                        logger.error(f"❌ LLM fallback also failed: {fallback_error}")
                        result = {
                            "jsonrpc": "2.0",
                            "error": {
                                "code": -32603,
                                "message": "Internal error",
                                "data": f"Message processing failed: {msg_error}, Fallback failed: {fallback_error}"
                            },
                            "id": request_id
                        }
                    
            elif method == "message/stream":
                logger.info("📨 Processing message/stream request")
                
                try:
                    response_message = loop.run_until_complete(
                        request_handler.on_message_send(params)
                    )
                    
                    result = {
                        "jsonrpc": "2.0",
                        "result": {
                            "message": {
                                "role": response_message.role.value if hasattr(response_message.role, 'value') else str(response_message.role),
                                "parts": response_message.parts
                            },
                            "streaming": True,
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        "id": request_id
                    }
                    logger.info("✅ Stream processing completed")
                    
                except Exception as stream_error:
                    logger.error(f"❌ Stream processing error: {stream_error}")
                    result = {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32603,
                            "message": "Internal error",
                            "data": f"Stream processing failed: {stream_error}"
                        },
                        "id": request_id
                    }
                
            elif method == "tasks/get":
                logger.info("📋 Processing tasks/get request")
                
                task_id = params.get("id")
                if not task_id:
                    result = {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32602,
                            "message": "Invalid params",
                            "data": "Missing task id"
                        },
                        "id": request_id
                    }
                else:
                    try:
                        task_result = loop.run_until_complete(
                            request_handler.on_tasks_get(params)
                        )
                        result = {
                            "jsonrpc": "2.0",
                            "result": task_result,
                            "id": request_id
                        }
                        logger.info(f"✅ Task {task_id} info retrieved")
                        
                    except ValueError as e:
                        logger.warning(f"⚠️ Task {task_id} not found: {e}")
                        result = {
                            "jsonrpc": "2.0",
                            "error": {
                                "code": -32602,
                                "message": "Invalid params",
                                "data": str(e)
                            },
                            "id": request_id
                        }
                    except Exception as task_error:
                        logger.error(f"❌ Task get error: {task_error}")
                        result = {
                            "jsonrpc": "2.0",
                            "error": {
                                "code": -32603,
                                "message": "Internal error",
                                "data": str(task_error)
                            },
                            "id": request_id
                        }
                        
            elif method == "tasks/cancel":
                logger.info("🚫 Processing tasks/cancel request")
                
                task_id = params.get("id")
                if task_id:
                    try:
                        cancel_result = loop.run_until_complete(
                            request_handler.agent_executor.cancel(task_id)
                        )
                        result = {
                            "jsonrpc": "2.0",
                            "result": {
                                "id": task_id,
                                "status": {
                                    "state": "cancelled",
                                    "progress": 0
                                },
                                "cancelledAt": datetime.utcnow().isoformat(),
                                "kind": "task"
                            },
                            "id": request_id
                        }
                        logger.info(f"✅ Task {task_id} cancelled")
                        
                    except Exception as cancel_error:
                        logger.error(f"❌ Task cancel error: {cancel_error}")
                        result = {
                            "jsonrpc": "2.0",
                            "error": {
                                "code": -32603,
                                "message": "Internal error",
                                "data": f"Cancel failed: {cancel_error}"
                            },
                            "id": request_id
                        }
                else:
                    result = {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32602,
                            "message": "Invalid params",
                            "data": "Missing task id"
                        },
                        "id": request_id
                    }
                    
            elif method.startswith("tasks/pushNotificationConfig/"):
                logger.info(f"🔔 Processing push notification config: {method}")
                
                try:
                    # 处理推送通知配置相关方法
                    if method == "tasks/pushNotificationConfig/set":
                        loop.run_until_complete(
                            request_handler.on_tasks_push_notification_config_set(params)
                        )
                        config_id = str(uuid.uuid4())
                        result = {
                            "jsonrpc": "2.0",
                            "result": {
                                "id": config_id,
                                "taskId": params.get("id"),
                                "pushNotificationConfig": params.get("pushNotificationConfig", {}),
                                "createdAt": datetime.utcnow().isoformat(),
                                "kind": "taskPushNotificationConfig"
                            },
                            "id": request_id
                        }
                        
                    elif method == "tasks/pushNotificationConfig/get":
                        config_result = loop.run_until_complete(
                            request_handler.on_tasks_push_notification_config_get(params)
                        )
                        result = {
                            "jsonrpc": "2.0",
                            "result": {
                                "id": params.get("configId"),
                                "taskId": params.get("id"),
                                "pushNotificationConfig": config_result.get("config", {}),
                                "createdAt": datetime.utcnow().isoformat(),
                                "kind": "taskPushNotificationConfig"
                            },
                            "id": request_id
                        }
                        
                    elif method == "tasks/pushNotificationConfig/list":
                        list_result = loop.run_until_complete(
                            request_handler.on_tasks_push_notification_config_list(params)
                        )
                        result = {
                            "jsonrpc": "2.0",
                            "result": {
                                "configs": list_result.get("configs", []),
                                "kind": "taskPushNotificationConfigList"
                            },
                            "id": request_id
                        }
                        
                    elif method == "tasks/pushNotificationConfig/delete":
                        loop.run_until_complete(
                            request_handler.on_tasks_push_notification_config_delete(params)
                        )
                        result = {
                            "jsonrpc": "2.0",
                            "result": {
                                "id": params.get("configId"),
                                "taskId": params.get("id"),
                                "deletedAt": datetime.utcnow().isoformat(),
                                "kind": "taskPushNotificationConfig"
                            },
                            "id": request_id
                        }
                        
                    logger.info(f"✅ Push notification config {method} completed")
                    
                except Exception as config_error:
                    logger.error(f"❌ Push notification config error: {config_error}")
                    result = {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32603,
                            "message": "Internal error",
                            "data": f"Config operation failed: {config_error}"
                        },
                        "id": request_id
                    }
                    
            elif method == "agent/getAuthenticatedExtendedCard":
                logger.info("🪪 Processing agent card request")
                
                try:
                    agent_card = zhipu_a2a_server.get_agent_card()
                    agent_card["url"] = f"{settings.a2a_base_url}/api/a2a"
                    result = {
                        "jsonrpc": "2.0",
                        "result": agent_card,
                        "id": request_id
                    }
                    logger.info("✅ Agent card retrieved")
                    
                except Exception as card_error:
                    logger.error(f"❌ Agent card error: {card_error}")
                    result = {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32603,
                            "message": "Internal error",
                            "data": f"Agent card not found: {card_error}"
                        },
                        "id": request_id
                    }
                
            elif method == "agent/discovery":
                logger.info("🔍 Processing agent discovery request")
                
                try:
                    discovery_result = loop.run_until_complete(
                        request_handler.handle_agent_discovery_request(params)
                    )
                    result = {
                        "jsonrpc": "2.0",
                        "result": discovery_result,
                        "id": request_id
                    }
                    logger.info("✅ Agent discovery completed")
                    
                except Exception as discovery_error:
                    logger.error(f"❌ Agent discovery error: {discovery_error}")
                    # 提供备用发现结果
                    result = {
                        "jsonrpc": "2.0",
                        "result": {
                            "agents": [],
                            "message": "Agent discovery temporarily unavailable",
                            "error": str(discovery_error)
                        },
                        "id": request_id
                    }
                
            else:
                logger.warning(f"❓ Unknown method: {method}")
                result = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32601,
                        "message": "Method not found",
                        "data": f"Unknown method: {method}"
                    },
                    "id": request_id
                }
            
            logger.info(f"🎉 A2A request {method} processed successfully in Worker")
            return result
            
        finally:
            loop.close()
            
    except Exception as exc:
        logger.error(f"💥 A2A request processing failed in Worker: {exc}")
        
        # 重试机制
        if self.request.retries < self.max_retries:
            logger.info(f"🔄 Retrying A2A request, attempt {self.request.retries + 1}")
            raise self.retry(countdown=60 * (self.request.retries + 1))
        
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32603,
                "message": "Internal error",
                "data": str(exc)
            },
            "id": request_data.get("request_id")
        }


@celery_app.task(bind=True, max_retries=agent_config.celery_max_retries)
def process_user_task(self, task_id: str, user_id: int, task_data: Dict[str, Any]):
    """处理用户任务的后台Worker"""
    try:
        # 更新任务状态
        with get_db() as db:
            task_repo = TaskRepository(db)
            task_repo.update_task_status(task_id, TaskStatus.PROCESSING)
        
        # 根据任务类型处理
        task_type = task_data.get("task_type")
        
        if task_type == "chat":
            result = _process_chat_task(task_data)
        elif task_type == "code_generation":
            result = _process_code_generation_task(task_data)
        elif task_type == "data_analysis":
            result = _process_data_analysis_task(task_data)
        elif task_type == "file_processing":
            result = _process_file_processing_task(task_data)
        else:
            result = {"error": f"Unknown task type: {task_type}"}
        
        # 更新任务结果
        with get_db() as db:
            task_repo = TaskRepository(db)
            if "error" in result:
                task_repo.update_task_status(
                    task_id, 
                    TaskStatus.FAILED, 
                    error_message=result["error"]
                )
            else:
                task_repo.update_task_status(
                    task_id, 
                    TaskStatus.COMPLETED, 
                    output_data=result
                )
            
            # 将结果放入用户消息收件箱
            message_repo = MessageInboxRepository(db)
            message_repo.create_message(
                user_id=user_id,
                message_type=MessageType.SYSTEM_RESPONSE,
                content=result.get("content", "任务已完成"),
                metadata={
                    "task_id": task_id,
                    "task_type": task_type,
                    "result": result
                }
            )
        
        return result
        
    except Exception as exc:
        logger.error(f"Task {task_id} failed: {exc}")
        
        # 更新任务状态为失败
        with get_db() as db:
            task_repo = TaskRepository(db)
            task_repo.update_task_status(
                task_id, 
                TaskStatus.FAILED, 
                error_message=str(exc)
            )
        
        # 重试机制
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying task {task_id}, attempt {self.request.retries + 1}")
            raise self.retry(countdown=60 * (self.request.retries + 1))
        
        raise exc


@celery_app.task(bind=True, max_retries=agent_config.celery_max_retries)
def send_a2a_request(self, correlation_id: str, agent_name: str, action: str, payload: Dict[str, Any]):
    """发送A2A请求的后台Worker - 使用新的官方SDK客户端"""
    try:
        # 这里需要运行异步代码
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 使用新的A2A客户端
            if action == "send_message":
                # 发送消息
                content = payload.get("content", "")
                context = payload.get("context", {})
                result = loop.run_until_complete(
                    zhipu_a2a_client.send_message(agent_name, content, context=context)
                )
            elif action == "execute_task":
                # 执行任务
                task_name = payload.get("task_name", "")
                parameters = payload.get("parameters", {})
                result = loop.run_until_complete(
                    zhipu_a2a_client.execute_task(agent_name, task_name, parameters)
                )
            elif action == "get_status":
                # 获取状态
                result = loop.run_until_complete(
                    zhipu_a2a_client.get_agent_status(agent_name)
                )
            else:
                # 通用任务执行
                result = loop.run_until_complete(
                    zhipu_a2a_client.execute_task(agent_name, action, payload)
                )
            
            # 记录交互结果
            with get_db() as db:
                from src.data_persistence.repositories import AgentInteractionRepository
                interaction_repo = AgentInteractionRepository(db)
                interaction_repo.update_interaction_response(
                    correlation_id=correlation_id,
                    response_data=result,
                    status="success" if result and result.get("success") else "failed"
                )
            
            return result
            
        finally:
            loop.close()
        
    except Exception as exc:
        logger.error(f"A2A request {correlation_id} failed: {exc}")
        
        # 记录失败
        with get_db() as db:
            from src.data_persistence.repositories import AgentInteractionRepository
            interaction_repo = AgentInteractionRepository(db)
            interaction_repo.update_interaction_response(
                correlation_id=correlation_id,
                response_data={"error": str(exc)},
                status="failed"
            )
        
        # 重试机制
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        
        raise exc


@celery_app.task
def process_a2a_response(correlation_id: str, response_data: Dict[str, Any]):
    """处理A2A响应的后台Worker"""
    try:
        # 查找相关任务并更新状态
        with get_db() as db:
            from src.data_persistence.repositories import AgentInteractionRepository
            interaction_repo = AgentInteractionRepository(db)
            interaction_repo.update_interaction_response(
                correlation_id=correlation_id,
                response_data=response_data,
                status="completed"
            )
        
        logger.info(f"A2A response processed for correlation_id: {correlation_id}")
        return {"status": "success", "correlation_id": correlation_id}
        
    except Exception as exc:
        logger.error(f"Failed to process A2A response {correlation_id}: {exc}")
        raise exc


def _process_chat_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """处理聊天任务"""
    try:
        # 这里需要运行异步代码
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            llm_service = LLMService()
            response = loop.run_until_complete(
                llm_service.generate_response(
                    prompt=task_data.get("input", ""),
                    context=task_data.get("context")
                )
            )
            
            return {
                "content": response,
                "type": "chat_response"
            }
        finally:
            loop.close()
            
    except Exception as e:
        return {"error": f"Chat processing failed: {str(e)}"}


def _process_code_generation_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """处理代码生成任务 - 需要调用代码生成Agent"""
    return {
        "content": "代码生成任务需要调用专门的A2A Agent",
        "type": "code_generation",
        "requires_agent": True,
        "agent_capability": "code_generation"
    }


def _process_data_analysis_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """处理数据分析任务 - 需要调用数据分析Agent"""
    return {
        "content": "数据分析任务需要调用专门的A2A Agent",
        "type": "data_analysis", 
        "requires_agent": True,
        "agent_capability": "data_analysis"
    }


def _process_file_processing_task(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """处理文件处理任务 - 需要调用文件处理Agent"""
    return {
        "content": "文件处理任务需要调用专门的A2A Agent",
        "type": "file_processing",
        "requires_agent": True,
        "agent_capability": "file_processing"
    }
