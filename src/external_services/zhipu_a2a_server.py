"""
基于官方a2a-python SDK的A2A服务器实现
严格按照官方SDK API实现所有功能
"""
import logging
import asyncio
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
import uuid
from fastapi import FastAPI

# 导入配置
from src.config.agent_config import agent_config
from config.settings import settings

logger = logging.getLogger(__name__)

# 导入官方A2A SDK
from a2a.server.apps.jsonrpc import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.agent_execution import AgentExecutor
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCard, AgentCapabilities, AgentSkill, AgentProvider,
    Message, Task, SendMessageRequest, SendMessageResponse,
    Part, TextPart, Role, TaskState, TaskStatus
)

# 尝试导入AgentInterface，如果不存在则创建简单版本
try:
    from a2a.types import AgentInterface
except ImportError:
    # 如果SDK没有AgentInterface，创建简单的字典版本
    logger.warning("AgentInterface not found in SDK, using dict representation")
    AgentInterface = dict
from a2a.utils.message import new_agent_text_message, get_message_text
from a2a.utils.task import new_task, completed_task

logger.info("✅ Official A2A SDK loaded successfully")

def serialize_for_json(obj):
    """递归序列化对象为JSON兼容的格式 - 复用async_execution.tasks中的逻辑"""
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

class ZhipuAgentExecutor(AgentExecutor):
    """
    智谱Agent执行器 - 增强版
    实现AgentExecutor抽象类，集成终端设备管理和任务协调
    """
    
    def __init__(self):
        # 终端设备管理已重构为新的终端设备管理器
        pass
    
    async def execute(self, task, request_context=None):
        """简化版任务执行器，支持通用任务处理"""
        try:
            # 兼容不同的调用方式
            if request_context is None and hasattr(task, 'get'):
                request_context = task
            elif request_context is None:
                request_context = {"type": "general", "parameters": {}}
                
            logger.info(f"Executing task in context: {request_context}")
            
            # 解析任务参数
            task_params = request_context.get("parameters", {})
            return await self._execute_general_task(task_params)
                
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            return {"status": "failed", "error": str(e)}

    async def _execute_general_task(self, params):
        """执行通用任务"""
        return {
            "status": "completed", 
            "result": f"General task executed with parameters: {params}",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def cancel(self, task, task_id=None):
        """取消任务"""
        # 兼容不同的调用方式
        if task_id is None:
            if hasattr(task, 'id'):
                task_id = task.id
            elif isinstance(task, str):
                task_id = task
            else:
                task_id = str(task)
                
        logger.info(f"Cancelling enhanced task: {task_id}")
        return {"status": "cancelled", "task_id": task_id, "timestamp": datetime.utcnow().isoformat()}

class ZhipuA2ARequestHandler(DefaultRequestHandler):
    """
    智谱A2A请求处理器 - 增强版
    继承官方SDK的DefaultRequestHandler，实现智能A2A协议处理
    """
    
    def __init__(self, agent_executor: AgentExecutor, task_store: InMemoryTaskStore):
        super().__init__(agent_executor, task_store)
        self.active_tasks: Dict[str, Any] = {}
        self._intent_router = None
        self._router_lock = asyncio.Lock()
        logger.info("✅ Enhanced ZhipuA2ARequestHandler initialized")
    
    async def on_message_send(self, params: dict, context=None):
        """处理消息发送请求 - 符合A2A标准的实现"""
        try:
            message = params.get("message", {})
            
            # 提取消息内容
            user_input = self._extract_message_content(message, params)
            logger.info(f"🔄 A2A handling message: {user_input}")

            # 首先获取路由结果，检查是否需要创建异步任务
            intent_router = await self._get_intent_router()
            
            if intent_router is None:
                logger.error("A2A intent router not available")
                error_message = new_agent_text_message(text=f"系统错误：意图路由器不可用。原始消息：{user_input}")
                return error_message
            
            # 执行智能路由分析
            routing_result = await intent_router.analyze_and_route_request(
                user_input=user_input,
                user_id=1,  # A2A请求的默认用户ID
                context={
                    "source": "a2a_agent", 
                    "protocol": "a2a_standard"
                }
            )
            
            # 添加详细的调试日志
            logger.info(f"🔍 路由结果详细信息:")
            logger.info(f"   📊 完整routing_result: {routing_result}")
            logger.info(f"   ✅ status: {routing_result.get('status')}")
            logger.info(f"   📝 type: {routing_result.get('type')}")
            logger.info(f"   📄 response: {routing_result.get('response', 'N/A')}")
            logger.info(f"   💬 message: {routing_result.get('message', 'N/A')}")
            logger.info(f"   🎯 agent_used: {routing_result.get('agent_used', 'N/A')}")
            logger.info(f"   🌐 agent_url: {routing_result.get('agent_url', 'N/A')}")
            
            # 处理路由结果
            if routing_result.get("status") == "success":
                logger.info(f"✅ 路由状态为success，检查类型...")
                if routing_result.get("type") == "agent_dispatch":
                    logger.info("🎯 匹配到agent_dispatch类型，进入外部Agent任务处理")
                    # 外部Agent任务 - 使用现有的完整方法
                    logger.info("🔄 检测到外部Agent任务，调用_create_async_task_for_external_agent")
                    
                    # 直接调用现有的完整异步任务创建方法
                    async_task_result = await self._create_async_task_for_external_agent(
                        user_input, routing_result, params
                    )
                    
                    # 如果返回的是Task对象，说明成功创建了异步任务
                    if hasattr(async_task_result, 'id') and hasattr(async_task_result, 'status'):
                        logger.info(f"✅ 成功创建外部Agent异步任务: {async_task_result.id}")
                        return async_task_result
                    else:
                        # 如果返回的是Message，说明降级为同步响应
                        logger.info("📝 外部Agent任务降级为同步响应")
                        return async_task_result
                    
                elif routing_result.get("type") == "agent_response":
                    logger.info("🤖 匹配到agent_response类型，这是外部Agent的响应，需要创建本地Task记录")
                    # 这是外部Agent的响应，需要创建本地Task记录
                    logger.info("🔄 检测到外部Agent响应，调用_create_async_task_for_external_agent")
                    
                    # 直接调用现有的完整异步任务创建方法
                    async_task_result = await self._create_async_task_for_external_agent(
                        user_input, routing_result, params
                    )
                    
                    # 如果返回的是Task对象，说明成功创建了异步任务
                    if hasattr(async_task_result, 'id') and hasattr(async_task_result, 'status'):
                        logger.info(f"✅ 成功创建外部Agent异步任务: {async_task_result.id}")
                        return async_task_result
                    else:
                        # 如果返回的是Message，说明降级为同步响应
                        logger.info("📝 外部Agent任务降级为同步响应")
                        return async_task_result
                        
                elif routing_result.get("type") == "local_chat":
                    logger.info("💬 匹配到local_chat类型，进入本地LLM处理")
                    # 本地LLM处理 - 返回Message
                    response_text = routing_result.get("response", "已通过本地智能处理您的请求。")
                    return new_agent_text_message(text=response_text)
                    
                elif routing_result.get("type") == "async_task":
                    logger.info("⚡ 匹配到async_task类型，进入异步任务处理")
                    # 其他异步任务
                    response_text = f"异步任务已创建：{routing_result.get('task_id', 'N/A')}。{routing_result.get('message', '')}"
                    return new_agent_text_message(text=response_text)
                    
                else:
                    logger.info(f"❓ 匹配到其他类型: {routing_result.get('type')}，进入通用处理")
                    # 其他类型
                    response_text = routing_result.get("response", routing_result.get("message", "请求已处理完成。"))
                    return new_agent_text_message(text=response_text)
            else:
                logger.error(f"❌ 路由状态不是success: {routing_result.get('status')}")
                # 路由失败，返回错误信息
                error_msg = routing_result.get('error', '未知错误')
                logger.error(f"Smart routing failed: {error_msg}")
                return new_agent_text_message(text=f"处理失败：{error_msg}")
            
        except Exception as e:
            logger.error(f"❌ A2A message handling error: {e}")
            error_message = new_agent_text_message(text=f"处理错误: {str(e)}")
            return error_message

    async def _get_agent_url_from_routing_result(self, routing_result: dict) -> str:
        """从路由结果中获取外部Agent的URL"""
        try:
            # 从意图路由器获取Agent信息
            intent_router = await self._get_intent_router()
            if not intent_router:
                logger.warning("Intent router not available to get agent URL")
                return None
            
            # 尝试通过Agent ID获取配置的Agent URL
            agent_id = routing_result.get("agent_used")
            if agent_id:
                # 从配置中获取Agent信息 - 修复导入错误
                try:
                    from src.config.agent_card_manager import load_agent_registry_config
                    agents_config = load_agent_registry_config()
                    
                    # 从agents列表中查找匹配的Agent
                    for agent in agents_config.get("agents", []):
                        if agent.get("id") == agent_id or agent.get("name") == agent_id:
                            # 从agent_card_url中提取基础URL
                            agent_card_url = agent.get("agent_card_url", "")
                            if agent_card_url:
                                # 提取基础URL（去掉/.well-known/agent-card.json部分）
                                base_url = agent_card_url.replace("/.well-known/agent-card.json", "")
                                logger.info(f"✅ Found agent URL for {agent_id}: {base_url}")
                                return base_url
                except ImportError as e:
                    logger.warning(f"Failed to import agent registry config: {e}")
            
            logger.warning(f"Could not find URL for agent: {agent_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting agent URL: {e}")
            return None

    async def _create_async_task_for_external_agent(self, user_input: str, routing_result: dict, params: dict):
        """为外部Agent创建异步任务"""
        try:
            logger.info(f"🔍 分析意图路由器响应结构: {routing_result.keys()}")
            
            # 意图路由器已经与外部Agent通信，我们需要从其响应中提取Task信息
            response_text = None
            
            # 尝试多种方式获取响应文本
            if "response" in routing_result:
                response_text = routing_result["response"]
                logger.info(f"� 从 response 字段获取响应文本")
            elif "message" in routing_result:
                response_text = routing_result["message"]
                logger.info(f"📄 从 message 字段获取响应文本")
            elif "result" in routing_result:
                response_text = str(routing_result["result"])
                logger.info(f"📄 从 result 字段转换响应文本")
            else:
                # 如果没有找到合适的字段，尝试整个 routing_result 转为字符串
                response_text = str(routing_result)
                logger.info(f"📄 使用整个routing_result作为响应文本")
            
            logger.info(f"�🔍 分析意图路由器响应文本: {response_text[:200]}...")
            
            if response_text:
                # 检查是否是Task对象响应
                if "Task(" in response_text and "context_id=" in response_text:
                    # 解析Task对象的context_id
                    import re
                    context_id_match = re.search(r"context_id='([a-f0-9-]{36})'", response_text)
                    if context_id_match:
                        external_task_id = context_id_match.group(1)
                        logger.info(f"✅ 从意图路由器响应中提取到外部Task context_id: {external_task_id}")
                        
                        # 创建本地Task记录，使用外部Task ID
                        task_id = external_task_id
                        
                        logger.info(f"🔧 开始创建本地Task记录，使用外部task_id: {task_id}")
                        
                        # 直接构造用户Message对象，使用A2A SDK的类型
                        # SDK可能没有new_user_text_message，我们使用Message构造器
                        message = Message(
                            role=Role.user,
                            parts=[Part(root=TextPart(kind="text", text=user_input))],
                            kind="message",
                            message_id=str(uuid.uuid4())
                        )
                        
                        # 使用A2A SDK创建Task对象
                        task = new_task(message)
                        
                        # 设置Task属性，使用外部Agent的ID
                        if hasattr(task, 'id'):
                            task.id = task_id
                            logger.info(f"🔄 Task ID 设置为外部ID: {task_id}")
                            
                        if hasattr(task, 'context_id'):
                            task.context_id = task_id
                            logger.info(f"🔄 Context ID 设置为外部ID: {task_id}")
                        
                        # 添加外部Agent元数据
                        if hasattr(task, 'metadata'):
                            if task.metadata is None:
                                task.metadata = {}
                            task.metadata['external_agent_url'] = routing_result.get("agent_url", "")
                            task.metadata['external_agent_id'] = routing_result.get("agent_id", "")
                            task.metadata['is_external_task'] = True
                            logger.info(f"🏷️ 添加外部Agent元数据: {task.metadata}")
                        
                        # 保存到task store
                        logger.info("💾 保存Task到task store...")
                        await self.task_store.save(task)
                        logger.info(f"✅ Task {task_id} 成功保存到task store")
                        
                        # 记录在active_tasks中
                        self.active_tasks[task_id] = {
                            "id": task_id,
                            "type": "external_agent_dispatch",
                            "status": "running",
                            "created_at": datetime.utcnow(),
                            "external_agent_url": routing_result.get("agent_url", ""),
                            "external_agent_id": routing_result.get("agent_id", ""),
                            "external_task_id": external_task_id,
                            "user_input": user_input,
                            "original_params": params,
                            "routing_result": routing_result
                        }
                        
                        logger.info(f"✅ Task {task_id} 记录在active_tasks中")
                        
                        # 异步启动外部Agent任务监控
                        asyncio.create_task(self._monitor_external_agent_task(task_id))
                        
                        logger.info(f"✅ 成功创建外部Agent异步任务: {task_id}")
                        return task
                    else:
                        logger.warning("❌ 无法从意图路由器响应中提取Task context_id")
                else:
                    logger.info("📝 意图路由器返回的是同步响应，不是Task对象")
                    
                # 如果无法创建Task，返回普通Message
                return new_agent_text_message(text=response_text)
                
            else:
                logger.warning("⚠️ 无法从意图路由器响应中提取有效文本")
                return new_agent_text_message(text="任务已分发处理，请稍后查看结果。")
            
        except Exception as e:
            logger.error(f"❌ Failed to create async task: {e}")
            import traceback
            logger.error(f"❌ 详细错误: {traceback.format_exc()}")
            # 如果创建异步任务失败，降级到同步响应
            response_text = routing_result.get("response", f"任务处理失败: {str(e)}")
            return new_agent_text_message(text=response_text)

    async def _send_request_to_external_agent(self, agent_url: str, user_input: str, params: dict) -> dict:
        """向外部A2A Agent发送请求并获取Task响应"""
        try:
            import httpx
            import uuid
            
            # 构造标准的A2A message/send请求
            request_data = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [
                            {
                                "type": "text",
                                "text": user_input
                            }
                        ],
                        "messageId": str(uuid.uuid4()),
                        "kind": "message"
                    },
                    "configuration": params.get("configuration", {})
                }
            }
            
            logger.info(f"🌐 Sending A2A request to {agent_url}")
            logger.debug(f"📤 Request data: {request_data}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    agent_url,
                    json=request_data,
                    headers={"Content-Type": "application/json"},
                    timeout=agent_config.external_agent_timeout
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"✅ Received A2A response from external agent")
                    logger.debug(f"📥 Response data: {result}")
                    
                    if "result" in result:
                        # A2A协议成功响应，返回result部分
                        return {
                            "status": "success",
                            "a2a_response": result,
                            "result": result["result"]
                        }
                    elif "error" in result:
                        # A2A协议错误响应
                        error_info = result["error"]
                        logger.error(f"❌ A2A error response: {error_info}")
                        return {
                            "status": "error",
                            "error": error_info,
                            "a2a_response": result
                        }
                    else:
                        logger.warning("⚠️ Invalid A2A response format")
                        return {
                            "status": "error",
                            "error": "Invalid A2A response format",
                            "a2a_response": result
                        }
                else:
                    logger.error(f"❌ HTTP error {response.status_code}: {response.text}")
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
                    
        except Exception as e:
            logger.error(f"❌ Failed to send request to external agent: {e}")
            raise

    def _extract_task_id_from_response(self, external_result: dict) -> str:
        """从外部A2A Agent响应中提取task_id - 优先使用Task对象的context_id字段"""
        try:
            if external_result.get("status") != "success":
                logger.warning("External agent request was not successful")
                return None
            
            # 1. 从A2A JSON-RPC响应中获取result
            result = external_result.get("result")
            if result:
                # 如果result是A2A SDK Task对象，直接访问其属性
                if hasattr(result, 'context_id') and hasattr(result, 'id'):
                    # 这是一个A2A SDK Task对象
                    logger.info("📋 External agent returned A2A SDK Task object (async response)")
                    task_id = getattr(result, 'context_id', None)
                    if task_id:
                        logger.info(f"✅ Extracted task ID from Task.context_id: {task_id}")
                        return task_id
                    else:
                        logger.warning("⚠️ Task object has no context_id attribute, checking id")
                        task_id = getattr(result, 'id', None)
                        if task_id:
                            logger.info(f"✅ Fallback to Task.id: {task_id}")
                            return task_id
                
                # 如果result是字典形式的Task对象
                elif isinstance(result, dict):
                    # 对于Task对象，优先使用context_id字段，这才是真正的任务执行ID
                    if result.get("kind") == "task":
                        # Task对象，这是异步响应 - 优先使用context_id字段
                        logger.info("📋 External agent returned Task dict (async response)")
                        task_id = result.get("context_id")  # 优先使用context_id字段
                        if task_id:
                            logger.info(f"✅ Extracted task ID from context_id pattern: {task_id}")
                            return task_id
                        else:
                            logger.warning("⚠️ Task object has no context_id field, checking id")
                            task_id = result.get("id")
                            if task_id:
                                logger.info(f"✅ Fallback to Task.id: {task_id}")
                                return task_id
                    
                    # 如果result是Message对象，可能需要检查其他字段
                    if result.get("kind") == "message":
                        # Message对象，这可能是同步响应
                        logger.info("📝 External agent returned Message (sync response)")
                        return None
                    
                    # 通用字段检查 - 优先顺序：context_id > id > taskId
                    task_id = (result.get("context_id") or 
                              result.get("id") or 
                              result.get("taskId"))
                    
                    if task_id:
                        logger.info(f"✅ Extracted task ID from A2A result: {task_id}")
                        return task_id
            
            # 2. 如果没有标准的result字段，尝试从response字符串中解析
            response_text = external_result.get("response", "")
            if response_text:
                import re
                
                # 模式1: 优先提取 id='xxx' (Task对象的主ID)
                id_match = re.search(r"id='([a-f0-9-]{36})'", response_text)
                if id_match:
                    task_id = id_match.group(1)
                    logger.info(f"✅ Extracted task ID from id pattern: {task_id}")
                    return task_id
                
                # 模式2: 如果没有id，再提取 context_id='xxx'
                context_id_match = re.search(r"context_id='([a-f0-9-]{36})'", response_text)
                if context_id_match:
                    task_id = context_id_match.group(1)
                    logger.info(f"✅ Extracted task ID from context_id pattern: {task_id}")
                    return task_id
            
            # 3. 如果result不是字典，可能是A2A SDK的对象
            if result and hasattr(result, 'id'):
                task_id = result.id
                logger.info(f"✅ Extracted task ID from object.id attribute: {task_id}")
                return task_id
            
            if result and hasattr(result, 'context_id'):
                task_id = result.context_id
                logger.info(f"✅ Extracted task ID from object.context_id attribute: {task_id}")
                return task_id
            
            logger.warning(f"Could not extract task ID from result: {type(result)} - {result}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error extracting task ID: {e}")
            return None

    async def _monitor_external_agent_task(self, task_id: str):
        """监控外部Agent任务状态"""
        try:
            task_info = self.active_tasks.get(task_id)
            if not task_info:
                return
            
            external_agent_url = task_info["external_agent_url"]
            external_agent_id = task_info["external_agent_id"]
            
            # 1. 首先检查外部Agent的Agent Card，了解其能力
            agent_card = await self._fetch_external_agent_card(external_agent_url)
            
            # 2. 根据Agent Card决定使用推送通知还是轮询
            if self._supports_push_notifications(agent_card) and task_info.get("push_notification_config"):
                await self._setup_push_notifications(task_id, task_info)
            else:
                await self._setup_polling_monitor(task_id, task_info)
                
        except Exception as e:
            logger.error(f"❌ Failed to monitor external agent task {task_id}: {e}")
            await self._mark_task_failed(task_id, str(e))

    async def _fetch_external_agent_card(self, agent_url: str) -> dict:
        """获取外部Agent的Agent Card"""
        try:
            import httpx
            
            # 根据A2A标准，Agent Card通常在配置的端点路径
            card_url = f"{agent_url.rstrip('/')}{agent_config.agent_card_endpoint}"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(card_url, timeout=agent_config.agent_card_timeout)
                if response.status_code == 200:
                    agent_card = response.json()
                    logger.info(f"✅ Fetched agent card from {card_url}")
                    return agent_card
                else:
                    logger.warning(f"Failed to fetch agent card: {response.status_code}")
                    return {}
                    
        except Exception as e:
            logger.error(f"❌ Error fetching agent card: {e}")
            return {}

    def _supports_push_notifications(self, agent_card: dict) -> bool:
        """检查Agent是否支持推送通知"""
        capabilities = agent_card.get("capabilities", {})
        return capabilities.get("pushNotifications", False) or capabilities.get("push_notifications", False)

    async def _setup_push_notifications(self, task_id: str, task_info: dict):
        """设置推送通知监控"""
        try:
            # 向外部Agent发送推送通知配置
            push_config = task_info["push_notification_config"]
            
            # 获取外部Agent的任务ID - 这是关键！
            external_task_id = task_info["external_task_id"]
            
            # 根据A2A协议发送 tasks/pushNotificationConfig/set 请求
            # 必须使用外部Agent的任务ID，不是本地任务ID
            await self._send_push_notification_config(
                task_info["external_agent_url"], 
                external_task_id,  # 使用外部Agent的任务ID
                push_config
            )
            
            logger.info(f"✅ Push notification setup for local task {task_id} -> external task {external_task_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to setup push notifications: {e}")
            # 降级到轮询模式
            await self._setup_polling_monitor(task_id, task_info)

    async def _setup_polling_monitor(self, task_id: str, task_info: dict):
        """设置轮询监控"""
        try:
            max_attempts = agent_config.polling_max_attempts  # 使用配置的最大轮询次数
            interval = agent_config.polling_interval  # 使用配置的轮询间隔
            
            # 获取外部Agent的task_id
            external_task_id = task_info.get("external_task_id", task_id)
            logger.info(f"🔄 Starting polling monitor for local task {task_id}, external task {external_task_id}")
            
            for attempt in range(max_attempts):
                await asyncio.sleep(interval)
                
                # 使用外部Agent的task_id发送 tasks/get 请求获取任务状态
                task_status = await self._get_external_task_status(
                    task_info["external_agent_url"],
                    external_task_id  # 使用外部Agent的task_id
                )
                
                if task_status.get("status") in ["completed", "failed", "cancelled"]:
                    await self._update_task_from_external_result(task_id, task_status)
                    break
                    
                logger.info(f"🔄 Polling task {task_id} (external: {external_task_id}), attempt {attempt + 1}/{max_attempts}")
            
        except Exception as e:
            logger.error(f"❌ Polling monitor failed: {e}")
            await self._mark_task_failed(task_id, str(e))
            await self._mark_task_failed(task_id, str(e))

    async def _get_external_task_status(self, agent_url: str, task_id: str) -> dict:
        """向外部Agent发送tasks/get请求"""
        try:
            import httpx
            
            request_data = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tasks/get",
                "params": {
                    "id": task_id  # 使用正确的参数名称：id，不是taskId
                }
            }
            
            # 记录查询开始时间
            import datetime
            query_start_time = datetime.datetime.now(datetime.timezone.utc)
            
            logger.info(f"🌐 向外部Agent查询任务状态: {agent_url}, task_id: {task_id}")
            logger.info(f"📤 发送的请求数据: {request_data}")
            logger.info(f"⏰ 查询开始时间: {query_start_time.isoformat()}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    agent_url,
                    json=request_data,
                    headers={"Content-Type": "application/json"},
                    timeout=agent_config.task_query_timeout
                )
                
                # 记录查询结束时间
                query_end_time = datetime.datetime.now(datetime.timezone.utc)
                query_duration = (query_end_time - query_start_time).total_seconds()
                
                logger.info(f"📥 外部Agent响应状态码: {response.status_code}")
                logger.info(f"⏰ 查询结束时间: {query_end_time.isoformat()}")
                logger.info(f"⏱️ 查询耗时: {query_duration:.3f}秒")
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"📋 外部Agent完整响应: {result}")
                    
                    task_result = result.get("result", {})
                    logger.info(f"🔍 外部Agent任务状态详情: {task_result}")
                    
                    # 详细解析任务状态信息
                    if task_result:
                        status = task_result.get("status", {})
                        state = status.get("state") if isinstance(status, dict) else task_result.get("state")
                        timestamp = status.get("timestamp") if isinstance(status, dict) else None
                        progress = task_result.get("progress")
                        result_data = task_result.get("result")
                        artifacts = task_result.get("artifacts")
                        
                        logger.info(f"📊 任务状态解析:")
                        logger.info(f"   - status: {status}")
                        logger.info(f"   - state: {state}")
                        logger.info(f"   - timestamp: {timestamp}")
                        logger.info(f"   - progress: {progress}")
                        logger.info(f"   - result: {result_data}")
                        logger.info(f"   - artifacts: {artifacts}")
                        
                        # 时间戳分析
                        if timestamp:
                            try:
                                # 解析外部Agent的时间戳
                                if isinstance(timestamp, str):
                                    task_timestamp = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                else:
                                    task_timestamp = timestamp
                                
                                # 计算时间差
                                time_diff = (query_start_time - task_timestamp).total_seconds()
                                
                                logger.info(f"⏰ 时间戳分析:")
                                logger.info(f"   - 外部Agent任务时间戳: {timestamp}")
                                logger.info(f"   - 我们的查询时间: {query_start_time.isoformat()}")
                                logger.info(f"   - 时间差: {time_diff:.3f}秒")
                                
                                if time_diff > 5:
                                    logger.warning(f"⚠️ 任务状态可能已过时！时间差超过5秒: {time_diff:.3f}秒")
                                elif time_diff < -1:
                                    logger.info(f"✨ 检测到任务状态更新！外部Agent时间戳比查询时间新 {abs(time_diff):.3f}秒")
                                    
                            except Exception as e:
                                logger.warning(f"⚠️ 时间戳解析失败: {e}")
                    
                    return task_result
                else:
                    logger.error(f"❌ 外部Agent HTTP错误: {response.status_code}, 响应内容: {response.text}")
                    return {"status": "unknown", "error": f"HTTP {response.status_code}"}
                    
        except Exception as e:
            logger.error(f"❌ Failed to get external task status: {e}")
            return {"status": "error", "error": str(e)}

    async def _update_task_from_external_result(self, task_id: str, external_result: dict):
        """根据外部Agent结果更新任务状态"""
        try:
            logger.info(f"🔄 开始更新任务状态: {task_id}")
            logger.info(f"📋 外部Agent返回的结果: {external_result}")
            
            # 更新task store中的任务
            task = await self.task_store.get(task_id)  # 使用正确的方法名
            logger.info(f"🔍 从task store获取任务: {task}")
            
            if task:
                original_status = task.status
                original_state = task.status.state if hasattr(task.status, 'state') else None  # 修复状态属性访问
                logger.info(f"📊 任务当前状态: status={original_status}, state={original_state}")
                
                # 解析外部结果的状态信息
                external_status = external_result.get("status")
                external_state = external_result.get("state")
                external_result_data = external_result.get("result")
                
                # 如果external_status是一个包含state的字典，提取真正的状态值
                if isinstance(external_status, dict) and "state" in external_status:
                    actual_external_state = external_status["state"]
                else:
                    actual_external_state = external_state
                
                logger.info(f"🌐 外部Agent状态信息:")
                logger.info(f"   - external_status: {external_status}")
                logger.info(f"   - external_state: {external_state}")
                logger.info(f"   - actual_external_state: {actual_external_state}")
                logger.info(f"   - external_result: {external_result_data}")
                
                # 详细的条件检查调试
                logger.info(f"🔍 条件检查调试:")
                logger.info(f"   - actual_external_state == 'completed': {actual_external_state == 'completed'}")
                logger.info(f"   - external_state == 'completed': {external_state == 'completed'}")
                logger.info(f"   - actual_external_state == 'failed': {actual_external_state == 'failed'}")
                logger.info(f"   - external_state == 'failed': {external_state == 'failed'}")
                logger.info(f"   - actual_external_state in ['working', 'submitted', 'input-required', 'pending']: {actual_external_state in ['working', 'submitted', 'input-required', 'pending']}")
                logger.info(f"   - actual_external_state 类型: {type(actual_external_state)}")
                logger.info(f"   - actual_external_state repr: {repr(actual_external_state)}")
                
                # 🔥 强制条件测试 - 直接测试input-required
                if actual_external_state == "input-required":
                    logger.error(f"🔥 DIRECT TEST: actual_external_state == 'input-required' 为True！")
                else:
                    logger.error(f"🔥 DIRECT TEST: actual_external_state == 'input-required' 为False！值: {repr(actual_external_state)}")
                
                # 🔥 强制条件测试 - 测试in操作
                test_list = ["working", "submitted", "input-required", "pending"]
                if actual_external_state in test_list:
                    logger.error(f"🔥 IN TEST: actual_external_state in {test_list} 为True！")
                else:
                    logger.error(f"🔥 IN TEST: actual_external_state in {test_list} 为False！值: {repr(actual_external_state)}")
                
                # 根据外部状态更新本地任务
                update_needed = False
                if actual_external_state == "completed" or external_state == "completed":
                    # 使用a2a-sdk的工具函数创建完成状态
                    try:
                        # 尝试使用SDK的completed_task工具函数来更新任务状态
                        # 但是completed_task可能需要特定的参数，我们先尝试直接更新TaskStatus
                        status_message = None
                        if isinstance(external_status, dict) and external_status.get("message"):
                            message_data = external_status.get("message")
                            try:
                                # 使用a2a-sdk的工具函数创建Message
                                if isinstance(message_data, dict) and message_data.get("kind") == "message":
                                    # 直接使用SDK的Message类型
                                    status_message = Message(**message_data)
                                else:
                                    # 使用SDK工具函数创建
                                    status_message = new_agent_text_message(text=str(message_data))
                            except Exception as e:
                                logger.warning(f"⚠️ 无法解析外部状态消息，使用备用方案: {e}")
                                status_message = new_agent_text_message(text=str(message_data))
                        
                        # 使用SDK的TaskStatus构造器
                        new_status = TaskStatus(
                            state=TaskState.completed,
                            message=status_message,
                            timestamp=external_status.get("timestamp") if isinstance(external_status, dict) else None
                        )
                        task.status = new_status
                        update_needed = True
                        logger.info(f"✅ 任务标记为已完成，包含状态消息: {status_message is not None}")
                    except Exception as e:
                        logger.error(f"❌ 无法使用SDK更新完成状态: {e}")
                        # 回退到基本的状态更新
                        task.status = TaskStatus(state=TaskState.completed, timestamp=external_status.get("timestamp") if isinstance(external_status, dict) else None)
                        update_needed = True
                    
                elif actual_external_state == "failed" or external_state == "failed":
                    # 使用a2a-sdk的工具函数创建失败状态的TaskStatus
                    status_message = None
                    if isinstance(external_status, dict) and external_status.get("message"):
                        message_data = external_status.get("message")
                        try:
                            # 使用a2a-sdk的工具函数创建Message
                            if isinstance(message_data, dict) and message_data.get("kind") == "message":
                                status_message = Message(**message_data)
                            else:
                                from a2a.utils.message import new_agent_text_message
                                status_message = new_agent_text_message(text=str(message_data))
                        except Exception as e:
                            logger.warning(f"⚠️ 无法解析外部错误消息，使用备用方案: {e}")
                            from a2a.utils.message import new_agent_text_message
                            status_message = new_agent_text_message(text=str(message_data))
                    
                    new_status = TaskStatus(
                        state=TaskState.failed,
                        message=status_message,
                        timestamp=external_status.get("timestamp") if isinstance(external_status, dict) else None
                    )
                    task.status = new_status
                    update_needed = True
                    logger.info(f"❌ 任务标记为失败，包含错误消息: {status_message is not None}")
                    
                elif actual_external_state in ["working", "submitted", "input-required", "pending"]:
                    # 更新为对应的工作状态，包含可能的状态消息
                    logger.info(f"🎯 匹配到工作状态分支: {actual_external_state}")
                    logger.info(f"🔍 详细条件检查: actual_external_state='{actual_external_state}', type={type(actual_external_state)}")
                    logger.info(f"🔍 条件列表检查: {['working', 'submitted', 'input-required', 'pending']}")
                    logger.info(f"🔍 是否在列表中: {actual_external_state in ['working', 'submitted', 'input-required', 'pending']}")
                    # 使用a2a-sdk定义的状态映射
                    state_mapping = {
                        "working": TaskState.working,
                        "submitted": TaskState.submitted,
                        "input-required": TaskState.input_required,  # 使用正确的input-required状态
                        "pending": TaskState.submitted
                    }
                    new_state = state_mapping.get(actual_external_state, TaskState.working)
                    logger.info(f"🎯 映射后的新状态: {new_state}")
                    
                    # 只有当状态真的不同时才更新
                    current_state = original_state
                    if current_state != new_state:
                        # 从外部状态中提取Message对象，使用a2a-sdk的Message构造器
                        status_message = None
                        if isinstance(external_status, dict) and external_status.get("message"):
                            message_data = external_status.get("message")
                            try:
                                # 使用a2a-sdk的工具函数创建Message
                                if isinstance(message_data, dict):
                                    # 如果是A2A标准格式的message
                                    if message_data.get("kind") == "message" and "parts" in message_data:
                                        # 直接使用SDK的Message类型
                                        status_message = Message(**message_data)
                                    else:
                                        # 转换为标准格式
                                        from a2a.utils.message import new_agent_text_message
                                        message_text = str(message_data)
                                        status_message = new_agent_text_message(text=message_text)
                                elif isinstance(message_data, str):
                                    from a2a.utils.message import new_agent_text_message
                                    status_message = new_agent_text_message(text=message_data)
                            except Exception as e:
                                logger.warning(f"⚠️ 无法解析外部状态消息，使用备用方案: {e}")
                                from a2a.utils.message import new_agent_text_message
                                status_message = new_agent_text_message(text=str(message_data))
                        
                        new_status = TaskStatus(
                            state=new_state,
                            message=status_message,
                            timestamp=external_status.get("timestamp") if isinstance(external_status, dict) else None
                        )
                        task.status = new_status
                        update_needed = True
                        logger.info(f"🔄 任务状态更新: {current_state} -> {new_state} (外部状态: {actual_external_state})，包含状态消息: {status_message is not None}")
                    else:
                        logger.info(f"ℹ️ 任务状态无变化，保持: {current_state}")
                else:
                    logger.warning(f"⚠️ 未知的外部状态: {actual_external_state}")
                    # 对于未知状态，保持当前状态但更新message
                    if isinstance(external_status, dict) and external_status.get("message"):
                        try:
                            from a2a.utils.message import new_agent_text_message
                            message_data = external_status.get("message")
                            status_message = new_agent_text_message(text=f"外部状态: {actual_external_state}, 详情: {str(message_data)}")
                            
                            new_status = TaskStatus(
                                state=original_state or TaskState.working,  # 保持原状态或默认为working
                                message=status_message,
                                timestamp=external_status.get("timestamp") if isinstance(external_status, dict) else None
                            )
                            task.status = new_status
                            update_needed = True
                            logger.info(f"🔄 更新未知状态的消息内容: {actual_external_state}")
                        except Exception as e:
                            logger.warning(f"⚠️ 无法处理未知状态的消息: {e}")
                
                if update_needed:
                    logger.info(f"💾 准备更新task store中的任务")
                    await self.task_store.save(task)  # 使用save方法而不是update_task
                    logger.info(f"✅ Task store更新成功")
                else:
                    logger.info(f"⚠️ 无需更新任务状态")
            else:
                logger.warning(f"⚠️ 在task store中未找到任务: {task_id}")
            
            # 更新本地任务记录
            if task_id in self.active_tasks:
                logger.info(f"🔄 更新active_tasks中的任务记录")
                old_status = self.active_tasks[task_id]["status"]
                
                # 使用解析后的实际状态值
                external_status = external_result.get("status")
                if isinstance(external_status, dict) and "state" in external_status:
                    new_status = external_status["state"]
                else:
                    new_status = external_result.get("state", old_status)
                
                self.active_tasks[task_id]["status"] = new_status
                self.active_tasks[task_id]["result"] = external_result.get("result")
                self.active_tasks[task_id]["completed_at"] = datetime.utcnow()
                logger.info(f"✅ Active tasks更新: {old_status} -> {new_status}")
            else:
                logger.warning(f"⚠️ 在active_tasks中未找到任务: {task_id}")
            
            logger.info(f"✅ Task {task_id} updated with external result")
            
        except Exception as e:
            logger.error(f"❌ Failed to update task from external result: {e}")
            import traceback
            logger.error(f"❌ 详细错误堆栈: {traceback.format_exc()}")

    async def _mark_task_failed(self, task_id: str, error_message: str):
        """标记任务为失败状态"""
        try:
            # 更新task store
            task = await self.task_store.get(task_id)  # 使用正确的方法名
            if task:
                # 使用a2a-sdk的工具函数创建错误消息
                error_message_obj = None
                if error_message:
                    try:
                        # 使用SDK的工具函数创建Message
                        from a2a.utils.message import new_agent_text_message
                        error_message_obj = new_agent_text_message(text=error_message)
                    except Exception as e:
                        logger.warning(f"⚠️ 无法创建错误消息对象: {e}")
                
                task.status = TaskStatus(
                    state=TaskState.failed,  # 使用正确的枚举值
                    message=error_message_obj,
                    timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
                )
                await self.task_store.save(task)  # 使用save方法而不是update_task
            
            # 更新本地记录
            if task_id in self.active_tasks:
                self.active_tasks[task_id]["status"] = "failed"
                self.active_tasks[task_id]["error"] = error_message
                self.active_tasks[task_id]["completed_at"] = datetime.utcnow()
            
            logger.info(f"❌ Task {task_id} marked as failed: {error_message}")
            
        except Exception as e:
            logger.error(f"❌ Failed to mark task as failed: {e}")

    async def _send_push_notification_config(self, agent_url: str, task_id: str, push_config: dict):
        """向外部Agent发送推送通知配置"""
        try:
            import httpx
            
            request_data = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "tasks/pushNotificationConfig/set",
                "params": {
                    "id": task_id,  # 使用正确的参数名称：id，不是taskId
                    "pushNotificationConfig": push_config
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    agent_url,
                    json=request_data,
                    headers={"Content-Type": "application/json"},
                    timeout=agent_config.push_config_timeout
                )
                
                if response.status_code == 200:
                    logger.info(f"✅ Push notification config sent to {agent_url}")
                    return True
                else:
                    logger.warning(f"Failed to send push config: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Error sending push notification config: {e}")
            return False

    def _extract_message_content(self, message: dict, params: dict) -> str:
        """提取消息内容 - 按A2A协议规范优先使用parts格式"""
        user_input = ""
        
        # 首先尝试标准的A2A格式: message.parts[]
        parts = message.get("parts", [])
        for part in parts:
            if part.get("type") == "text":
                user_input += part.get("text", "")
        
        # 如果parts为空，尝试content格式（向后兼容错误格式）
        if not user_input:
            content = message.get("content", [])
            for part in content:
                if part.get("type") == "text":
                    user_input += part.get("text", "")
        
        # 如果还是空，尝试直接从params.content获取（旧格式兼容）
        if not user_input:
            content = params.get("content", [])
            for part in content:
                if part.get("type") == "text":
                    user_input += part.get("text", "")
        
        return user_input.strip()

    async def on_tasks_get(self, params: dict, context=None):
        """处理tasks/get请求 - A2A标准方法"""
        try:
            task_id = params.get("id") or params.get("taskId") or params.get("task_id")
            
            if not task_id:
                raise ValueError("taskId is required")
            
            logger.info(f"🔍 查询任务状态: {task_id}")
            
            # 首先从task store获取任务以检查是否是外部Agent任务
            task = await self.task_store.get(task_id)  # 使用正确的方法名 get() 而不是 get_task()
            if task:
                logger.info(f"✅ 从task store找到任务 {task_id}")
                
                # 检查任务的metadata来判断是否是外部Agent任务
                is_external_task = False
                external_agent_url = None
                
                # 检查任务metadata中是否有external_agent信息
                if hasattr(task, 'metadata') and task.metadata:
                    external_agent_url = task.metadata.get('external_agent_url')
                    if external_agent_url:
                        is_external_task = True
                        logger.info(f"🌐 检测到外部Agent任务 (从metadata): {external_agent_url}")
                
                # 如果是外部Agent任务，主动查询最新状态
                if is_external_task and external_agent_url:
                    logger.info(f"🔍 主动查询外部Agent最新状态...")
                    
                    try:
                        # 主动查询外部Agent的最新状态
                        external_status = await self._get_external_task_status(
                            external_agent_url,
                            task_id  # 直接使用task_id作为外部任务ID
                        )
                        
                        # 如果获取到外部状态，更新本地任务并返回最新状态
                        if external_status and not external_status.get("error"):
                            logger.info(f"✅ 成功获取外部Agent任务状态，准备更新本地记录")
                            # 更新本地任务状态
                            await self._update_task_from_external_result(task_id, external_status)
                            
                            # 重新从task store获取更新后的任务
                            updated_task = await self.task_store.get(task_id)  # 使用正确的方法名
                            if updated_task:
                                logger.info(f"✅ 返回更新后的任务状态")
                                
                                # 使用A2A SDK对象，通过serialize_for_json处理序列化
                                task_dict = {
                                    "id": updated_task.id,
                                    "kind": updated_task.kind,
                                    "status": updated_task.status,  # 直接使用TaskStatus对象
                                    "history": getattr(updated_task, 'history', None),
                                    "result": getattr(updated_task, 'result', None),
                                    "artifacts": getattr(updated_task, 'artifacts', None),
                                    "metadata": getattr(updated_task, 'metadata', None)
                                }
                                
                                # 使用统一的序列化函数处理A2A SDK对象
                                return serialize_for_json(task_dict)
                            else:
                                # 如果task store中没有，返回external_status
                                return external_status
                        else:
                            logger.warning(f"⚠️ 外部Agent查询失败或返回错误: {external_status}")
                            
                    except Exception as e:
                        logger.warning(f"⚠️ 查询外部Agent失败: {e}")
                        # 如果外部查询失败，继续使用本地状态
                
                # 返回本地任务状态
                logger.info(f"✅ 返回本地任务状态 {task_id}")
                
                # 使用A2A SDK对象，通过serialize_for_json处理序列化
                task_dict = {
                    "id": task.id,
                    "kind": task.kind,
                    "status": task.status,  # 直接使用TaskStatus对象
                    "history": getattr(task, 'history', None),
                    "result": getattr(task, 'result', None),
                    "artifacts": getattr(task, 'artifacts', None),
                    "metadata": getattr(task, 'metadata', None)
                }
                
                # 使用统一的序列化函数处理A2A SDK对象
                return serialize_for_json(task_dict)
            
            # 检查active_tasks作为备选方案
            if task_id in self.active_tasks:
                task_info = self.active_tasks[task_id]
                logger.info(f"✅ 从active_tasks找到任务 {task_id}")
                
                # 如果是外部Agent任务，需要查询外部Agent的最新状态
                if task_info.get("type") == "external_agent_dispatch" and task_info.get("external_agent_url"):
                    logger.info(f"🌐 检测到外部Agent任务，主动查询最新状态: {task_info['external_agent_url']}")
                    
                    # 使用外部Agent的task_id进行查询
                    external_task_id = task_info.get("external_task_id", task_id)
                    logger.info(f"🔍 使用外部task_id查询: {external_task_id}")
                    
                    try:
                        # 主动查询外部Agent的最新状态
                        external_status = await self._get_external_task_status(
                            task_info["external_agent_url"],
                            external_task_id  # 使用外部Agent的task_id
                        )
                        
                        # 如果获取到外部状态，更新本地任务并返回最新状态
                        if external_status and not external_status.get("error"):
                            logger.info(f"✅ 成功获取外部Agent任务状态，准备更新本地记录")
                            # 更新本地任务状态
                            await self._update_task_from_external_result(task_id, external_status)
                            
                            # 重新从task store获取更新后的任务
                            task = await self.task_store.get(task_id)  # 使用正确的方法名
                            if task:
                                logger.info(f"✅ 返回更新后的任务状态")
                                # 使用A2A SDK对象，通过serialize_for_json处理序列化
                                task_dict = {
                                    "id": task.id,
                                    "kind": task.kind,
                                    "status": task.status,  # 直接使用TaskStatus对象
                                    "history": getattr(task, 'history', None),
                                    "result": getattr(task, 'result', None),
                                    "artifacts": getattr(task, 'artifacts', None),
                                    "metadata": getattr(task, 'metadata', None)
                                }
                                
                                # 使用统一的序列化函数处理A2A SDK对象
                                return serialize_for_json(task_dict)
                            else:
                                # 如果task store中没有，返回external_status
                                return external_status
                        else:
                            logger.warning(f"⚠️ 外部Agent查询失败或返回错误: {external_status}")
                            
                    except Exception as e:
                        logger.warning(f"⚠️ 查询外部Agent失败: {e}")
                        # 如果外部查询失败，继续使用本地状态
            
            # 如果在active_tasks中有记录但不是外部Agent任务，返回本地状态  
            if task_id in self.active_tasks:
                task_info = self.active_tasks[task_id]
                logger.info(f"✅ 从active_tasks找到任务，但task store中没有对应记录 {task_id}")
                
                # 尝试重新从task store获取，可能之前查询失败
                task = await self.task_store.get(task_id)
                if task:
                    logger.info(f"✅ 重新从task store获取到任务")
                    # 使用A2A SDK对象，通过serialize_for_json处理序列化
                    task_dict = {
                        "id": task.id,
                        "kind": task.kind,
                        "status": task.status,  # 直接使用TaskStatus对象
                        "history": getattr(task, 'history', None),
                        "result": getattr(task, 'result', None),
                        "artifacts": getattr(task, 'artifacts', None),
                        "metadata": getattr(task, 'metadata', None)
                    }
                    
                    # 使用统一的序列化函数处理A2A SDK对象
                    return serialize_for_json(task_dict)
                else:
                    # 如果task store中真的没有，构造一个基本的Task结构
                    logger.warning(f"⚠️ task store中没有任务记录，基于active_tasks构造基本Task结构")
                    
                    # 使用A2A SDK构造基本的TaskStatus
                    task_state = getattr(TaskState, task_info["status"], TaskState.working) if hasattr(TaskState, task_info["status"]) else TaskState.working
                    basic_status = TaskStatus(
                        state=task_state,
                        timestamp=task_info.get("created_at", datetime.utcnow()).isoformat() if hasattr(task_info.get("created_at", datetime.utcnow()), 'isoformat') else str(task_info.get("created_at", datetime.utcnow()))
                    )
                    
                    task_dict = {
                        "id": task_id,
                        "kind": "task",
                        "status": basic_status,  # 使用A2A SDK的TaskStatus对象
                        "history": [],
                        "result": task_info.get("result"),
                        "artifacts": None,
                        "metadata": {
                            "external_agent_id": task_info.get("external_agent_id"),
                            "type": task_info.get("type"),
                            "created_at": task_info["created_at"].isoformat() if hasattr(task_info["created_at"], 'isoformat') else str(task_info["created_at"]),
                            "completed_at": task_info.get("completed_at").isoformat() if task_info.get("completed_at") and hasattr(task_info.get("completed_at"), 'isoformat') else None
                        }
                    }
                    
                    # 使用统一的序列化函数处理A2A SDK对象
                    return serialize_for_json(task_dict)
            
            # 任务不存在
            logger.warning(f"❌ 任务 {task_id} 不存在")
            raise ValueError(f"Task {task_id} not found")
            
        except Exception as e:
            logger.error(f"❌ Error getting task {task_id}: {e}")
            raise RuntimeError(f"获取任务状态失败: {str(e)}")
    
    async def handle_task_request(self, task_request) -> Dict[str, Any]:
        """处理任务执行请求"""
        try:
            task_id = str(uuid.uuid4())
            task_type = task_request.get("type", "general")
            task_params = task_request.get("parameters", {})
            
            logger.info(f"🎯 A2A task request: {task_type} with ID: {task_id}")
            
            # 记录活跃任务
            self.active_tasks[task_id] = {
                "id": task_id,
                "type": task_type,
                "status": "running",
                "created_at": datetime.utcnow(),
                "parameters": task_params
            }
            
            # 执行任务
            execution_result = await self.agent_executor.execute({
                "type": task_type,
                "parameters": task_params,
                "task_id": task_id
            })
            
            # 更新任务状态
            if task_id in self.active_tasks:
                self.active_tasks[task_id]["status"] = execution_result.get("status", "completed")
                self.active_tasks[task_id]["result"] = execution_result.get("result")
                self.active_tasks[task_id]["completed_at"] = datetime.utcnow()
            
            return {
                "task_id": task_id,
                "status": execution_result.get("status", "completed"),
                "result": execution_result.get("result"),
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ A2A task execution error: {e}")
            return {
                "task_id": task_id if 'task_id' in locals() else "unknown",
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def handle_agent_discovery_request(self, discovery_params: Dict[str, Any]) -> Dict[str, Any]:
        """处理Agent发现请求 - 简化版本直接返回终端设备信息"""
        try:
            logger.info(f"🔍 A2A agent discovery request: {discovery_params}")
            
            # 直接使用终端设备管理器获取设备信息
            try:
                from src.core_application.terminal_device_manager import TerminalDeviceManager
                from src.data_persistence.database import SessionLocal
                
                db = SessionLocal()
                device_manager = TerminalDeviceManager(db)
                
                device_type = discovery_params.get("device_type")
                devices = device_manager.get_devices(device_type=device_type, status="active")
                
                discovered_agents = [
                    {
                        "device_id": device.device_id,
                        "name": device.name,
                        "device_type": device.device_type,
                        "capabilities": device.mcp_capabilities,
                        "mcp_server_url": device.mcp_server_url,
                        "last_seen": device.last_seen.isoformat() if device.last_seen else None
                    }
                    for device in devices
                ]
                
                db.close()
                
                return {
                    "status": "success",
                    "discovered_agents": discovered_agents,
                    "count": len(discovered_agents),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            except Exception as device_error:
                logger.warning(f"Failed to get device information: {device_error}")
                return {
                    "status": "success",
                    "discovered_agents": [],
                    "count": 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"❌ A2A agent discovery error: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def get_active_tasks_status(self) -> Dict[str, Any]:
        """获取活跃任务状态"""
        return {
            "active_tasks_count": len(self.active_tasks),
            "tasks": [
                {
                    "id": task["id"],
                    "type": task["type"],
                    "status": task["status"],
                    "created_at": task["created_at"].isoformat(),
                    "completed_at": task.get("completed_at", {}).isoformat() if task.get("completed_at") else None
                }
                for task in self.active_tasks.values()
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def _get_intent_router(self):
        """线程安全获取意图路由器实例"""
        if self._intent_router is None:
            async with self._router_lock:
                # 双重检查锁定模式
                if self._intent_router is None:
                    try:
                        from src.core_application.a2a_intent_router import A2AIntentRouter
                        self._intent_router = A2AIntentRouter()
                        logger.info("✅ A2A Intent Router initialized successfully")
                    except ImportError as ie:
                        logger.warning(f"Unable to import A2A intent router: {ie}")
                        self._intent_router = False  # 标记为不可用
                    except Exception as e:
                        logger.error(f"Failed to initialize A2A intent router: {e}")
                        self._intent_router = False  # 标记为不可用
        
        return self._intent_router if self._intent_router is not False else None
    
    async def _process_message(self, user_input: str, notification_url: Optional[str] = None) -> str:
        """处理用户消息 - 统一的智能A2A路由处理"""
        try:
            # 线程安全获取路由器实例
            intent_router = await self._get_intent_router()
            
            if intent_router is None:
                logger.error("A2A intent router not available")
                return f"系统错误：意图路由器不可用。原始消息：{user_input}"
            
            # 执行智能路由分析
            routing_result = await intent_router.analyze_and_route_request(
                user_input=user_input,
                user_id=1,  # A2A请求的默认用户ID
                context={
                    "source": "a2a_agent", 
                    "protocol": "a2a_standard",
                    "notification_url": notification_url  # 传递通知URL
                }
            )
            
            # 处理路由结果
            if routing_result.get("status") == "success":
                if routing_result.get("type") == "agent_dispatch":
                    # 任务已分发给其他Agent
                    return routing_result.get("message", "任务已分发处理，请稍后查看结果。")
                elif routing_result.get("type") == "local_chat":
                    # 本地LLM处理
                    return routing_result.get("response", "已通过本地智能处理您的请求。")
                elif routing_result.get("type") == "async_task":
                    # 异步任务
                    return f"异步任务已创建：{routing_result.get('task_id', 'N/A')}。{routing_result.get('message', '')}"
                else:
                    return routing_result.get("response", routing_result.get("message", "请求已处理完成。"))
            else:
                # 路由失败，返回错误信息
                error_msg = routing_result.get('error', '未知错误')
                logger.error(f"Smart routing failed: {error_msg}")
                return f"处理失败：{error_msg}"
                
        except Exception as e:
            logger.error(f"Message processing failed: {e}")
            return f"系统错误：{str(e)}"
    
    # A2A协议推送通知配置方法
    async def on_tasks_push_notification_config_set(self, params: Any, context=None):
        """设置推送通知配置 - A2A协议标准格式"""
        try:
            # 根据A2A协议，params应该是TaskPushNotificationConfig格式
            task_id = params.get("taskId")
            push_config = params.get("pushNotificationConfig", {})
            
            logger.info(f"🔔 Setting push notification config for task {task_id}: {push_config}")
            
            # 这里可以保存配置到数据库或内存
            # 目前返回符合A2A协议的响应
            return {
                "taskId": task_id,
                "pushNotificationConfig": push_config
            }
        except Exception as e:
            logger.error(f"❌ Error setting push notification config: {e}")
            raise RuntimeError(f"设置推送通知配置失败: {str(e)}")
    
    async def on_tasks_push_notification_config_get(self, params: Any, context=None):
        """获取推送通知配置"""
        try:
            logger.info("📋 Getting push notification config")
            
            # 返回默认配置（实际应该从存储中获取）
            default_config = {
                "enabled": True,
                "notification_types": ["task_completed", "task_failed", "task_progress"],
                "delivery_methods": ["webhook", "websocket"],
                "retry_attempts": 3,
                "timeout_seconds": 30
            }
            
            return {
                "status": "success",
                "config": default_config
            }
        except Exception as e:
            logger.error(f"❌ Error getting push notification config: {e}")
            raise RuntimeError(f"获取推送通知配置失败: {str(e)}")
    
    async def on_tasks_push_notification_config_delete(self, params: Any, context=None):
        """删除推送通知配置"""
        try:
            logger.info("🗑️ Deleting push notification config")
            
            # 这里应该从存储中删除配置
            return {
                "status": "success",
                "message": "推送通知配置已删除"
            }
        except Exception as e:
            logger.error(f"❌ Error deleting push notification config: {e}")
            raise RuntimeError(f"删除推送通知配置失败: {str(e)}")
    
    async def on_tasks_push_notification_config_list(self, params: Any, context=None):
        """列出所有推送通知配置"""
        try:
            logger.info("📝 Listing push notification configs")
            
            # 返回配置列表（实际应该从存储中获取）
            configs = [
                {
                    "id": "default",
                    "name": "默认推送配置",
                    "enabled": True,
                    "created_at": datetime.utcnow().isoformat()
                }
            ]
            
            return {
                "status": "success",
                "configs": configs,
                "total": len(configs)
            }
        except Exception as e:
            logger.error(f"❌ Error listing push notification configs: {e}")
            raise RuntimeError(f"列出推送通知配置失败: {str(e)}")

class ZhipuA2AServer:
    """
    智谱A2A服务器
    严格按照官方a2a-python SDK API构建的标准A2A协议服务器
    """
    
    def __init__(self):
        self.active_tasks: Dict[str, Any] = {}
        
        # 使用统一的Agent Card管理器
        from src.config.agent_card_manager import load_a2a_agent_card
        self.agent_card = load_a2a_agent_card()
        
        # 创建所需的依赖组件
        self.agent_executor = ZhipuAgentExecutor()
        self.task_store = InMemoryTaskStore()
        
        # 创建官方SDK请求处理器
        self.request_handler = ZhipuA2ARequestHandler(
            agent_executor=self.agent_executor,
            task_store=self.task_store
        )
        
        # 创建官方SDK FastAPI应用
        self.a2a_app = A2AFastAPIApplication(
            agent_card=self.agent_card,
            http_handler=self.request_handler
        )
        
        logger.info("✅ ZhipuA2AServer initialized with official SDK")
    
    def reload_agent_card(self):
        """重新加载Agent Card配置"""
        from src.config.agent_card_manager import load_a2a_agent_card
        self.agent_card = load_a2a_agent_card(force_reload=True)
        
        # 重新创建A2A应用
        self.a2a_app = A2AFastAPIApplication(
            agent_card=self.agent_card,
            http_handler=self.request_handler
        )
        
        logger.info("✅ Agent Card reloaded successfully")
    
    def get_fastapi_app(self) -> FastAPI:
        """获取FastAPI应用实例"""
        return self.a2a_app.build(
            agent_card_url="/.well-known/agent-card.json",
            rpc_url="/",
            extended_agent_card_url="/agent/authenticatedExtendedCard"
        )
    
    def get_agent_card(self) -> Dict[str, Any]:
        """获取Agent Card"""
        return self.agent_card.model_dump(mode='json')
    
    def get_status(self) -> Dict[str, Any]:
        """获取增强版服务状态"""
        try:
            # 获取终端设备统计 - 使用重构后的设备管理器
            terminal_device_summary = {}
            try:
                from src.data_persistence.database import SessionLocal
                from src.core_application.terminal_device_manager import TerminalDeviceManager
                db = SessionLocal()
                device_manager = TerminalDeviceManager(db)
                terminal_device_summary = device_manager.get_device_summary()
                db.close()
            except ImportError as e:
                logger.warning(f"Failed to import terminal device components: {e}")
                terminal_device_summary = {"status": "device_manager_unavailable", "reason": "import_error"}
            except Exception as e:
                logger.warning(f"Failed to get terminal device summary: {e}")
                terminal_device_summary = {"status": "error", "reason": str(e)}
            
            # 获取任务统计
            active_tasks_status = self.request_handler.get_active_tasks_status()
            
            # 从Agent Card获取基础信息，避免硬编码
            agent_card_info = {
                "agent_name": self.agent_card.name,
                "agent_description": self.agent_card.description,
                "protocol_version": self.agent_card.protocol_version,
                "agent_version": self.agent_card.version,
                "agent_url": self.agent_card.url,
                "preferred_transport": self.agent_card.preferred_transport
            }
            
            # 构建技能列表，包含详细的技能信息
            skills_summary = [
                {
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description[:100] + "..." if len(skill.description) > 100 else skill.description,
                    "tags": skill.tags,
                    "examples_count": len(skill.examples) if hasattr(skill, 'examples') and skill.examples else 0
                }
                for skill in self.agent_card.skills
            ]
            
            # 从技能中提取功能特性，避免硬编码
            features = []
            for skill in self.agent_card.skills:
                if "intent" in skill.id.lower() or "nlp" in skill.tags:
                    features.append("LLM-powered intent recognition")
                if "task" in skill.id.lower() or "async" in skill.tags:
                    features.append("Async task management")
                if "routing" in skill.tags:
                    features.append("Dynamic agent discovery")
            
            # 添加基于配置的特性
            if self.agent_card.capabilities.streaming:
                features.append("Real-time streaming")
            if self.agent_card.capabilities.push_notifications:
                features.append("Push notifications")
            
            # 去重并添加默认的A2A协议特性
            features = list(set(features))
            features.extend([
                "Multi-agent task orchestration",
                "Terminal device lifecycle management", 
                "Smart capability matching",
                "A2A protocol compliance"
            ])
            
            return {
                "service": f"{self.agent_card.name} - Enhanced Server",
                "version": self.agent_card.version,
                "sdk_available": True,
                "agent_card": agent_card_info,
                "capabilities": {
                    # 从Agent Card获取的A2A标准能力
                    "streaming": self.agent_card.capabilities.streaming,
                    "push_notifications": self.agent_card.capabilities.push_notifications,
                    "state_transition_history": self.agent_card.capabilities.state_transition_history,
                    # 扩展的服务器能力
                    "intelligent_routing": True,
                    "terminal_agent_management": True,
                    "multi_agent_orchestration": True,
                    "smart_discovery": True,
                    "a2a_protocol_gateway": True
                },
                "active_tasks": len(self.active_tasks),
                "request_handler_tasks": active_tasks_status.get("active_tasks_count", 0),
                "terminal_devices": terminal_device_summary,
                "skills": skills_summary,
                "skills_count": len(self.agent_card.skills),
                "features": features,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to get enhanced status: {e}")
            return {
                "service": "ZhipuA2AServer Enhanced",
                "version": "2.0.0",  # 默认版本
                "status": "error",
                "error": str(e),
                "sdk_available": True,
                "agent_card": {
                    "agent_name": "Unknown",
                    "protocol_version": "Unknown"
                },
                "capabilities": {},
                "active_tasks": 0,
                "timestamp": datetime.utcnow().isoformat()
            }

# 创建全局A2A服务器实例
zhipu_a2a_server = ZhipuA2AServer()
