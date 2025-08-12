"""
A2A Agent注册表配置
通过Agent Card地址进行简单注册和管理
"""
import json
import os
import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class SimpleAgentRegistry:
    """
    简单A2A Agent注册表
    配置文件只存储Agent Card URL，运行时动态获取Agent信息
    """
    
    def __init__(self, config_file: Optional[str] = None):
        # 使用统一的配置管理器
        from src.config.agent_card_manager import AgentRegistryManager
        if config_file:
            self.config_manager = AgentRegistryManager()
            self.config_manager.config_file = config_file
        else:
            self.config_manager = AgentRegistryManager()
        
        self.agent_urls: Dict[str, Dict[str, Any]] = {}  # 存储配置的URL信息
        self.agent_cache: Dict[str, Dict[str, Any]] = {}  # 缓存动态获取的Agent信息
        self._load_config()
    
    def _load_config(self):
        """加载配置文件 - 只加载URL配置"""
        try:
            config = self.config_manager.load_config()
            
            agents_list = config.get('agents', [])
            logger.info(f"📖 Found {len(agents_list)} agents in config file")
            
            for agent_config in agents_list:
                agent_id = agent_config['id']
                agent_url_info = {
                    "id": agent_id,
                    "name": agent_config.get('name', f"Agent {agent_id}"),
                    "agent_card_url": agent_config['agent_card_url'],
                    "enabled": agent_config.get('enabled', True),
                    "added_at": agent_config.get('added_at', datetime.utcnow().isoformat())
                }
                self.agent_urls[agent_id] = agent_url_info
                
                logger.info(f"📝 Loaded agent config: {agent_id}")
                logger.debug(f"   🔗 URL: {agent_url_info['agent_card_url']}")
                logger.debug(f"   ✅ Enabled: {agent_url_info['enabled']}")
            
            logger.info(f"✅ Loaded {len(self.agent_urls)} agent URLs from config")
                
        except Exception as e:
            logger.error(f"Failed to load agent config: {e}")
            self._create_empty_config()
    
    def _create_empty_config(self):
        """创建空的配置文件"""
        try:
            empty_config = self.config_manager.create_empty_config()
            logger.info(f"Created empty agent config")
        except Exception as e:
            logger.error(f"Failed to create empty config: {e}")
        
        # 初始化为空
        self.agent_urls = {}
    
    async def _fetch_agent_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """动态获取Agent的详细信息"""
        from datetime import datetime, timedelta
        
        url_config = self.agent_urls.get(agent_id)
        if not url_config or not url_config['enabled']:
            return None
        
        # 检查缓存
        if agent_id in self.agent_cache:
            cached_info = self.agent_cache[agent_id]
            # 如果缓存时间不超过5分钟，直接返回
            if 'cached_at' in cached_info:
                cached_time = datetime.fromisoformat(cached_info['cached_at'])
                if datetime.utcnow() - cached_time < timedelta(minutes=5):
                    return cached_info
        
        try:
            from src.external_services.zhipu_a2a_client import zhipu_a2a_client
            
            agent_card_url = url_config['agent_card_url']
            logger.info(f"🔍 Fetching agent info for {agent_id}")
            logger.info(f"📍 Agent card URL: {agent_card_url}")
            logger.debug(f"🔧 Full URL config: {url_config}")
            
            agent_card = await zhipu_a2a_client.discover_agent(agent_card_url)
            if agent_card:
                logger.info(f"✅ Successfully fetched agent card for {agent_id}: {agent_card.name}")
                # 构建完整的Agent信息
                agent_info = {
                    "agent_id": agent_id,
                    "name": agent_card.name,
                    "description": agent_card.description,
                    "agent_card_url": agent_card_url,
                    "url": agent_card.url,
                    "version": agent_card.version,
                    "protocol_version": agent_card.protocol_version,
                    "capabilities": self._extract_capabilities(agent_card),
                    "skills": [skill.model_dump() for skill in agent_card.skills] if agent_card.skills else [],
                    "enabled": url_config['enabled'],
                    "added_at": url_config['added_at'],
                    "cached_at": datetime.utcnow().isoformat(),
                    "last_updated": datetime.utcnow().isoformat()
                }
                
                # 缓存信息
                self.agent_cache[agent_id] = agent_info
                logger.debug(f"Cached agent info for {agent_id}")
                return agent_info
            else:
                logger.error(f"❌ Failed to fetch agent card for {agent_id} from {agent_card_url}")
                return None
                
        except Exception as e:
            logger.error(f"💥 Error fetching agent info for {agent_id}: {e}")
            logger.error(f"🔗 Agent card URL was: {url_config.get('agent_card_url', 'NOT_SET')}")
            return None
    
    async def add_agent_by_card_url(self, agent_card_url: str, agent_id: Optional[str] = None) -> bool:
        """
        添加Agent Card URL到配置文件
        """
        try:
            # 生成Agent ID
            if not agent_id:
                from src.external_services.zhipu_a2a_client import zhipu_a2a_client
                # 先获取Agent Card来生成ID
                agent_card = await zhipu_a2a_client.discover_agent(agent_card_url)
                if agent_card:
                    agent_id = self._generate_agent_id(agent_card.name)
                else:
                    logger.error(f"Failed to discover agent from {agent_card_url}")
                    return False
            
            # 添加到URL配置
            self.agent_urls[agent_id] = {
                "id": agent_id,
                "name": agent_card.name if 'agent_card' in locals() else f"Agent {agent_id}",
                "agent_card_url": agent_card_url,
                "enabled": True,
                "added_at": datetime.utcnow().isoformat()
            }
            
            # 保存配置文件
            await self._save_config()
            
            # 清除缓存，强制重新获取
            if agent_id in self.agent_cache:
                del self.agent_cache[agent_id]
            
            logger.info(f"Successfully added agent URL: {agent_id} -> {agent_card_url}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding agent URL {agent_card_url}: {e}")
            return False
    
    def _generate_agent_id(self, name: str) -> str:
        """生成Agent ID"""
        import re
        # 清理名称，生成ID
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())
        clean_name = re.sub(r'_{2,}', '_', clean_name)  # 合并多个下划线
        clean_name = clean_name.strip('_')  # 移除首尾下划线
        
        # 确保唯一性
        base_id = clean_name
        counter = 1
        while base_id in self.agent_urls:
            base_id = f"{clean_name}_{counter}"
            counter += 1
        
        return base_id
    
    def _extract_capabilities(self, agent_card) -> List[str]:
        """从Agent Card提取能力"""
        capabilities = []
        
        if agent_card.skills:
            for skill in agent_card.skills:
                # 直接使用技能ID作为能力
                capabilities.append(skill.id)
                
                # 如果有标签，也添加到能力列表
                if skill.tags:
                    capabilities.extend(skill.tags)
        
        return list(set(capabilities))  # 去重
    
    async def _save_config(self):
        """保存配置到文件 - 只保存URL配置"""
        try:
            config = {
                "agents": []
            }
            
            for agent_id, url_config in self.agent_urls.items():
                config["agents"].append(url_config)
            
            self.config_manager.save_config(config)
            logger.debug(f"Saved agent URLs using config manager")
            
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
    
    async def get_enabled_agents(self) -> Dict[str, Any]:
        """返回启用的Agent配置 - 动态获取详细信息"""
        logger.info("🔍 Getting enabled agents from registry")
        logger.info(f"📊 Total agent URLs in registry: {len(self.agent_urls)}")
        
        enabled_agents = {}
        
        for agent_id, url_config in self.agent_urls.items():
            logger.info(f"🤖 Processing agent: {agent_id}")
            logger.debug(f"   Config: {url_config}")
            
            if url_config.get('enabled', True):
                logger.info(f"✅ Agent {agent_id} is enabled, fetching details...")
                agent_info = await self._fetch_agent_info(agent_id)
                if agent_info:
                    enabled_agents[agent_id] = agent_info
                    logger.info(f"✅ Added {agent_id} to enabled agents list")
                else:
                    logger.warning(f"❌ Failed to fetch info for enabled agent {agent_id}")
            else:
                logger.info(f"❌ Agent {agent_id} is disabled, skipping")
        
        logger.info(f"🎯 Final enabled agents count: {len(enabled_agents)}")
        return enabled_agents
    
    async def get_all_agents(self) -> Dict[str, Any]:
        """返回所有Agent配置 - 动态获取详细信息"""
        all_agents = {}
        
        for agent_id in self.agent_urls.keys():
            agent_info = await self._fetch_agent_info(agent_id)
            if agent_info:
                all_agents[agent_id] = agent_info
            else:
                # 如果无法获取详细信息，返回基本URL配置
                all_agents[agent_id] = {
                    **self.agent_urls[agent_id],
                    "status": "unavailable",
                    "last_checked": datetime.utcnow().isoformat()
                }
        
        return all_agents
    
    async def refresh_agent_info(self, agent_id: str) -> bool:
        """刷新Agent信息 - 清除缓存，强制重新获取"""
        if agent_id not in self.agent_urls:
            logger.error(f"Agent {agent_id} not found in configuration")
            return False
        
        # 清除缓存
        if agent_id in self.agent_cache:
            del self.agent_cache[agent_id]
        
        # 重新获取信息
        agent_info = await self._fetch_agent_info(agent_id)
        if agent_info:
            logger.info(f"Refreshed agent info for {agent_id}")
            return True
        else:
            logger.error(f"Failed to refresh agent info for {agent_id}")
            return False
    
    def remove_agent(self, agent_id: str) -> bool:
        """移除Agent"""
        if agent_id in self.agent_urls:
            del self.agent_urls[agent_id]
            if agent_id in self.agent_cache:
                del self.agent_cache[agent_id]
            # 异步保存配置
            asyncio.create_task(self._save_config())
            logger.info(f"Removed agent: {agent_id}")
            return True
        return False
    
    def is_agent_enabled(self, agent_id: str) -> bool:
        """检查指定Agent是否启用"""
        url_config = self.agent_urls.get(agent_id)
        return url_config.get("enabled", False) if url_config else False
    
    async def get_agent_by_id(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取Agent配置 - 动态获取详细信息"""
        return await self._fetch_agent_info(agent_id)
    
    async def get_agents_by_capability(self, capability: str) -> Dict[str, Any]:
        """根据能力查找Agent - 动态获取并筛选"""
        result = {}
        all_agents = await self.get_enabled_agents()
        
        for agent_id, agent_config in all_agents.items():
            if capability in agent_config.get("capabilities", []):
                result[agent_id] = agent_config
        
        return result
    
    def enable_agent(self, agent_id: str) -> bool:
        """启用Agent"""
        if agent_id in self.agent_urls:
            self.agent_urls[agent_id]['enabled'] = True
            asyncio.create_task(self._save_config())
            # 清除缓存
            if agent_id in self.agent_cache:
                del self.agent_cache[agent_id]
            return True
        return False
    
    def disable_agent(self, agent_id: str) -> bool:
        """禁用Agent"""
        if agent_id in self.agent_urls:
            self.agent_urls[agent_id]['enabled'] = False
            asyncio.create_task(self._save_config())
            # 清除缓存
            if agent_id in self.agent_cache:
                del self.agent_cache[agent_id]
            return True
        return False
    
    def clear_cache(self):
        """清除所有缓存"""
        self.agent_cache.clear()
        logger.info("Cleared agent cache")
    
    def reload_config(self):
        """重新加载配置文件"""
        logger.info("Reloading agent configuration")
        self.agent_cache.clear()  # 清除缓存
        self.config_manager.reload_config()  # 使用配置管理器重新加载
        self._load_config()

# 创建全局注册表实例
_agent_registry = SimpleAgentRegistry()

# 兼容性函数 - 保持向后兼容
def get_enabled_agents():
    """返回启用的Agent配置 - 同步版本"""
    import asyncio
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_agent_registry.get_enabled_agents())

def get_all_agents():
    """返回所有Agent配置 - 同步版本"""
    import asyncio
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_agent_registry.get_all_agents())

def is_agent_enabled(agent_id: str) -> bool:
    """检查指定Agent是否启用"""
    return _agent_registry.is_agent_enabled(agent_id)

def get_agent_by_id(agent_id: str):
    """根据ID获取Agent配置 - 同步版本"""
    import asyncio
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_agent_registry.get_agent_by_id(agent_id))

def get_agents_by_capability(capability: str):
    """根据能力查找Agent - 同步版本"""
    import asyncio
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_agent_registry.get_agents_by_capability(capability))

# 简化的新功能函数
async def add_agent_by_card_url(agent_card_url: str, agent_id: Optional[str] = None) -> bool:
    """通过Agent Card URL添加Agent"""
    return await _agent_registry.add_agent_by_card_url(agent_card_url, agent_id)

async def refresh_agent_info(agent_id: str) -> bool:
    """刷新Agent信息"""
    return await _agent_registry.refresh_agent_info(agent_id)

def remove_agent(agent_id: str) -> bool:
    """移除Agent"""
    return _agent_registry.remove_agent(agent_id)

def get_agent_registry():
    """获取Agent注册表实例"""
    return _agent_registry