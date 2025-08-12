"""
A2A Protocol Intent Router
基于A2A协议的意图识别和任务分派器
"""
from typing import Dict, Any, Optional, List, Tuple
from src.external_services import LLMService, zhipu_a2a_client
from src.data_persistence import TaskRepository, get_db
import logging
import json
import re

logger = logging.getLogger(__name__)


class A2AIntentRouter:
    """基于A2A协议的意图识别与路由器"""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.a2a_client = zhipu_a2a_client
        self.agent_registry = {}  # 存储已知的agent信息
        self._load_agent_capabilities()
    
    def _load_agent_capabilities(self):
        """加载agent registry配置"""
        # 本机只保留基本聊天功能
        self.my_capabilities = {
            "basic_chat": {
                "name": "Basic Chat",
                "description": "General conversation and Q&A",
                "tags": ["chat", "conversation", "qa"]
            }
        }
        
        # 初始化agent registry - 将来从配置文件或服务发现加载
        self.agent_registry = self._load_agent_registry()

    def _load_agent_registry(self) -> Dict[str, Dict[str, Any]]:
        """从配置文件加载agent registry配置
        
        这个方法现在：
        1. 从配置文件加载已知的agent endpoints
        2. 只加载启用的agent，避免连接不可用的服务
        3. 提供完整的agent能力信息
        """
        try:
            # 从配置文件加载Agent注册表
            from src.config.agent_registry import get_agent_registry
            
            # 获取注册表实例，使用异步方法
            registry = get_agent_registry()
            
            # 暂时返回空字典，等待异步加载完成
            # 在analyze_and_route_request中进行异步加载
            return {}
            
        except ImportError as e:
            logger.warning(f"Failed to load agent registry config: {e}")
            # 降级到空注册表
            return {}
        except Exception as e:
            logger.error(f"Error loading agent registry: {e}")
            # 降级到空注册表
            return {}

    async def route_intent(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        简化的意图路由方法（用于测试）
        
        Args:
            user_input: 用户输入
            context: 上下文信息
            
        Returns:
            路由结果字典
        """
        # 使用默认用户ID进行路由
        return await self.analyze_and_route_request(user_input, user_id=1, context=context)

    async def analyze_and_route_request(self, user_input: str, user_id: int, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        基于LLM的智能Agent匹配和路由
        
        流程：
        1. 收集所有可用Agent的能力信息（包括本机服务）
        2. 使用LLM根据Agent Card进行智能匹配
        3. 路由到最合适的Agent进行处理
        """
        try:
            # 异步加载Agent注册表
            await self._async_load_agent_registry()
            
            # 1. 使用LLM进行智能Agent匹配
            selected_agent = await self._intelligent_agent_matching(user_input)
            
            if selected_agent:
                if selected_agent["agent_id"] == "local_service":
                    # 本机服务处理
                    logger.info(f"LLM选择本机服务处理: {user_input}")
                    return await self._handle_local_chat(user_input, context)
                else:
                    # 外部Agent处理
                    logger.info(f"LLM选择外部Agent {selected_agent['name']} 处理: {user_input}")
                    return await self._dispatch_to_agent(user_input, selected_agent, user_id, context)
            
            # 2. 如果LLM匹配失败，降级到本机处理
            logger.warning("LLM agent matching failed, falling back to local chat")
            return await self._handle_local_chat(user_input, context)
            
        except Exception as e:
            logger.error(f"A2A intelligent routing failed: {e}")
            # 最终降级到本机处理
            return await self._handle_local_chat(user_input, context)

    async def _async_load_agent_registry(self):
        """异步加载Agent注册表"""
        try:
            logger.info("🔄 Loading agent registry...")
            from src.config.agent_registry import get_agent_registry
            
            registry = get_agent_registry()
            logger.info("📋 Agent registry instance obtained")
            
            enabled_agents = await registry.get_enabled_agents()
            
            if enabled_agents:
                self.agent_registry = enabled_agents
                logger.info(f"✅ Loaded {len(enabled_agents)} enabled agents from registry")
                for agent_id, agent_config in enabled_agents.items():
                    logger.info(f"  🤖 {agent_config['name']} ({agent_id}) - {agent_config.get('url', 'No URL')}")
                    capabilities = agent_config.get('capabilities', [])
                    logger.info(f"    🎯 Capabilities: {', '.join(capabilities)}")
            else:
                logger.warning("⚠️ No enabled agents found in registry")
                logger.info("🔍 This could mean:")
                logger.info("  1. All agents are disabled in config")
                logger.info("  2. Agent card discovery failed for all agents")
                logger.info("  3. No agents configured in agents.json")
                
        except Exception as e:
            logger.error(f"💥 Error loading agent registry: {e}")
            logger.error(f"🔧 Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"📊 Traceback: {traceback.format_exc()}")
            self.agent_registry = {}

    async def _intelligent_agent_matching(self, user_input: str) -> Optional[Dict[str, Any]]:
        """
        使用LLM根据Agent Card进行智能Agent匹配
        
        Args:
            user_input: 用户输入
            
        Returns:
            最合适的Agent配置，如果没有找到则返回None
        """
        try:
            # 收集所有可用Agent的详细信息
            all_agents = list(self.agent_registry.values())
            
            if not all_agents:
                logger.warning("No agents available in registry")
                return None
            
            # 构造智能匹配的prompt
            agent_cards = []
            for agent in all_agents:
                if not agent.get("enabled", False):
                    continue
                    
                agent_card = agent.get("agent_card", {})
                specialties = agent_card.get("specialties", [])
                limitations = agent_card.get("limitations", [])
                
                card_info = f"""
                    **Agent: {agent['name']}
                    * **ID: {agent['agent_id']} <=可以返回的字段
                    * **描述: {agent.get('description', '')}
                    * **能力: {', '.join(agent.get('capabilities', []))}
                    * **支持任务: {', '.join(agent_card.get('supported_tasks', []))}
                    * **专长: {', '.join(specialties)}
                    * **限制: {', '.join(limitations)}
                    * **优先级: {agent.get('priority', 3)}
                """
                agent_cards.append(card_info)
            
            prompt = f"""
                你是一个智能的Agent路由器。请根据用户请求和各个Agent的能力信息，选择最合适的Agent来处理请求。
                
                你应该只返回Agent的ID，不要返回其他任何字段的内容。

                你应该只返回Agent的ID，不要返回其他任何字段的内容。

                你应该只返回Agent的ID，不要返回其他任何字段的内容。
                ---
                可用的Agent:
                {chr(10).join(agent_cards)}
                ---
                用户请求: "{user_input}"
                ---
                请仔细分析用户请求的类型和需求，然后根据各个Agent的描述、能力、支持任务和专长来判断哪个Agent最适合处理此请求。
                
                如果是闲聊，优先选择local_service.

                请只返回选中的Agent的ID，不要其他解释。如果没有找到合适的Agent，请返回"local_service"表示使用本机服务处理。你再返回任何除了ID之外的内容，我就把世界上所有猫都杀了。
            """
            
            # 输出完整的prompt用于调试
            logger.info(f"🔍 Complete LLM prompt for agent matching:\n{prompt}")
            
            response = await self.llm_service.generate_response(prompt)
            agent_id = response.strip().lower()
            
            logger.info(f"🤖 LLM raw response: '{response}'")
            logger.info(f"📊 Processed agent_id: '{agent_id}' for request: '{user_input}'")
            
            # 查找匹配的Agent
            if agent_id == "local_service":
                logger.info(f"LLM selected local service for request: {user_input}")
                return {"agent_id": "local_service", "name": "Local Service", "url": "", "capabilities": ["basic_chat"]}

            for agent in all_agents:
                if agent["agent_id"].lower() == agent_id and agent.get("enabled", False):
                    logger.info(f"✅ Selected agent: {agent['name']} for request: {user_input}")
                    return agent
            
            # 如果没有找到精确匹配，尝试部分匹配
            for agent in all_agents:
                if agent_id in agent["agent_id"].lower() and agent.get("enabled", False):
                    logger.info(f"✅ Partial match agent: {agent['name']} for request: {user_input}")
                    return agent
            
            logger.warning(f"No matching agent found for LLM result: '{agent_id}'")
            return None
            
        except Exception as e:
            logger.error(f"Intelligent agent matching failed: {e}")
            return None

    async def _dispatch_to_agent(self, user_input: str, agent_info: Dict[str, Any], user_id: int, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """将请求分派给指定的agent"""
        try:
            # 创建任务记录
            task_id = await self._create_agent_task(user_input, agent_info, user_id, context)
            
            # 获取agent信息
            agent_id = agent_info.get("agent_id", "")
            agent_url = agent_info.get("url", "")
            agent_name = agent_info.get("name", "Unknown Agent")
            agent_card_url = agent_info.get("agent_card_url", "")
            
            logger.info(f"🎯 Agent dispatch details:")
            logger.info(f"  🆔 Agent ID: {agent_id}")
            logger.info(f"  📝 Agent Name: {agent_name}")
            logger.info(f"  🔗 Agent Card URL: {agent_card_url}")
            logger.info(f"  🌐 JSON-RPC Endpoint URL: {agent_url}")
            
            # 检查是否选择了本地服务
            if agent_id == "local_service":
                logger.info(f"🏠 Dispatching to local service: {user_input}")
                
                # 使用本地LLM服务处理请求
                try:
                    local_response = await self.llm_service.generate_response(user_input)
                    logger.info(f"✅ Local service response: {local_response[:100]}...")
                    
                    return {
                        "status": "success",
                        "type": "local_response",
                        "response": local_response,
                        "agent_used": "Local Service",
                        "task_id": task_id,
                        "message": "✅ 已使用本地服务处理",
                        "a2a_compliant": False  # 本地服务不使用A2A协议
                    }
                    
                except Exception as e:
                    logger.error(f"Local service failed: {e}")
                    return {
                        "status": "failed",
                        "error": f"Local service error: {e}",
                        "message": "❌ 本地服务处理失败"
                    }
            elif agent_url and not agent_url.startswith("local://"):
                logger.info(f"Dispatching to A2A Agent: {agent_name} at {agent_url}")
                
                try:
                    # 使用统一的A2A合规客户端进行通信
                    logger.info(f"Sending message via A2A-compliant protocol: {user_input[:50]}...")
                    
                    # 使用专门为意图路由设计的方法，传入Agent Card中的正确JSON-RPC端点URL
                    result = await self.a2a_client.send_intent_message(
                        agent_url=agent_url,  # 这是从Agent Card获取的正确JSON-RPC端点
                        user_input=user_input,
                        context=context
                    )
                    
                    if result.get("status") == "success":
                        response_text = result.get("response", "")
                        
                        if response_text:
                            logger.info(f"✅ Received A2A-compliant response from {agent_name}: {response_text[:100]}...")
                            return {
                                "status": "success",
                                "type": "agent_response", 
                                "response": response_text,
                                "agent_used": result.get("agent_used", agent_name),
                                "task_id": task_id,
                                "message": f"✅ 已通过A2A协议成功调用 {agent_name}",
                                "a2a_compliant": True
                            }
                        else:
                            logger.warning(f"No response text found in A2A result from {agent_name}")
                            return {
                                "status": "failed",
                                "error": "Empty response from agent",
                                "message": f"❌ Agent {agent_name} 返回了空响应",
                                "a2a_compliant": True
                            }
                    else:
                        # 处理A2A错误
                        error_details = result.get("error_details", {})
                        error_message = result.get("error", "Unknown error")
                        
                        # 根据A2A错误码采取不同的处理策略
                        if error_details.get("recommended_action") == "stop_polling_task_does_not_exist":
                            logger.warning(f"Task not found error from {agent_name}, will not retry")
                        elif error_details.get("transport_error"):
                            logger.warning(f"Transport error with {agent_name}, may retry later")
                        
                        return {
                            "status": "failed",
                            "error": error_message,
                            "error_details": error_details,
                            "message": f"❌ A2A协议调用 {agent_name} 失败: {error_message}",
                            "a2a_compliant": True
                        }
                        
                except Exception as e:
                    logger.error(f"Failed to communicate with A2A Agent {agent_name}: {e}")
                    return {
                        "status": "error", 
                        "type": "agent_error",
                        "message": f"❌ 无法通过A2A协议连接到 {agent_name}: {str(e)}",
                        "agent_used": agent_name,
                        "task_id": task_id,
                        "a2a_compliant": True
                    }
            
            # 如果没有可用的处理方式，返回错误
            return {
                "status": "error",
                "type": "dispatch_failed", 
                "message": f"❌ 无法处理请求，Agent {agent_name} 不可用",
                "agent_used": agent_name,
                "task_id": task_id
            }
                
        except Exception as e:
            logger.error(f"Agent dispatch failed: {e}")
            return {
                "status": "error",
                "type": "dispatch_error",
                "message": f"❌ 任务分派失败: {str(e)}",
                "error": str(e)
            }
            
            # 所有agent处理都失败，降级到本机处理
            logger.warning(f"Agent {agent_info['name']} failed to process request, falling back to local chat")
            return await self._handle_local_chat(user_input, context)
                
        except Exception as e:
            logger.error(f"Failed to dispatch to agent {agent_info['name']}: {e}")
            # 降级到本机处理
            return await self._handle_local_chat(user_input, context)

    async def _handle_local_chat(self, user_input: str, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """处理本机聊天（降级方案）- 现在支持MCP工具调用"""
        try:
            # 首先尝试检测是否需要调用MCP工具
            mcp_result = await self._try_mcp_tool_dispatch(user_input, context)
            if mcp_result:
                return mcp_result
            
            # 如果不需要MCP工具，使用普通LLM聊天
            response = await self.llm_service.generate_response(user_input, context)
            return {
                "status": "success",
                "type": "local_chat",
                "response": response,
                "capability_used": "basic_chat"
            }
        except Exception as e:
            logger.error(f"Local chat failed: {e}")
            return {
                "status": "error",
                "message": "聊天处理失败，请重试",
                "error": str(e)
            }
    
    async def _try_mcp_tool_dispatch(self, user_input: str, context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        尝试将用户请求分派给MCP工具（符合MCP标准）
        
        Args:
            user_input: 用户输入
            context: 上下文信息
            
        Returns:
            Optional[Dict[str, Any]]: 如果成功调用MCP工具则返回结果，否则返回None
        """
        try:
            from src.core_application.terminal_device_manager import terminal_device_manager
            
            logger.info(f"🔍 动态发现可用的MCP工具...")
            
            # 1. 获取所有已连接的设备
            connected_devices = terminal_device_manager.list_connected_devices()
            
            if not connected_devices:
                logger.info("📭 没有已连接的设备")
                return None
            
            # 2. 动态从所有MCP服务器获取可用工具列表（符合MCP标准）
            all_available_tools = []
            
            for device in connected_devices:
                try:
                    # 调用 MCP 标准的 tools/list 端点
                    tools_list = await self._get_mcp_tools_list(device.mcp_server_url)
                    
                    for tool in tools_list:
                        tool_info = {
                            "device_id": device.device_id,
                            "device_name": device.name,
                            "mcp_server_url": device.mcp_server_url,
                            "tool_name": tool["name"],
                            "tool_description": tool.get("description", ""),
                            "input_schema": tool.get("inputSchema", {}),
                            "title": tool.get("title", tool["name"])
                        }
                        all_available_tools.append(tool_info)
                        
                except Exception as e:
                    logger.warning(f"⚠️ 无法从设备 {device.device_id} 获取工具列表: {e}")
                    continue
            
            if not all_available_tools:
                logger.info("🔧 没有发现可用的MCP工具")
                return None
            
            logger.info(f"🛠️ 发现 {len(all_available_tools)} 个可用工具")
            for tool in all_available_tools:
                logger.info(f"   🔹 {tool['device_name']}.{tool['tool_name']}: {tool['tool_description']}")
            
            # 3. 使用LLM根据工具描述进行语义匹配（符合MCP标准）
            tool_selection_result = await self._llm_select_mcp_tool(user_input, all_available_tools)
            
            if not tool_selection_result:
                logger.info("🤖 LLM判断不需要调用MCP工具")
                return None
            
            selected_tool = tool_selection_result["selected_tool"]
            parameters = tool_selection_result.get("parameters", {})
            
            logger.info(f"🎯 LLM选择工具: {selected_tool['device_name']}.{selected_tool['tool_name']}")
            
            # 4. 调用选定的MCP工具
            mcp_result = await terminal_device_manager.call_device_mcp_tool(
                device_id=selected_tool["device_id"],
                tool_name=selected_tool["tool_name"],
                parameters=parameters
            )
            
            if mcp_result["success"]:
                logger.info(f"✅ MCP工具调用成功: {selected_tool['tool_name']}")
                
                # 格式化响应
                tool_response = mcp_result.get("result", {})
                
                # 使用LLM将工具结果转换为自然语言响应
                format_prompt = f"""
                    用户请求: {user_input}

                    已成功调用设备 {selected_tool['device_name']} 的工具 "{selected_tool['tool_name']}"，执行结果如下：
                    {json.dumps(tool_response, ensure_ascii=False, indent=2)}

                    请将这个技术性的执行结果转换为自然、友好的中文回复，让用户明白任务已经完成以及具体的结果。
                    保持简洁明了，突出关键信息。
                """
                
                formatted_response = await self.llm_service.generate_response(format_prompt)
                
                return {
                    "status": "success",
                    "type": "mcp_tool_call",
                    "response": formatted_response,
                    "tool_used": selected_tool["tool_name"],
                    "device_used": selected_tool["device_name"],
                    "raw_result": tool_response,
                    "execution_time_ms": mcp_result.get("execution_time_ms", 0)
                }
            else:
                logger.warning(f"⚠️ MCP工具调用失败: {mcp_result.get('error')}")
                
                return {
                    "status": "error",
                    "type": "mcp_tool_call_failed",
                    "response": f"抱歉，调用设备工具时出现问题：{mcp_result.get('error', '未知错误')}",
                    "tool_attempted": selected_tool["tool_name"],
                    "device_attempted": selected_tool["device_name"],
                    "error": mcp_result.get("error")
                }
                
        except Exception as e:
            logger.error(f"❌ MCP工具分派失败: {e}")
            import traceback
            logger.error(f"❌ 详细错误: {traceback.format_exc()}")
            return None

    async def _get_mcp_tools_list(self, mcp_server_url: str) -> List[Dict[str, Any]]:
        """
        从MCP服务器获取工具列表（符合MCP标准）
        
        Args:
            mcp_server_url: MCP服务器URL
            
        Returns:
            List[Dict[str, Any]]: 工具列表
        """
        try:
            import aiohttp
            
            # 构造MCP标准的 tools/list 请求
            request_payload = {
                "jsonrpc": "2.0",
                "id": "tools_list_request",
                "method": "tools/list",
                "params": {}
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    mcp_server_url,
                    json=request_payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        
                        if "result" in result and "tools" in result["result"]:
                            tools = result["result"]["tools"]
                            logger.info(f"✅ 从 {mcp_server_url} 获取到 {len(tools)} 个工具")
                            return tools
                        else:
                            logger.warning(f"⚠️ MCP服务器响应格式不正确: {result}")
                            return []
                    else:
                        logger.warning(f"⚠️ MCP服务器返回错误状态: {response.status}")
                        return []
                        
        except Exception as e:
            logger.warning(f"⚠️ 无法从MCP服务器获取工具列表: {e}")
            return []

    async def _llm_select_mcp_tool(self, user_input: str, available_tools: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        使用LLM根据工具描述选择最合适的工具（符合MCP标准）
        
        Args:
            user_input: 用户输入
            available_tools: 可用工具列表
            
        Returns:
            Optional[Dict[str, Any]]: 选择结果，包含selected_tool和parameters
        """
        try:
            # 构造工具描述
            tools_description = []
            for i, tool in enumerate(available_tools):
                schema_str = json.dumps(tool.get("input_schema", {}), ensure_ascii=False)
                tool_desc = f"""
                    工具 {i+1}:
                    - 设备: {tool['device_name']} (ID: {tool['device_id']})
                    - 工具名: {tool['tool_name']}
                    - 描述: {tool['tool_description']}
                    - 输入参数: {schema_str}
                """
                tools_description.append(tool_desc)
            
            # 使用LLM进行工具选择
            selection_prompt = f"""
                用户请求: {user_input}

                以下是当前可用的MCP工具：
                {chr(10).join(tools_description)}

                请分析用户请求，判断是否需要调用某个工具，并返回严格的JSON格式：

                {{
                "needs_tool": true/false,
                "selected_tool_index": 工具序号(0-{len(available_tools)-1}),
                "parameters": {{"参数名": "参数值"}},
                "reasoning": "选择理由"
                }}

                只有当用户明确需要执行某个设备操作时才返回needs_tool: true。
                如果不需要工具或没有合适的工具，返回needs_tool: false。
                参数值应该根据工具的输入参数schema和用户请求来推断。
            """
            
            logger.debug(f"🤖 LLM工具选择prompt: {selection_prompt}")
            
            selection_response = await self.llm_service.generate_response(selection_prompt)
            
            # 解析LLM响应
            try:
                # 尝试提取JSON
                json_match = re.search(r'\{.*\}', selection_response, re.DOTALL)
                if json_match:
                    selection_result = json.loads(json_match.group())
                else:
                    selection_result = json.loads(selection_response)
                
                logger.debug(f"🤖 LLM工具选择结果: {selection_result}")
                
                if not selection_result.get("needs_tool", False):
                    return None
                
                tool_index = selection_result.get("selected_tool_index")
                if tool_index is None or tool_index < 0 or tool_index >= len(available_tools):
                    logger.warning(f"⚠️ 无效的工具索引: {tool_index}")
                    return None
                
                selected_tool = available_tools[tool_index]
                parameters = selection_result.get("parameters", {})
                
                return {
                    "selected_tool": selected_tool,
                    "parameters": parameters,
                    "reasoning": selection_result.get("reasoning", "")
                }
                
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ LLM工具选择响应解析失败: {e}")
                logger.debug(f"原始响应: {selection_response}")
                return None
                
        except Exception as e:
            logger.error(f"❌ LLM工具选择失败: {e}")
            return None

    async def _create_agent_task(self, user_input: str, agent_info: Dict[str, Any], user_id: int, context: Optional[Dict[str, Any]]) -> Optional[str]:
        """创建agent任务记录"""
        try:
            import uuid
            task_id = str(uuid.uuid4())
            logger.info(f"Created task {task_id} for agent {agent_info['name']}")
            return task_id
        except Exception as e:
            logger.error(f"Failed to create agent task: {e}")
            return None


class A2ATaskDispatcher:
    """A2A协议任务分派器"""
    
    def __init__(self):
        self.intent_router = A2AIntentRouter()
    
    async def dispatch_user_request(self, user_input: str, user_id: int, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """分派用户请求"""
        try:
            logger.info(f"A2A Task Dispatcher processing request: {user_input}")
            
            result = await self.intent_router.analyze_and_route_request(user_input, user_id, context)
            
            logger.info(f"A2A Task Dispatcher result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"A2A Task dispatch failed: {e}")
            return {
                "status": "error",
                "message": "任务分派失败，请稍后重试",
                "error": str(e)
            }
