"""
Agent Registry and Management API
Agent注册表和管理API - 提供完整的外部Agent管理功能
"""
from fastapi import APIRouter, HTTPException, status
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from src.config.agent_registry import get_all_agents, get_enabled_agents
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["Agent Registry & Management"])

# Pydantic模型
class ExternalAgentInfo(BaseModel):
    """外部Agent信息"""
    agent_id: str
    name: str
    description: str
    url: str
    capabilities: List[str]
    tags: List[str]
    enabled: bool
    agent_card: Dict[str, Any]

class AddAgentRequest(BaseModel):
    """添加Agent请求"""
    agent_card_url: str = Field(..., description="Agent Card URL")
    agent_id: Optional[str] = Field(None, description="自定义Agent ID (可选)")

class AgentResponse(BaseModel):
    """Agent响应"""
    id: str
    name: str
    agent_card_url: str
    url: Optional[str] = None
    enabled: bool
    added_at: str
    capabilities: Optional[List[str]] = None

# ==================== Agent管理API (CRUD操作) ====================

@router.post("/", response_model=Dict[str, Any])
async def add_agent(request: AddAgentRequest):
    """添加新的A2A Agent"""
    try:
        from src.config.agent_registry import get_agent_registry
        
        registry = get_agent_registry()
        
        # 检查是否已存在相同URL的Agent
        all_agents = await registry.get_all_agents()
        for agent_id, agent_info in all_agents.items():
            if agent_info.get('agent_card_url') == request.agent_card_url:
                return {
                    "success": False,
                    "error": f"Agent with URL '{request.agent_card_url}' already exists",
                    "existing_agent_id": agent_id
                }
        
        # 添加Agent
        success = await registry.add_agent_by_card_url(
            request.agent_card_url, 
            request.agent_id
        )
        
        if success:
            # 获取添加后的Agent信息
            if request.agent_id:
                agent_info = await registry.get_agent_by_id(request.agent_id)
                agent_id = request.agent_id
            else:
                # 找到最新添加的Agent
                all_agents = await registry.get_all_agents()
                for aid, info in all_agents.items():
                    if info.get('agent_card_url') == request.agent_card_url:
                        agent_info = info
                        agent_id = aid
                        break
                else:
                    agent_info = None
                    agent_id = None
            
            return {
                "success": True,
                "message": "Agent added successfully",
                "agent": {
                    "id": agent_id,
                    "name": agent_info.get('name', 'Unknown') if agent_info else 'Unknown',
                    "agent_card_url": request.agent_card_url,
                    "url": agent_info.get('url') if agent_info else None,
                    "enabled": True,
                    "capabilities": agent_info.get('capabilities', []) if agent_info else []
                }
            }
        else:
            return {
                "success": False,
                "error": "Failed to add agent - unable to fetch agent card"
            }
            
    except Exception as e:
        logger.error(f"Failed to add agent: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@router.get("/list", response_model=Dict[str, Any])
async def list_agents():
    """获取所有已注册的Agent列表"""
    try:
        from src.config.agent_registry import get_agent_registry
        
        registry = get_agent_registry()
        all_agents = await registry.get_all_agents()
        
        agents_list = []
        for agent_id, agent_info in all_agents.items():
            agents_list.append({
                "id": agent_id,
                "name": agent_info.get('name', 'Unknown'),
                "agent_card_url": agent_info.get('agent_card_url'),
                "url": agent_info.get('url'),
                "enabled": agent_info.get('enabled', True),
                "added_at": agent_info.get('added_at'),
                "capabilities": agent_info.get('capabilities', []),
                "status": "available" if 'url' in agent_info else "unavailable"
            })
        
        return {
            "success": True,
            "agents": agents_list,
            "total": len(agents_list)
        }
        
    except Exception as e:
        logger.error(f"Failed to list agents: {e}")
        return {
            "success": False,
            "error": str(e),
            "agents": []
        }

@router.delete("/{agent_id}")
async def remove_agent(agent_id: str):
    """移除指定的Agent"""
    try:
        from src.config.agent_registry import get_agent_registry
        
        registry = get_agent_registry()
        success = registry.remove_agent(agent_id)
        
        return {
            "success": success,
            "message": f"Agent '{agent_id}' {'removed' if success else 'not found'}"
        }
        
    except Exception as e:
        logger.error(f"Failed to remove agent: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@router.put("/{agent_id}/enable")
async def enable_agent(agent_id: str):
    """启用指定的Agent"""
    try:
        from src.config.agent_registry import get_agent_registry
        
        registry = get_agent_registry()
        success = registry.enable_agent(agent_id)
        
        return {
            "success": success,
            "message": f"Agent '{agent_id}' {'enabled' if success else 'not found'}"
        }
        
    except Exception as e:
        logger.error(f"Failed to enable agent: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@router.put("/{agent_id}/disable")
async def disable_agent(agent_id: str):
    """禁用指定的Agent"""
    try:
        from src.config.agent_registry import get_agent_registry
        
        registry = get_agent_registry()
        success = registry.disable_agent(agent_id)
        
        return {
            "success": success,
            "message": f"Agent '{agent_id}' {'disabled' if success else 'not found'}"
        }
        
    except Exception as e:
        logger.error(f"Failed to disable agent: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@router.post("/reload")
async def reload_agent_config():
    """重新加载Agent配置文件"""
    try:
        from src.config.agent_registry import get_agent_registry
        
        registry = get_agent_registry()
        registry.reload_config()
        
        # 获取重新加载后的Agent列表
        all_agents = await registry.get_all_agents()
        
        return {
            "success": True,
            "message": "Agent configuration reloaded successfully",
            "agents_count": len(all_agents)
        }
        
    except Exception as e:
        logger.error(f"Failed to reload agent config: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# ==================== Agent发现和查询API (只读操作) ====================

@router.get("/registry", response_model=List[ExternalAgentInfo])
async def get_external_agents_registry(
    enabled_only: bool = False,
    capability: Optional[str] = None,
    tag: Optional[str] = None
):
    """
    获取外部Agent注册表
    
    - **enabled_only**: 仅返回启用的Agent
    - **capability**: 按能力筛选Agent
    - **tag**: 按标签筛选Agent
    """
    try:
        # 获取Agent配置
        if enabled_only:
            agents_config = get_enabled_agents()
        else:
            agents_config = get_all_agents()
        
        # 转换为响应格式
        agents_list = []
        for agent_id, config in agents_config.items():
            # 应用筛选条件
            if capability and capability not in config.get("capabilities", []):
                continue
            if tag and tag not in config.get("tags", []):
                continue
                
            agent_info = ExternalAgentInfo(
                agent_id=config["agent_id"],
                name=config["name"],
                description=config["description"],
                url=config["url"],
                capabilities=config.get("capabilities", []),
                tags=config.get("tags", []),
                enabled=config.get("enabled", False),
                agent_card=config.get("agent_card", {})
            )
            agents_list.append(agent_info)
        
        logger.info(f"Retrieved {len(agents_list)} external agents from registry")
        return agents_list
        
    except Exception as e:
        logger.error(f"Failed to get external agents registry: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve external agents: {str(e)}"
        )

@router.get("/summary")
async def get_external_agents_summary():
    """
    获取外部Agent注册表摘要统计信息
    """
    try:
        # 获取外部Agent统计
        all_external_agents = get_all_agents()
        enabled_external_agents = get_enabled_agents()
        
        # 统计能力
        capabilities_summary = {}
        agent_types = {"external_agent": len(all_external_agents)}
        
        # 统计外部Agent能力
        for agent_id, config in all_external_agents.items():
            for capability in config.get("capabilities", []):
                capabilities_summary[capability] = capabilities_summary.get(capability, 0) + 1
        
        summary = {
            "total_external_agents": len(all_external_agents),
            "enabled_external_agents": len(enabled_external_agents),
            "agent_types": agent_types,
            "capabilities_summary": capabilities_summary
        }
        
        logger.info("Generated external agents registry summary")
        return summary
        
    except Exception as e:
        logger.error(f"Failed to get external agents summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve external agents summary: {str(e)}"
        )
