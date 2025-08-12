"""
统一配置文件管理器
用于管理Agent Card和Agent Registry等JSON配置文件
"""
import json
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ConfigManager:
    """通用配置文件管理器"""
    
    def __init__(self, config_file: str, config_name: str = "Config"):
        self.config_file = config_file
        self.config_name = config_name
        self._cached_data: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None
        
    def get_config_path(self) -> str:
        """获取配置文件的绝对路径"""
        if os.path.isabs(self.config_file):
            return self.config_file
        
        # 从项目根目录开始查找
        current_dir = os.path.dirname(os.path.abspath(__file__))
        while current_dir != os.path.dirname(current_dir):  # 直到根目录
            config_path = os.path.join(current_dir, self.config_file)
            if os.path.exists(config_path):
                return config_path
            current_dir = os.path.dirname(current_dir)
        
        # 如果没找到，返回相对于当前模块的路径
        module_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        return os.path.join(module_dir, self.config_file)
    
    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """加载配置文件"""
        config_path = self.get_config_path()
        
        # 检查缓存
        if not force_reload and self._cached_data and self._cache_timestamp:
            if os.path.exists(config_path):
                file_mtime = datetime.fromtimestamp(os.path.getmtime(config_path))
                if file_mtime <= self._cache_timestamp:
                    return self._cached_data
        
        logger.info(f"Loading {self.config_name} from: {config_path}")
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"{self.config_name} file not found: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # 更新缓存
        self._cached_data = config_data
        self._cache_timestamp = datetime.now()
        
        logger.info(f"✅ {self.config_name} loaded successfully")
        return config_data
    
    def save_config(self, config_data: Dict[str, Any]) -> None:
        """保存配置文件"""
        config_path = self.get_config_path()
        
        # 确保目录存在
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        # 更新缓存
        self._cached_data = config_data
        self._cache_timestamp = datetime.now()
        
        logger.info(f"✅ {self.config_name} saved successfully")
    
    def reload_config(self) -> Dict[str, Any]:
        """强制重新加载配置"""
        return self.load_config(force_reload=True)


class AgentCardManager(ConfigManager):
    """Agent Card配置管理器"""
    
    def __init__(self):
        super().__init__("config/agent_card.json", "Agent Card")
    
    def load_a2a_agent_card(self, force_reload: bool = False):
        """加载并转换为A2A SDK的AgentCard对象"""
        try:
            from a2a.types import AgentCard, AgentCapabilities, AgentSkill, AgentProvider
        except ImportError:
            logger.error("A2A SDK not available")
            raise ImportError("A2A SDK not available")
        
        config_data = self.load_config(force_reload)
        
        # 验证必需字段 - 根据A2A SDK的实际要求
        required_fields = [
            "name", "description", "version", "protocolVersion", "url", 
            "preferredTransport", "defaultInputModes", "defaultOutputModes", 
            "capabilities", "skills"
        ]
        for field in required_fields:
            if field not in config_data:
                raise ValueError(f"Required field '{field}' missing in Agent Card config")
        
        # 验证capabilities字段的结构
        capabilities_data = config_data["capabilities"]
        if not isinstance(capabilities_data, dict):
            raise ValueError("capabilities must be an object")
        
        # 处理additionalInterfaces
        additional_interfaces = []
        for interface in config_data.get("additionalInterfaces", []):
            if "url" not in interface or "transport" not in interface:
                raise ValueError("additionalInterfaces items must have 'url' and 'transport' fields")
            additional_interfaces.append({
                "url": interface["url"],
                "transport": interface["transport"]
            })
        
        # 处理skills
        skills = []
        for skill_data in config_data.get("skills", []):
            required_skill_fields = ["id", "name", "description"]
            for field in required_skill_fields:
                if field not in skill_data:
                    raise ValueError(f"Required skill field '{field}' missing in skills config")
            
            skill = AgentSkill(
                id=skill_data["id"],
                name=skill_data["name"],
                description=skill_data["description"],
                tags=skill_data.get("tags", []),
                examples=skill_data.get("examples", [])
            )
            skills.append(skill)
        
        # 验证provider字段（如果存在）
        provider_data = config_data.get("provider", {})
        if provider_data:
            if "organization" not in provider_data:
                raise ValueError("provider.organization is required when provider is specified")
            if "url" not in provider_data:
                raise ValueError("provider.url is required when provider is specified")
        
        # 创建Agent Card - 严格使用配置文件中的值
        # 注意：A2A SDK使用下划线式字段名，而配置文件使用驼峰式
        agent_card = AgentCard(
            name=config_data["name"],
            description=config_data["description"],
            version=config_data["version"],
            protocol_version=config_data["protocolVersion"],  # 配置文件用驼峰式，SDK用下划线式
            url=config_data["url"],
            preferred_transport=config_data["preferredTransport"],
            additional_interfaces=additional_interfaces if additional_interfaces else None,
            default_input_modes=config_data["defaultInputModes"],
            default_output_modes=config_data["defaultOutputModes"],
            provider=AgentProvider(
                organization=provider_data["organization"],
                url=provider_data["url"]
            ) if provider_data else None,
            capabilities=AgentCapabilities(
                streaming=capabilities_data.get("streaming", False),
                push_notifications=capabilities_data.get("pushNotifications", False),
                state_transition_history=capabilities_data.get("stateTransitionHistory", False),
                extensions=capabilities_data.get("extensions", [])
            ),
            skills=skills
        )
        
        logger.info("✅ A2A Agent Card created successfully from config")
        return agent_card


class AgentRegistryManager(ConfigManager):
    """Agent Registry配置管理器"""
    
    def __init__(self):
        super().__init__("config/agents.json", "Agent Registry")
        
    def create_empty_config(self) -> Dict[str, Any]:
        """创建空的Agent Registry配置"""
        empty_config = {"agents": []}
        self.save_config(empty_config)
        return empty_config
    
    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """加载Agent Registry配置，如果不存在则创建空配置"""
        try:
            return super().load_config(force_reload)
        except FileNotFoundError:
            logger.warning("⚠️ No agent registry config file found, creating empty one")
            return self.create_empty_config()


# 全局实例
_agent_card_manager = AgentCardManager()
_agent_registry_manager = AgentRegistryManager()

def get_agent_card_manager() -> AgentCardManager:
    """获取Agent Card管理器实例"""
    return _agent_card_manager

def get_agent_registry_manager() -> AgentRegistryManager:
    """获取Agent Registry管理器实例"""
    return _agent_registry_manager

# Agent Card 便捷函数
def load_agent_card_config(force_reload: bool = False) -> Dict[str, Any]:
    """便捷函数：加载Agent Card配置（字典格式）"""
    return _agent_card_manager.load_config(force_reload)

def load_a2a_agent_card(force_reload: bool = False):
    """便捷函数：加载Agent Card配置（A2A SDK对象）"""
    return _agent_card_manager.load_a2a_agent_card(force_reload)

def reload_agent_card_config() -> Dict[str, Any]:
    """便捷函数：重新加载Agent Card配置"""
    return _agent_card_manager.reload_config()

# Agent Registry 便捷函数
def load_agent_registry_config(force_reload: bool = False) -> Dict[str, Any]:
    """便捷函数：加载Agent Registry配置"""
    return _agent_registry_manager.load_config(force_reload)

def save_agent_registry_config(config_data: Dict[str, Any]) -> None:
    """便捷函数：保存Agent Registry配置"""
    return _agent_registry_manager.save_config(config_data)
