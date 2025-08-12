"""
LLM Service Integration - 精简版
支持OpenAI和智谱AI（ZAI）GLM模型 - 使用zai-sdk
"""
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod
import openai
import json
from config.settings import settings
import logging

# 智谱AI zai-sdk
try:
    from zai import ZhipuAiClient
    import zai.core
    ZAI_SDK_AVAILABLE = True
except ImportError:
    ZAI_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """LLM提供者抽象基类"""
    
    @abstractmethod
    async def generate_response(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        pass
    
    @abstractmethod
    async def analyze_intent(self, user_input: str) -> Dict[str, Any]:
        pass
    
    def _get_intent_prompt(self, user_input: str) -> str:
        """通用意图分析提示词"""
        return f'''分析以下用户输入的意图，返回JSON格式：
{{"intent": "chat|simple_command|complex_task", "task_type": "", "parameters": {{}}, "confidence": 0.95, "requires_agent": false}}

用户输入: {user_input}'''
    
    def _safe_parse_json(self, text: str) -> Dict[str, Any]:
        """安全解析JSON响应"""
        try:
            return json.loads(text)
        except:
            return {"intent": "chat", "task_type": None, "parameters": {}, "confidence": 0.5, "requires_agent": False}


class OpenAIProvider(LLMProvider):
    """OpenAI GPT服务提供者"""
    
    def __init__(self, api_key: str = None):
        self.client = openai.AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        # 读取集中配置的模型
        self.chat_model, self.intent_model = settings.get_openai_models()
        logger.info(f"OpenAI models configured - chat: {self.chat_model}, intent: {self.intent_model}")
    
    async def generate_response(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        try:
            messages = [{"role": "system", "content": "你是一个智能的A2A Agent助手。"}, {"role": "user", "content": prompt}]
            if context:
                messages.insert(1, {"role": "system", "content": f"上下文信息: {context}"})
            
            response = await self.client.chat.completions.create(
                model=self.chat_model, messages=messages, max_tokens=1000, temperature=0.7
            )
            
            # 检查响应内容
            if response and response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                if content and content.strip():
                    return content.strip()
                else:
                    logger.warning("OpenAI returned empty response content")
                    return "我收到了您的消息，但生成的回复为空。请尝试重新描述您的问题。"
            else:
                logger.warning("OpenAI returned no choices in response")
                return "抱歉，服务返回了异常响应。"
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return "抱歉，我暂时无法处理您的请求。"
    
    async def analyze_intent(self, user_input: str) -> Dict[str, Any]:
        try:
            response = await self.client.chat.completions.create(
                model=self.intent_model, 
                messages=[{"role": "user", "content": self._get_intent_prompt(user_input)}],
                max_tokens=200, temperature=0.3
            )
            return self._safe_parse_json(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"OpenAI intent analysis error: {e}")
            return self._safe_parse_json("")


class ZhipuAIProvider(LLMProvider):
    """智谱AI GLM服务提供者 - 使用zai-sdk"""
    
    def __init__(self, api_key: str = None):
        if not ZAI_SDK_AVAILABLE:
            raise ImportError("zai-sdk not available. Install with: pip install zai-sdk")
        
        self.client = ZhipuAiClient(api_key=api_key or settings.zhipu_api_key)
    
    async def generate_response(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> str:
        try:
            messages = [{"role": "system", "content": "你是一个智能的A2A Agent助手。"}, {"role": "user", "content": prompt}]
            if context:
                messages.insert(1, {"role": "system", "content": f"上下文信息: {context}"})
            
            # ZhipuAI zai-sdk 客户端是同步的，不需要await
            response = self.client.chat.completions.create(
                model="glm-4.5-x",
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            
            # 提取响应内容
            if response and response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                if content and content.strip():
                    return content.strip()
                else:
                    logger.warning("ZhipuAI returned empty response content")
                    return "我收到了您的消息，但生成的回复为空。请尝试重新描述您的问题。"
            else:
                logger.warning("ZhipuAI returned no choices in response")
                return "抱歉，服务返回了异常响应。"
            
        except Exception as e:
            if "zai.core" in str(type(e)):
                if "APIStatusError" in str(type(e)):
                    logger.error(f"ZhipuAI API status error: {e}")
                    return "抱歉，API服务暂时不可用。"
                elif "APITimeoutError" in str(type(e)):
                    logger.error(f"ZhipuAI API timeout: {e}")
                    return "抱歉，请求超时，请稍后重试。"
                else:
                    logger.error(f"ZhipuAI API error: {e}")
                    return "抱歉，API调用失败。"
            else:
                logger.error(f"ZhipuAI unexpected error: {e}")
                return "抱歉，我暂时无法处理您的请求。"
    
    async def analyze_intent(self, user_input: str) -> Dict[str, Any]:
        try:
            messages = [
                {"role": "system", "content": "你是一个意图分析专家，只返回有效的JSON格式。"},
                {"role": "user", "content": self._get_intent_prompt(user_input)}
            ]
            
            response = self.client.chat.completions.create(
                model="glm-4",
                messages=messages,
                max_tokens=200,
                temperature=0.3
            )
            return self._safe_parse_json(response.choices[0].message.content)
            
        except zai.core.APIStatusError as e:
            logger.error(f"ZhipuAI intent analysis API status error: {e}")
            return self._safe_parse_json("")
        except zai.core.APITimeoutError as e:
            logger.error(f"ZhipuAI intent analysis timeout: {e}")
            return self._safe_parse_json("")
        except Exception as e:
            logger.error(f"ZhipuAI intent analysis error: {e}")
            return self._safe_parse_json("")
    
    def transcribe_audio(self, audio_data: bytes) -> str:
        """使用GLM-ASR转换音频为文字（同步方法）"""
        try:
            import io
            
            # 创建音频文件对象
            audio_file = io.BytesIO(audio_data)
            
            response = self.client.audio.transcriptions.create(
                model="glm-asr",
                file=audio_file,
                stream=True
            )
            
            # 收集所有转录文本
            transcribed_text = ""
            for chunk in response:
                if chunk.type == "transcript.text.delta":
                    transcribed_text += chunk.delta
            
            logger.info(f"🎵 音频转文字成功，长度: {len(transcribed_text)} 字符")
            return transcribed_text.strip()
            
        except zai.core.APIStatusError as e:
            logger.error(f"ZhipuAI ASR API status error: {e}")
            return ""
        except zai.core.APITimeoutError as e:
            logger.error(f"ZhipuAI ASR timeout: {e}")
            return ""
        except Exception as e:
            logger.error(f"ZhipuAI ASR error: {e}")
            return ""


class LLMService:
    """LLM服务管理器 - 精简版"""
    
    def __init__(self):
        self.providers = {}
        logger.info("🔧 Initializing LLM Service...")
        
        # 打印调试信息
        logger.info(f"📊 OpenAI API Key: {'✅ Set' if settings.openai_api_key else '❌ Not Set'}")
        logger.info(f"📊 Zhipu API Key: {'✅ Set' if settings.zhipu_api_key else '❌ Not Set'}")
        logger.info(f"📊 ZAI SDK Available: {'✅ Yes' if ZAI_SDK_AVAILABLE else '❌ No'}")
        
        # 初始化OpenAI
        if settings.openai_api_key:
            try:
                self.providers['openai'] = OpenAIProvider()
                logger.info("✅ OpenAI Provider initialized")
            except Exception as e:
                logger.error(f"❌ OpenAI Provider initialization failed: {e}")
        else:
            logger.warning("⚠️ OpenAI API key not set")
        
        # 初始化智谱AI（使用zai-sdk）
        if ZAI_SDK_AVAILABLE and hasattr(settings, 'zhipu_api_key') and settings.zhipu_api_key:
            try:
                self.providers['zhipu'] = ZhipuAIProvider()
                logger.info("✅ ZhipuAI Provider initialized (zai-sdk)")
            except Exception as e:
                logger.error(f"❌ ZhipuAI Provider initialization failed: {e}")
        elif not ZAI_SDK_AVAILABLE:
            logger.warning("⚠️ zai-sdk not available. Install with: pip install zai-sdk")
        elif not settings.zhipu_api_key:
            logger.warning("⚠️ Zhipu API key not set")
        
        if not self.providers:
            logger.warning("⚠️ No LLM providers available - chat will use fallback responses")
        else:
            provider_names = list(self.providers.keys())
            logger.info(f"✅ LLM Service initialized with providers: {provider_names}")
    
    def get_provider(self, provider_name: str = None) -> LLMProvider:
        """获取LLM提供者"""
        if provider_name and provider_name in self.providers:
            return self.providers[provider_name]
        # 优先智谱AI
        for name in ['zhipu', 'openai']:
            if name in self.providers:
                return self.providers[name]
        raise ValueError("No LLM provider available")
    
    async def generate_response(self, prompt: str, context: Optional[Dict[str, Any]] = None, provider: str = None) -> str:
        """生成响应"""
        try:
            logger.info(f"🤖 LLM generating response for: '{prompt[:50]}...'")
            selected_provider = self.get_provider(provider)
            logger.info(f"🔧 Using LLM provider: {type(selected_provider).__name__}")
            
            result = await selected_provider.generate_response(prompt, context)
            logger.info(f"✅ LLM response generated: '{result[:100]}...'")
            return result
        except Exception as e:
            logger.error(f"❌ LLM response failed: {e}")
            return f"抱歉，我暂时无法处理您的请求。错误：{str(e)[:100]}"
    
    async def analyze_intent(self, user_input: str, provider: str = None) -> Dict[str, Any]:
        """分析用户意图"""
        try:
            return await self.get_provider(provider).analyze_intent(user_input)
        except Exception as e:
            logger.error(f"Intent analysis failed: {e}")
            return {"intent": "chat", "task_type": None, "parameters": {}, "confidence": 0.5, "requires_agent": False}
    
    def transcribe_audio(self, audio_data: bytes, provider: str = None) -> str:
        """音频转文字（仅支持ZhipuAI GLM-ASR）"""
        try:
            # 优先使用ZhipuAI，因为只有它支持ASR
            if 'zhipu' in self.providers:
                provider_instance = self.providers['zhipu']
                if hasattr(provider_instance, 'transcribe_audio'):
                    logger.info(f"🎵 使用 ZhipuAI GLM-ASR 转录音频，大小: {len(audio_data)} bytes")
                    result = provider_instance.transcribe_audio(audio_data)
                    logger.info(f"✅ 音频转录完成: '{result[:50]}...'")
                    return result
                else:
                    logger.error("❌ ZhipuAI provider不支持音频转录")
                    return ""
            else:
                logger.error("❌ 没有可用的音频转录服务（需要ZhipuAI）")
                return ""
        except Exception as e:
            logger.error(f"❌ 音频转录失败: {e}")
            return ""
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        return {
            "available_providers": list(self.providers.keys()),
            "zai_sdk_available": ZAI_SDK_AVAILABLE,
            "provider_count": len(self.providers)
        }
