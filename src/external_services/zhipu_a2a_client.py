"""
基于官方a2a-python SDK的A2A客户端
替代原有的手写A2A客户端实现
"""
import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import httpx

"""
基于官方a2a-python SDK的A2A客户端
严格按照官方SDK API实现所有功能
"""
import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)

# 导入官方A2A SDK 0.3.0
from a2a.client import A2AClient, A2ACardResolver
from a2a.client.helpers import create_text_message_object
from a2a.types import (
    AgentCard, Message, Task, SendMessageRequest, SendMessageResponse,
    Part, TextPart, Role, TaskState, TaskStatus
)
from a2a.utils import new_agent_text_message, get_message_text, new_task

logger.info("✅ Official A2A SDK client loaded successfully")

class ZhipuA2AClient:
    """
    智谱A2A客户端
    严格按照官方a2a-python SDK与其他A2A Agent通信
    """
    
    def __init__(self):
        self._agent_cache: Dict[str, AgentCard] = {}
        self._client_cache: Dict[str, A2AClient] = {}
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """获取HTTP客户端实例"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client
    
    async def discover_agent(self, agent_url: str, force_refresh: bool = False):
        """
        发现并获取Agent的Agent Card
        使用官方SDK 0.3.0的A2ACardResolver
        
        Args:
            agent_url: Agent的根URL
            force_refresh: 是否强制刷新缓存
            
        Returns:
            AgentCard对象，如果发现失败则返回None
        """
        # 检查缓存
        if not force_refresh and agent_url in self._agent_cache:
            logger.info(f"Using cached agent card for {agent_url}")
            return self._agent_cache[agent_url]
        
        try:
            logger.info(f"🔍 Discovering agent at {agent_url}")
            
            # 处理不同的URL格式
            if agent_url.endswith('/.well-known/agent-card.json'):
                # 如果已经是完整的agent card URL，提取base_url
                base_url = agent_url.replace('/.well-known/agent-card.json', '')
                logger.info(f"📍 Detected complete agent-card URL, base_url: {base_url}")
            elif agent_url.endswith('/.well-known/agent.json'):
                # 如果是旧格式，替换为新格式
                base_url = agent_url.replace('/.well-known/agent.json', '')
                logger.warning(f"⚠️ Detected old agent.json format, converted base_url: {base_url}")
            else:
                # 如果是base URL，直接使用
                base_url = agent_url.rstrip('/')
                logger.info(f"📍 Using base URL: {base_url}")
            
            logger.info(f"🚀 Calling A2ACardResolver with base_url: {base_url}")
            
            # 使用官方SDK 0.3.0的A2ACardResolver
            http_client = await self._get_http_client()
            card_resolver = A2ACardResolver(
                base_url=base_url,
                httpx_client=http_client
            )
            
            # 获取Agent Card - 使用正确的agent-card.json路径
            logger.info(f"📡 Attempting to get agent card...")
            agent_card = await card_resolver.get_agent_card(
                relative_card_path="/.well-known/agent-card.json"
            )
            
            if agent_card:
                self._agent_cache[agent_url] = agent_card
                logger.info(f"✅ Successfully discovered agent: {agent_card.name}")
                logger.debug(f"🔧 Agent details: url={agent_card.url}, version={agent_card.version}")
                return agent_card
            else:
                logger.warning(f"❌ No agent found at {agent_url}")
                return None
                
        except Exception as e:
            # 提供更详细的错误信息
            logger.error(f"💥 Failed to discover agent at {agent_url}: {type(e).__name__}: {e}")
            if hasattr(e, 'response'):
                logger.error(f"🌐 HTTP Response status: {getattr(e.response, 'status_code', 'Unknown')}")
                logger.error(f"🔗 Attempted URL: {getattr(e.response, 'url', 'Unknown')}")
            return None
            if "502" in str(e) or "Bad Gateway" in str(e) or "Connection refused" in str(e):
                logger.debug(f"Agent at {agent_url} is not available: {e}")
            else:
                logger.error(f"Failed to discover agent at {agent_url}: {e}")
            return None
    
    async def discover_agents(self, agent_urls: Optional[List[str]] = None) -> List[AgentCard]:
        """
        发现多个Agent
        
        Args:
            agent_urls: Agent URL列表，如果为None则返回缓存的agents
            
        Returns:
            AgentCard对象列表
        """
        agents = []
        
        if agent_urls is None:
            # 返回缓存的agents
            return list(self._agent_cache.values())
        
        for url in agent_urls:
            try:
                agent_card = await self.discover_agent(url)
                if agent_card:
                    agents.append(agent_card)
            except Exception as e:
                logger.error(f"Failed to discover agent at {url}: {e}")
                continue
        
        return agents
    
    async def get_client(self, agent_url: str):
        """
        获取指定Agent的客户端实例
        使用官方SDK的A2AClient
        
        Args:
            agent_url: Agent的根URL
            
        Returns:
            A2AClient实例，如果创建失败则返回None
        """
        # 检查缓存
        if agent_url in self._client_cache:
            return self._client_cache[agent_url]
        
        try:
            # 先发现Agent
            agent_card = await self.discover_agent(agent_url)
            if not agent_card:
                return None
            
            # 获取HTTP客户端
            http_client = await self._get_http_client()
            
            # 创建官方SDK客户端
            client = A2AClient(
                httpx_client=http_client,
                agent_card=agent_card
            )
            
            self._client_cache[agent_url] = client
            logger.info(f"Created A2A client for {agent_card.name}")
            return client
            
        except Exception as e:
            logger.error(f"Failed to create client for {agent_url}: {e}")
            return None
    
    async def send_message(
        self, 
        agent_url: str, 
        content: str,
        message_type: str = "text",
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        向指定Agent发送消息
        使用官方SDK的消息发送功能，完全符合A2A协议规范
        
        Args:
            agent_url: 目标Agent的URL
            content: 消息内容
            message_type: 消息类型
            context: 额外的上下文信息
            
        Returns:
            发送结果，包含响应信息和A2A合规的错误处理
        """
        try:
            client = await self.get_client(agent_url)
            if not client:
                return {
                    "status": "error", 
                    "error": "Failed to create client for agent",
                    "error_code": "CLIENT_CREATION_FAILED"
                }
            
            # 使用官方SDK的helper函数创建消息
            message = create_text_message_object(Role.user, content)
            
            # 创建正确的SendMessageRequest对象（A2AClient.send_message的真正参数类型）
            from a2a.types import SendMessageRequest
            from uuid import uuid4
            
            request = SendMessageRequest(
                id=str(uuid4()),
                jsonrpc="2.0",
                method="message/send",
                params={
                    "message": message.model_dump(),
                    "metadata": context if context else None
                }
            )
            
            # 发送消息
            logger.info(f"Sending A2A-compliant message to {agent_url}: {content[:50]}...")
            response = await client.send_message(request)
            
            if response and response.root:
                # SendMessageResponse的结果在root字段中，可能是Message或Task
                result = response.root
                
                # 根据结果类型处理响应
                if hasattr(result, 'parts'):  # 这是一个Message对象
                    response_text = get_message_text(result)
                    logger.info(f"Received A2A response: {response_text[:100]}...")
                    
                    return {
                        "status": "success",
                        "response": response_text,
                        "message": result,  # 保留原始消息对象以便后续处理
                        "message_id": getattr(result, 'message_id', None),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                else:  # 这可能是一个Task对象
                    logger.info(f"Received A2A task response: {result}")
                    return {
                        "status": "success", 
                        "response": str(result),
                        "task": result,
                        "task_id": getattr(result, 'id', None),
                        "timestamp": datetime.utcnow().isoformat()
                    }
            else:
                return {
                    "status": "error",
                    "error": "No response received",
                    "error_code": "NO_RESPONSE"
                }
                
        except Exception as e:
            # 增强的A2A错误处理
            error_info = self._handle_a2a_error(e)
            logger.error(f"A2A message sending failed to {agent_url}: {error_info}")
            return {
                "status": "error",
                "error": str(e),
                "error_details": error_info,
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def execute_task(
        self,
        agent_url: str,
        task_name: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        在指定Agent上执行任务
        使用官方SDK的任务执行功能
        
        Args:
            agent_url: 目标Agent的URL
            task_name: 任务名称
            parameters: 任务参数
            
        Returns:
            任务执行结果
        """
        try:
            client = await self.get_client(agent_url)
            if not client:
                return {"error": "Failed to create client for agent"}
            
            # 创建任务
            task = new_task(
                name=task_name,
                description=f"Execute {task_name} with parameters: {parameters}",
                arguments=parameters or {}
            )
            
            logger.info(f"Executing task {task_name} on {agent_url}")
            result = await client.execute_task(task)
            
            if result:
                logger.info(f"Task {task_name} completed successfully")
                return {
                    "success": True,
                    "result": result,
                    "task_name": task_name,
                    "timestamp": datetime.utcnow().isoformat()
                }
            else:
                return {"error": "Task execution failed"}
                
        except Exception as e:
            logger.error(f"Failed to execute task {task_name} on {agent_url}: {e}")
            return {"error": str(e)}
    
    async def get_agent_status(self, agent_url: str) -> Optional[Dict[str, Any]]:
        """
        获取Agent状态信息
        
        Args:
            agent_url: Agent的URL
            
        Returns:
            Agent状态信息
        """
        try:
            agent_card = await self.discover_agent(agent_url)
            if not agent_card:
                return {"error": "Agent not found or not accessible"}
            
            return {
                "name": agent_card.name,
                "description": agent_card.description,
                "version": agent_card.version,
                "url": agent_card.url,
                "capabilities": agent_card.capabilities.model_dump() if agent_card.capabilities else {},
                "skills": [skill.model_dump() for skill in agent_card.skills] if agent_card.skills else [],
                "status": "active",
                "last_checked": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get status for {agent_url}: {e}")
            return {"error": str(e)}
    
    async def list_agent_skills(self, agent_url: str) -> List[Dict[str, Any]]:
        """
        列出Agent的所有技能
        
        Args:
            agent_url: Agent的URL
            
        Returns:
            技能列表
        """
        try:
            agent_card = await self.discover_agent(agent_url)
            if not agent_card or not agent_card.skills:
                return []
            
            return [
                {
                    "id": skill.id,
                    "name": skill.name,
                    "description": skill.description,
                    "tags": skill.tags,
                    "examples": skill.examples
                }
                for skill in agent_card.skills
            ]
            
        except Exception as e:
            logger.error(f"Failed to list skills for {agent_url}: {e}")
            return []
    
    async def close(self):
        """关闭HTTP客户端"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    def clear_cache(self):
        """清空所有缓存"""
        self._agent_cache.clear()
        self._client_cache.clear()
        logger.info("A2A client cache cleared")
    
    def _handle_a2a_error(self, error: Exception) -> Dict[str, Any]:
        """
        处理A2A协议特定错误，符合11.2.2规范要求
        
        Args:
            error: 捕获的异常
            
        Returns:
            结构化的错误信息
        """
        error_str = str(error)
        error_info = {
            "error_type": type(error).__name__,
            "error_message": error_str
        }
        
        # 解析JSON-RPC错误码
        if hasattr(error, 'code') or '"code"' in error_str:
            try:
                # 尝试提取错误码
                if hasattr(error, 'code'):
                    code = error.code
                else:
                    # 从错误字符串中解析错误码
                    import re
                    match = re.search(r'"code":\s*(-?\d+)', error_str)
                    code = int(match.group(1)) if match else None
                
                if code:
                    error_info["a2a_error_code"] = code
                    error_info["a2a_error_name"] = self._get_a2a_error_name(code)
                    error_info["recommended_action"] = self._get_recommended_action(code)
                    
            except Exception as parse_error:
                logger.debug(f"Could not parse A2A error code: {parse_error}")
        
        # 检查传输层错误
        if "Connection" in error_str or "timeout" in error_str.lower():
            error_info["transport_error"] = True
            error_info["recommended_action"] = "retry_with_backoff"
        
        return error_info
    
    def _get_a2a_error_name(self, code: int) -> str:
        """根据A2A错误码返回错误名称"""
        a2a_errors = {
            -32001: "TaskNotFoundError",
            -32002: "TaskNotCancelableError", 
            -32003: "PushNotificationNotSupportedError",
            -32004: "UnsupportedOperationError",
            -32005: "ContentTypeNotSupportedError",
            -32006: "InvalidAgentResponseError",
            -32007: "AuthenticatedExtendedCardNotConfiguredError"
        }
        return a2a_errors.get(code, f"UnknownA2AError({code})")
    
    def _get_recommended_action(self, code: int) -> str:
        """根据A2A错误码返回推荐的处理动作"""
        actions = {
            -32001: "stop_polling_task_does_not_exist",
            -32002: "do_not_retry_cancel_task_in_terminal_state",
            -32003: "disable_push_notifications_for_this_agent",
            -32004: "check_agent_capabilities_and_adjust_request",
            -32005: "use_supported_content_type",
            -32006: "report_agent_implementation_issue",
            -32007: "use_public_agent_card_instead"
        }
        return actions.get(code, "retry_with_exponential_backoff")
    
    async def send_intent_message(
        self,
        agent_url: str,
        user_input: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        专门为意图路由器设计的A2A消息发送方法
        完全符合A2A协议规范，用于替代A2ATerminalClient
        
        Args:
            agent_url: 目标Agent的URL
            user_input: 用户输入内容
            context: 上下文信息
            
        Returns:
            标准化的响应格式，兼容现有的意图路由器逻辑
        """
        try:
            logger.info(f"🔄 Sending A2A-compliant intent message to {agent_url}")
            
            # 发送消息
            result = await self.send_message(agent_url, user_input, context=context)
            
            if result and result.get("status") == "success":
                # 构造兼容意图路由器的响应格式
                response_text = result.get("response", "")
                
                return {
                    "status": "success",
                    "type": "agent_response",
                    "response": response_text,
                    "message": result.get("message"),  # 原始A2A消息对象
                    "task": {
                        "history": [
                            {
                                "role": "user",
                                "parts": [{"kind": "text", "text": user_input}]
                            },
                            {
                                "role": "agent", 
                                "parts": [{"kind": "text", "text": response_text}]
                            }
                        ]
                    },
                    "agent_used": await self._get_agent_name(agent_url),
                    "timestamp": result.get("timestamp"),
                    "a2a_compliant": True
                }
            else:
                # 处理失败情况
                error_details = result.get("error_details", {}) if result else {}
                return {
                    "status": "failed",
                    "error": result.get("error", "Unknown error") if result else "No response",
                    "error_details": error_details,
                    "a2a_compliant": True
                }
                
        except Exception as e:
            logger.error(f"❌ A2A intent message failed: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "error_details": self._handle_a2a_error(e),
                "a2a_compliant": True
            }
    
    # ===== A2A协议标准方法 =====
    # 根据A2A协议v0.2.6规范实现的标准方法
    
    async def message_send(
        self,
        agent_url: str,
        message: str,
        task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        A2A协议标准方法: message/send
        向代理发送消息以启动新任务或继续现有任务
        
        这是A2A协议的核心方法，用于：
        - 启动新的交互任务
        - 继续现有的任务
        - 同步请求/响应交互
        
        Args:
            agent_url: 目标Agent的URL
            message: 要发送的消息内容
            task_id: 可选的任务ID（用于继续现有任务）
            context: 上下文信息
            
        Returns:
            Task对象或Message对象（根据A2A协议）
        """
        try:
            client = await self.get_client(agent_url)
            if not client:
                return {
                    "status": "failed",
                    "error": "Failed to create client for agent",
                    "a2a_compliant": True,
                    "method": "message/send"
                }
            
            # 创建A2A标准消息
            message_obj = new_agent_text_message(message)
            
            logger.info(f"A2A message/send to {agent_url}: {message[:50]}...")
            
            # 使用官方SDK的send_message方法 (对应message/send)
            if task_id:
                # 继续现有任务
                result = await client.send_message(message_obj, task_id=task_id)
            else:
                # 启动新任务
                result = await client.send_message(message_obj)
            
            if result:
                return {
                    "status": "success",
                    "result": result,
                    "agent_url": agent_url,
                    "timestamp": datetime.utcnow().isoformat(),
                    "a2a_compliant": True,
                    "method": "message/send"
                }
            else:
                return {
                    "status": "failed",
                    "error": "Message send failed",
                    "a2a_compliant": True,
                    "method": "message/send"
                }
                
        except Exception as e:
            logger.error(f"A2A message/send failed to {agent_url}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "error_details": self._handle_a2a_error(e),
                "a2a_compliant": True,
                "method": "message/send"
            }
    
    async def tasks_get(
        self,
        agent_url: str,
        task_id: str,
        history_length: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        A2A协议标准方法: tasks/get
        检索任务的当前状态（包括状态、工件和可选的历史记录）
        
        用于：
        - 轮询由message/send启动的任务状态
        - 获取任务的最终状态
        - 检索任务历史记录
        
        Args:
            agent_url: 目标Agent的URL
            task_id: 任务ID
            history_length: 要检索的历史消息数量
            
        Returns:
            Task对象（根据A2A协议）
        """
        try:
            client = await self.get_client(agent_url)
            if not client:
                return {
                    "status": "failed",
                    "error": "Failed to create client for agent",
                    "a2a_compliant": True,
                    "method": "tasks/get"
                }
            
            logger.info(f"A2A tasks/get {task_id} from {agent_url}")
            
            # 使用官方SDK的get_task方法 (对应tasks/get)
            task_result = await client.get_task(task_id, history_length=history_length)
            
            if task_result:
                return {
                    "status": "success",
                    "task": task_result,
                    "task_id": task_id,
                    "agent_url": agent_url,
                    "timestamp": datetime.utcnow().isoformat(),
                    "a2a_compliant": True,
                    "method": "tasks/get"
                }
            else:
                return {
                    "status": "failed",
                    "error": "Failed to get task",
                    "task_id": task_id,
                    "a2a_compliant": True,
                    "method": "tasks/get"
                }
                
        except Exception as e:
            logger.error(f"A2A tasks/get failed for {task_id} from {agent_url}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "error_details": self._handle_a2a_error(e),
                "task_id": task_id,
                "a2a_compliant": True,
                "method": "tasks/get"
            }
    
    # ===== 兼容性方法 =====
    # 保持向后兼容的同时提供A2A标准方法的别名
    
    async def submit_task(
        self,
        agent_url: str,
        task_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        兼容性方法：映射到A2A标准的message/send
        在A2A协议中，任务通过message/send方法创建，而不是单独的submit_task
        """
        # 将任务参数转换为消息
        message = f"Task: {task_name}"
        if parameters:
            message += f"\nParameters: {parameters}"
        
        # 使用标准的message/send方法
        return await self.message_send(agent_url, message, context=context)
    
    async def get_task_result(
        self,
        agent_url: str,
        task_id: str,
        timeout: float = 30.0
    ) -> Dict[str, Any]:
        """
        兼容性方法：映射到A2A标准的tasks/get
        """
        # 使用标准的tasks/get方法
        return await self.tasks_get(agent_url, task_id)

    async def _get_agent_name(self, agent_url: str) -> str:
        """获取Agent名称"""
        try:
            agent_card = await self.discover_agent(agent_url)
            return agent_card.name if agent_card else "Unknown Agent"
        except Exception:
            return "Unknown Agent"
    
    async def tasks_push_notification_config_set(
        self,
        agent_url: str,
        task_id: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        A2A协议标准方法: tasks/pushNotificationConfig/set
        设置任务的推送通知配置
        """
        try:
            client = await self.get_client(agent_url)
            if not client:
                return {
                    "status": "error",
                    "error": "Failed to create client for agent",
                    "error_code": "CLIENT_CREATION_FAILED",
                    "method": "tasks/pushNotificationConfig/set"
                }

            # 构造符合A2A协议的参数
            params = {
                "taskId": task_id,
                "config": config
            }
            
            logger.info(f"A2A tasks/pushNotificationConfig/set for task {task_id} to {agent_url}")
            
            # 目前官方SDK可能没有直接的pushNotificationConfig方法，使用底层HTTP调用
            try:
                # 尝试使用SDK的底层HTTP客户端
                http_client = await self._get_http_client()
                
                # 构造JSON-RPC请求
                import json
                from uuid import uuid4
                
                request_data = {
                    "jsonrpc": "2.0",
                    "id": str(uuid4()),
                    "method": "tasks/pushNotificationConfig/set",
                    "params": params
                }
                
                # 发送请求到Agent的端点
                response = await http_client.post(
                    agent_url,
                    json=request_data,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if "result" in result:
                        return {
                            "status": "success",
                            "result": result["result"],
                            "method": "tasks/pushNotificationConfig/set"
                        }
                    else:
                        return {
                            "status": "error",
                            "error": result.get("error", {}).get("message", "Unknown error"),
                            "error_code": result.get("error", {}).get("code", "UNKNOWN"),
                            "method": "tasks/pushNotificationConfig/set"
                        }
                else:
                    return {
                        "status": "error",
                        "error": f"HTTP {response.status_code}",
                        "error_code": "HTTP_ERROR",
                        "method": "tasks/pushNotificationConfig/set"
                    }
                    
            except Exception as e:
                logger.error(f"A2A tasks/pushNotificationConfig/set failed for task {task_id}: {e}")
                return {
                    "status": "error",
                    "error": str(e),
                    "error_code": "REQUEST_FAILED",
                    "method": "tasks/pushNotificationConfig/set"
                }
                
        except Exception as e:
            logger.error(f"A2A tasks/pushNotificationConfig/set failed for task {task_id}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "error_code": "GENERAL_ERROR",
                "method": "tasks/pushNotificationConfig/set"
            }

    def get_status(self) -> Dict[str, Any]:
        """获取客户端状态"""
        return {
            "service": "ZhipuA2AClient",
            "sdk_available": True,
            "cached_agents": len(self._agent_cache),
            "cached_clients": len(self._client_cache),
            "a2a_protocol_version": "v0.2.6",
            "standard_methods": ["message/send", "tasks/get", "message/stream"],
            "extended_methods": ["tasks/pushNotificationConfig/set"],
            "timestamp": datetime.utcnow().isoformat()
        }

# 创建全局A2A客户端实例
zhipu_a2a_client = ZhipuA2AClient()
