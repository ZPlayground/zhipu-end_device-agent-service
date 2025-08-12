"""
FastAPI Main Application - API & WebSocket Gateway
包含基本功能和A2A协议支持
Compliant with A2A Protocol Specification v0.2.6
"""
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# 导入配置
from config.settings import settings
from src.config.agent_config import agent_config
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any, Union
import json
import logging
import asyncio
import uuid
import os
from datetime import datetime, timedelta

# 导入各层组件
from src.data_persistence import (
    get_db, create_tables,
    UserRepository, MessageInboxRepository, TaskRepository, A2AAgentRepository
)
from src.data_persistence.models import MessageType

# 导入真正的组件
from src.external_services import LLMService
from src.external_services.zhipu_a2a_server import zhipu_a2a_server
from src.external_services.zhipu_a2a_client import zhipu_a2a_client
from config.settings import settings

# A2A SDK 导入
from a2a.types import (
    AgentCard, AgentCapabilities, AgentSkill, AgentProvider,
    Message, Task, SendMessageRequest, SendMessageResponse,
    Part, TextPart, Role, TaskState, TaskStatus
)
from a2a.client import A2AClient
A2A_SDK_AVAILABLE = True
logger = logging.getLogger(__name__)
logger.info("A2A SDK successfully imported")

# 配置日志
logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)

# 设置日志
logger = logging.getLogger(__name__)

# JSON-RPC 2.0 响应工具函数
def create_jsonrpc_response(result=None, error=None, request_id=None):
    """创建标准的JSON-RPC 2.0响应"""
    response = {"jsonrpc": "2.0", "id": request_id}
    if error:
        response["error"] = error
    else:
        response["result"] = result
    return response

def create_jsonrpc_error(code: int, message: str, data=None, request_id=None):
    """创建JSON-RPC 2.0错误响应"""
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return create_jsonrpc_response(error=error, request_id=request_id)

# 创建FastAPI应用
app = FastAPI(
    title=settings.app_name,
    description="智谱终端设备代理服务 API - 支持A2A协议",
    version=settings.app_version
)

# 添加终端Agent管理路由
# 终端设备API已重构为新的terminal_device_api

# 添加重构的终端设备API（已修复MCPCapability引用）
from src.user_interaction.terminal_device_api import router as terminal_device_router
app.include_router(terminal_device_router)

# 添加Agent发现和注册表路由
from src.user_interaction.agent_registry_api import router as agent_registry_router
app.include_router(agent_registry_router)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加OPTIONS处理器以支持CORS预检请求
@app.options("/{path:path}")
async def handle_options(path: str):
    """处理CORS预检请求"""
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )

# 安全组件
security = HTTPBearer(auto_error=False)

# A2A服务实例 - 使用新的官方SDK服务器
a2a_server = zhipu_a2a_server
a2a_client = zhipu_a2a_client

# 认证依赖（简化版本）
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """简化的用户认证"""
    if credentials:
        token = credentials.credentials
        # 这里可以验证JWT token，现在简化处理
        # 在生产环境中应该验证真实的JWT token
        if token and len(token) > 0:
            return 1
    # 如果没有认证信息，返回默认用户ID（开发环境）
    return 1

# 启动事件
@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    logger.info("Starting A2A Agent Service...")
    
    # 创建数据库表
    try:
        create_tables()
        logger.info("Database tables initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
    
    # 启动Celery Worker Manager (仅在非Docker环境中)
    try:
        import os
        # 检查是否在Docker容器中运行
        in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == 'true'
        
        if not in_docker:
            # 宿主机环境：启动内置Worker Manager
            from src.async_execution.worker_manager import worker_manager
            worker_manager.start_workers(worker_count=agent_config.default_worker_count)  # 使用配置的Worker数量
            logger.info("Celery Workers started (host environment)")
        else:
            # Docker环境：Worker由docker-compose管理
            logger.info("Running in Docker environment - Workers managed by docker-compose")
    except Exception as e:
        logger.error(f"Failed to start Celery Workers: {e}")
    
    # 启动重构的终端设备管理组件
    try:
        # 启动EventStream维护任务
        from src.core_application.event_stream_manager import event_stream_manager
        event_stream_manager.start_maintenance()
        logger.info("EventStream maintenance started")
        
        # 启动多模态LLM意图识别代理
        from src.core_application.multimodal_llm_agent import multimodal_llm_agent_manager
        await multimodal_llm_agent_manager.start_all_agents()
        logger.info("Multimodal LLM agents started")
        
    except Exception as e:
        logger.error(f"Terminal device components initialization failed: {e}")
    
    logger.info("A2A Agent Service started successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理"""
    logger.info("Shutting down A2A Agent Service...")
    
    # 停止Celery Workers
    try:
        from src.async_execution.worker_manager import worker_manager
        worker_manager.stop_workers()
        logger.info("Celery Workers stopped")
    except Exception as e:
        logger.error(f"Failed to stop Celery Workers: {e}")
    
    # 停止重构的终端设备管理组件
    try:
        from src.core_application.event_stream_manager import event_stream_manager
        event_stream_manager.stop_maintenance()
        logger.info("EventStream maintenance stopped")
        
        from src.core_application.multimodal_llm_agent import multimodal_llm_agent_manager
        await multimodal_llm_agent_manager.stop_all_agents()
        logger.info("Multimodal LLM agents stopped")
        
    except Exception as e:
        logger.error(f"Terminal device components shutdown failed: {e}")

# 基本路由
@app.get("/")
async def root():
    """根端点"""
    return {
        "message": "A2A Agent Service is running", 
        "version": settings.app_version,
        "status": "running",
        "a2a_supported": A2A_SDK_AVAILABLE,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health")
async def health_check():
    """健康检查端点"""
    try:
        # 简单的数据库连接检查
        from src.data_persistence.database import DatabaseManager
        db_manager = DatabaseManager()
        if db_manager.health_check():
            db_status = "connected"
        else:
            db_status = "disconnected"
        
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "database": db_status,
                "llm": "available",
                "a2a_sdk": "available" if A2A_SDK_AVAILABLE else "unavailable"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

# A2A Protocol 端点
if A2A_SDK_AVAILABLE and a2a_server:

    @app.get("/.well-known/agent-card.json")
    async def get_agent_card(request: Request):
        """返回此Agent的A2A Agent Card (标准A2A发现端点)"""
        # 直接使用zhipu_a2a_server的get_agent_card方法，避免重复实现
        agent_card = zhipu_a2a_server.get_agent_card()
        
        # 动态设置URL
        base_url = str(request.base_url).rstrip('/')
        agent_card["url"] = f"{base_url}/api/a2a"
        
        # 设置文档URL（如果字段存在）
        if "documentationUrl" in agent_card:
            agent_card["documentationUrl"] = f"{base_url}/docs"
        
        return agent_card
    
    # A2A 协议端点设置 - 使用 Celery Worker 异步处理
    @app.post("/api/a2a")
    async def a2a_main_endpoint(jsonrpc_request: dict):
        """A2A协议主端点 - 使用Celery Worker异步处理"""
        try:
            logger.info(f"A2A main endpoint received: {jsonrpc_request}")
            
            # 验证JSON-RPC 2.0格式
            if jsonrpc_request.get("jsonrpc") != "2.0":
                return create_jsonrpc_error(-32600, "Invalid Request", "jsonrpc field must be '2.0'", jsonrpc_request.get("id"))
            
            method = jsonrpc_request.get("method")
            params = jsonrpc_request.get("params", {})
            request_id = jsonrpc_request.get("id")
            
            # 导入Celery任务
            from src.async_execution.tasks import process_a2a_request
            
            # 处理不同的A2A方法
            if method == "message/send":
                try:
                    # 使用Celery Worker异步处理A2A请求
                    task_result = process_a2a_request.delay({
                        "method": method,
                        "params": params,
                        "request_id": request_id,
                        "jsonrpc": "2.0"
                    })
                    
                    logger.info(f"Task {task_result.id} submitted to Worker, waiting for completion...")
                    
                    # 等待Worker任务完成并获取实际结果
                    try:
                        # 使用配置的长超时时间，避免无限等待
                        actual_result = task_result.get(timeout=agent_config.task_result_timeout_long)
                        logger.info(f"Task {task_result.id} completed successfully")
                        
                        # 直接返回Worker的处理结果
                        return actual_result
                        
                    except Exception as timeout_error:
                        logger.error(f"Task timeout or error: {timeout_error}")
                        # 如果任务超时或失败，返回错误
                        return create_jsonrpc_error(-32603, "Internal error", 
                                                  f"Task processing failed: {timeout_error}", request_id)
                    
                except Exception as worker_error:
                    logger.error(f"Celery Worker error: {worker_error}")
                    # 如果Worker不可用，回退到同步处理
                    logger.warning("Falling back to synchronous processing")
                    
                    from src.external_services.zhipu_a2a_server import zhipu_a2a_server
                    request_handler = zhipu_a2a_server.request_handler
                    response = await request_handler.on_message_send(params)
                    
                    # 检查返回的是Message还是Task对象
                    if hasattr(response, 'role') and hasattr(response, 'parts'):
                        # Message对象 - 同步响应
                        return create_jsonrpc_response({
                            "message": {
                                "role": response.role.value,
                                "parts": response.parts
                            },
                            "timestamp": datetime.utcnow().isoformat()
                        }, request_id=request_id)
                    elif hasattr(response, 'id') and hasattr(response, 'status'):
                        # Task对象 - 异步响应
                        return create_jsonrpc_response(response, request_id=request_id)
                    else:
                        # 其他类型，尝试作为Message处理
                        logger.warning(f"Unknown response type from on_message_send: {type(response)}")
                        return create_jsonrpc_response({
                            "message": {
                                "role": "agent",
                                "parts": [{"type": "text", "text": str(response)}]
                            },
                            "timestamp": datetime.utcnow().isoformat()
                        }, request_id=request_id)
                
            elif method == "message/stream":
                # 流式消息也使用异步处理
                try:
                    task_result = process_a2a_request.delay({
                        "method": method,
                        "params": params,
                        "request_id": request_id,
                        "jsonrpc": "2.0"
                    })
                    
                    logger.info(f"Stream task {task_result.id} submitted to Worker, waiting for completion...")
                    
                    # 等待Worker任务完成
                    try:
                        actual_result = task_result.get(timeout=agent_config.task_result_timeout_long)
                        logger.info(f"Stream task {task_result.id} completed successfully")
                        return actual_result
                    except Exception as timeout_error:
                        logger.error(f"Stream task timeout or error: {timeout_error}")
                        return create_jsonrpc_error(-32603, "Internal error", 
                                                  f"Stream processing failed: {timeout_error}", request_id)
                    
                except Exception as worker_error:
                    logger.error(f"Celery Worker error for stream: {worker_error}")
                    # 回退到同步处理
                    from src.external_services.zhipu_a2a_server import zhipu_a2a_server
                    request_handler = zhipu_a2a_server.request_handler
                    response_message = await request_handler.on_message_send(params)
                    
                    return create_jsonrpc_response({
                        "message": {
                            "role": response_message.role.value,
                            "parts": response_message.parts
                        },
                        "streaming": True,
                        "timestamp": datetime.utcnow().isoformat()
                    }, request_id=request_id)
                
            elif method == "tasks/get":
                    # 任务查询也使用异步处理
                    try:
                        task_result = process_a2a_request.delay({
                            "method": method,
                            "params": params,
                            "request_id": request_id,
                            "jsonrpc": "2.0"
                        })
                        
                        logger.info(f"Tasks/get task {task_result.id} submitted to Worker, waiting for completion...")
                        
                        # 等待Worker任务完成
                        try:
                            actual_result = task_result.get(timeout=agent_config.task_result_timeout_short)
                            logger.info(f"Tasks/get task {task_result.id} completed successfully")
                            return actual_result
                        except Exception as timeout_error:
                            logger.error(f"Tasks/get task timeout or error: {timeout_error}")
                            return create_jsonrpc_error(-32603, "Internal error", 
                                                      f"Task query failed: {timeout_error}", request_id)
                        
                    except Exception as worker_error:
                        logger.error(f"Celery Worker error for tasks/get: {worker_error}")
                        # 回退到同步处理
                        from src.external_services.zhipu_a2a_server import zhipu_a2a_server
                        request_handler = zhipu_a2a_server.request_handler
                        task_id = params.get("id")
                        if not task_id:
                            return create_jsonrpc_error(-32602, "Invalid params", "Missing task id", request_id)
                        
                        try:
                            task_result = await request_handler.on_tasks_get(params)
                            return create_jsonrpc_response(task_result, request_id=request_id)
                        except ValueError as e:
                            return create_jsonrpc_error(-32602, "Invalid params", str(e), request_id)
                        except Exception as e:
                            logger.error(f"Error in tasks/get: {e}")
                            return create_jsonrpc_error(-32603, "Internal error", str(e), request_id)
                
            elif method == "tasks/cancel":
                    # 任务取消也使用异步处理
                    try:
                        task_result = process_a2a_request.delay({
                            "method": method,
                            "params": params,
                            "request_id": request_id,
                            "jsonrpc": "2.0"
                        })
                        
                        logger.info(f"Tasks/cancel task {task_result.id} submitted to Worker, waiting for completion...")
                        
                        # 等待Worker任务完成
                        try:
                            actual_result = task_result.get(timeout=agent_config.task_result_timeout_short)
                            logger.info(f"Tasks/cancel task {task_result.id} completed successfully")
                            return actual_result
                        except Exception as timeout_error:
                            logger.error(f"Tasks/cancel task timeout or error: {timeout_error}")
                            return create_jsonrpc_error(-32603, "Internal error", 
                                                      f"Task cancellation failed: {timeout_error}", request_id)
                        
                    except Exception as worker_error:
                        logger.error(f"Celery Worker error for tasks/cancel: {worker_error}")
                        # 回退到同步处理
                        from src.external_services.zhipu_a2a_server import zhipu_a2a_server
                        request_handler = zhipu_a2a_server.request_handler
                        task_id = params.get("id")
                        if task_id:
                            cancel_result = await request_handler.agent_executor.cancel(task_id)
                            return create_jsonrpc_response({
                                "id": task_id,
                                "status": {
                                    "state": "cancelled",
                                    "progress": 0
                                },
                                "cancelledAt": datetime.utcnow().isoformat(),
                                "kind": "task"
                            }, request_id=request_id)
                        else:
                            return create_jsonrpc_error(-32602, "Invalid params", "Missing task id", request_id)
                
            elif method in ["tasks/pushNotificationConfig/set", "tasks/pushNotificationConfig/get", 
                              "tasks/pushNotificationConfig/list", "tasks/pushNotificationConfig/delete"]:
                    # 推送通知配置方法也使用异步处理
                    try:
                        task_result = process_a2a_request.delay({
                            "method": method,
                            "params": params,
                            "request_id": request_id,
                            "jsonrpc": "2.0"
                        })
                        
                        logger.info(f"{method} task {task_result.id} submitted to Worker, waiting for completion...")
                        
                        # 等待Worker任务完成
                        try:
                            actual_result = task_result.get(timeout=agent_config.task_result_timeout_short)
                            logger.info(f"{method} task {task_result.id} completed successfully")
                            return actual_result
                        except Exception as timeout_error:
                            logger.error(f"{method} task timeout or error: {timeout_error}")
                            return create_jsonrpc_error(-32603, "Internal error", 
                                                      f"{method} processing failed: {timeout_error}", request_id)
                        
                    except Exception as worker_error:
                        logger.error(f"Celery Worker error for {method}: {worker_error}")
                        # 回退到同步处理
                        from src.external_services.zhipu_a2a_server import zhipu_a2a_server
                        request_handler = zhipu_a2a_server.request_handler
                        
                        if method == "tasks/pushNotificationConfig/set":
                            result = await request_handler.on_tasks_push_notification_config_set(params)
                            config_id = str(uuid.uuid4())
                            return create_jsonrpc_response({
                                "id": config_id,
                                "taskId": params.get("id"),
                                "pushNotificationConfig": params.get("pushNotificationConfig", {}),
                                "createdAt": datetime.utcnow().isoformat(),
                                "kind": "taskPushNotificationConfig"
                            }, request_id=request_id)
                        elif method == "tasks/pushNotificationConfig/get":
                            result = await request_handler.on_tasks_push_notification_config_get(params)
                            return create_jsonrpc_response({
                                "id": params.get("configId"),
                                "taskId": params.get("id"),
                                "pushNotificationConfig": result.get("config", {}),
                                "createdAt": datetime.utcnow().isoformat(),
                                "kind": "taskPushNotificationConfig"
                            }, request_id=request_id)
                        elif method == "tasks/pushNotificationConfig/list":
                            result = await request_handler.on_tasks_push_notification_config_list(params)
                            return create_jsonrpc_response({
                                "configs": result.get("configs", []),
                                "kind": "taskPushNotificationConfigList"
                            }, request_id=request_id)
                        elif method == "tasks/pushNotificationConfig/delete":
                            result = await request_handler.on_tasks_push_notification_config_delete(params)
                            return create_jsonrpc_response({
                                "id": params.get("configId"),
                                "taskId": params.get("id"),
                                "deletedAt": datetime.utcnow().isoformat(),
                                "kind": "taskPushNotificationConfig"
                            }, request_id=request_id)
                
            elif method == "agent/getAuthenticatedExtendedCard":
                    # Agent卡片获取使用异步处理
                    try:
                        task_result = process_a2a_request.delay({
                            "method": method,
                            "params": params,
                            "request_id": request_id,
                            "jsonrpc": "2.0"
                        })
                        
                        logger.info(f"Agent card task {task_result.id} submitted to Worker, waiting for completion...")
                        
                        # 等待Worker任务完成
                        try:
                            actual_result = task_result.get(timeout=agent_config.task_result_timeout_short)
                            logger.info(f"Agent card task {task_result.id} completed successfully")
                            return actual_result
                        except Exception as timeout_error:
                            logger.error(f"Agent card task timeout or error: {timeout_error}")
                            return create_jsonrpc_error(-32603, "Internal error", 
                                                      f"Agent card request failed: {timeout_error}", request_id)
                        
                    except Exception as worker_error:
                        logger.error(f"Celery Worker error for agent/getAuthenticatedExtendedCard: {worker_error}")
                        # 回退到同步处理
                        try:
                            from src.external_services.zhipu_a2a_server import zhipu_a2a_server
                            agent_card = zhipu_a2a_server.get_agent_card()
                            agent_card["url"] = f"{settings.a2a_base_url}/api/a2a"
                            return create_jsonrpc_response(agent_card, request_id=request_id)
                        except Exception as e:
                            return create_jsonrpc_error(-32603, "Internal error", "Agent card configuration not found", request_id)
                
            elif method == "agent/discovery":
                    # Agent发现也使用异步处理
                    try:
                        task_result = process_a2a_request.delay({
                            "method": method,
                            "params": params,
                            "request_id": request_id,
                            "jsonrpc": "2.0"
                        })
                        
                        logger.info(f"Agent discovery task {task_result.id} submitted to Worker, waiting for completion...")
                        
                        # 等待Worker任务完成
                        try:
                            actual_result = task_result.get(timeout=agent_config.task_result_timeout_short)
                            logger.info(f"Agent discovery task {task_result.id} completed successfully")
                            return actual_result
                        except Exception as timeout_error:
                            logger.error(f"Agent discovery task timeout or error: {timeout_error}")
                            return create_jsonrpc_error(-32603, "Internal error", 
                                                      f"Agent discovery failed: {timeout_error}", request_id)
                        
                    except Exception as worker_error:
                        logger.error(f"Celery Worker error for agent/discovery: {worker_error}")
                        # 回退到同步处理
                        from src.external_services.zhipu_a2a_server import zhipu_a2a_server
                        request_handler = zhipu_a2a_server.request_handler
                        discovery_result = await request_handler.handle_agent_discovery_request(params)
                        return create_jsonrpc_response(discovery_result, request_id=request_id)
                
            else:
                return create_jsonrpc_error(-32601, "Method not found", f"Unknown method: {method}", request_id)
                    
        except Exception as e:
            logger.error(f"A2A endpoint error: {e}")
            return create_jsonrpc_error(-32603, "Internal error", str(e), jsonrpc_request.get("id") if isinstance(jsonrpc_request, dict) else None)
    
    @app.post("/api/a2a/notifications")
    async def a2a_notification_endpoint(notification_data: dict = None, db: Session = Depends(get_db)):
        """A2A推送通知接收端点 - AutoGLM Agent使用标准A2A协议tasks/pushNotificationConfig/set"""
        try:
            # 处理空请求体
            if notification_data is None:
                notification_data = {}
            
            logger.info(f"Received A2A notification from AutoGLM Agent: {notification_data}")
            logger.info("AutoGLM Agent supports standard A2A protocol push notifications!")
            
            # 解析通知数据 - 支持多种格式
            task_id = (
                notification_data.get("taskId") or 
                notification_data.get("id") or
                notification_data.get("task_id")
            )
            
            status = notification_data.get("status", {})
            result = notification_data.get("result")
            context_id = notification_data.get("contextId") or notification_data.get("context_id")
            notification_type = notification_data.get("type", "task_update")
            
            # 处理不同类型的通知
            if notification_type == "test":
                logger.info("Received test notification - endpoint is working correctly")
                return {
                    "status": "received",
                    "message": "Test notification received successfully",
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            if task_id:
                # 更新任务状态到数据库
                task_repo = TaskRepository(db)
                try:
                    # 更新任务状态
                    task_repo.update_task_status(
                        task_id=task_id,
                        status=status.get("state", "updated"),
                        result=result
                    )
                    logger.info(f"Updated task {task_id} status: {status.get('state', 'updated')}")
                except Exception as db_error:
                    logger.warning(f"Failed to update task in database: {db_error}")
                
                # 如果任务完成，保存到消息收件箱
                if status.get("state") in ["completed", "finished", "done"]:
                    # 从任务记录中获取用户ID
                    try:
                        task_info = task_repo.get_task(task_id)
                        if task_info and hasattr(task_info, 'user_id'):
                            user_id = task_info.user_id
                            
                            # 保存到消息收件箱
                            message_repo = MessageInboxRepository(db)
                            try:
                                message_repo.create_message(
                                    user_id=user_id,
                                    message_type=MessageType.AGENT_MESSAGE,
                                    content=f"任务已完成: {task_id}",
                                    metadata={
                                        "task_id": task_id,
                                        "context_id": context_id,
                                        "notification_type": "task_completion",
                                        "result": result,
                                        "timestamp": datetime.utcnow().isoformat()
                                    }
                                )
                                logger.info(f"Saved task completion message to inbox for user {user_id}")
                            except Exception as msg_error:
                                logger.warning(f"Failed to save notification message: {msg_error}")
                    
                    except Exception as user_error:
                        logger.warning(f"Failed to get task user info: {user_error}")
            
            return {
                "status": "received",
                "message": "Notification processed successfully",
                "task_id": task_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"A2A notification processing error: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to process notification: {str(e)}"
            )

    # Worker管理API端点
    @app.get("/api/tasks/{task_id}/status")
    async def get_task_status(task_id: str):
        """获取Celery任务状态"""
        try:
            from src.async_execution.message_queue import celery_app
            
            task_result = celery_app.AsyncResult(task_id)
            
            if task_result.state == 'PENDING':
                response = {
                    'task_id': task_id,
                    'state': task_result.state,
                    'status': 'Task is waiting to be processed'
                }
            elif task_result.state == 'PROGRESS':
                response = {
                    'task_id': task_id,
                    'state': task_result.state,
                    'current': task_result.info.get('current', 0),
                    'total': task_result.info.get('total', 1),
                    'status': task_result.info.get('status', '')
                }
            elif task_result.state == 'SUCCESS':
                response = {
                    'task_id': task_id,
                    'state': task_result.state,
                    'result': task_result.result
                }
            else:
                # FAILURE case
                response = {
                    'task_id': task_id,
                    'state': task_result.state,
                    'error': str(task_result.info)
                }
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting task status: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get task status: {e}")

    @app.get("/api/workers/status")
    async def get_workers_status():
        """获取Worker状态"""
        try:
            from src.async_execution.worker_manager import worker_manager
            return worker_manager.get_worker_status()
        except Exception as e:
            logger.error(f"Error getting worker status: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get worker status: {e}")

    @app.post("/api/workers/restart")
    async def restart_workers(worker_count: int = None):
        """重启Workers"""
        try:
            # 使用配置的默认重启数量
            worker_count = worker_count or agent_config.worker_restart_count
            from src.async_execution.worker_manager import worker_manager
            worker_manager.restart_workers(worker_count)
            return {"message": f"Workers restarted with count: {worker_count}"}
        except Exception as e:
            logger.error(f"Error restarting workers: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to restart workers: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
