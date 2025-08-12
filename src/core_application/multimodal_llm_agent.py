"""
多模态LLM意图识别代理
Multimodal LLM Intent Recognition Agent

负责：
1. 定期读取设备EventStream中的数据
2. 基于设备的system prompt进行意图识别
3. 判断是否需要执行任务
4. 构造丰富上下文的A2A任务请求
5. 发送任务到A2A接口进行分派
"""
import asyncio
import logging
import json
import uuid
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta

from src.core_application.event_stream_manager import event_stream_manager
from src.core_application.terminal_device_manager import terminal_device_manager
from src.data_persistence.terminal_device_models import (
    MultimodalLLMAgent, IntentRecognitionLog, DataType
)
from src.data_persistence.database import DatabaseManager
from src.external_services.llm_service import LLMService
from config.settings import settings


logger = logging.getLogger(__name__)


# 简化的数据条目类，用于Redis Streams数据处理
class StreamData:
    """简化的流数据结构，用于Redis Streams"""
    
    def __init__(self, data: Dict[str, Any]):
        self.entry_id = data.get("entry_id", "")
        self.device_id = data.get("device_id", "")
        self.data_type = data.get("data_type", DataType.TEXT)
        self.content_text = data.get("content_text")
        self.content_json = data.get("content_json")
        self.content_binary = data.get("content_binary")
        self.file_content = data.get("file_content")
        self.metadata = data.get("metadata", {})
        self.mime_type = data.get("mime_type")
        self.created_at = data.get("created_at")
        self.file_path = data.get("file_path")
        self.thumbnail_path = data.get("thumbnail_path")
        self.file_size = data.get("file_size", 0)
    
    @property
    def has_content(self) -> bool:
        """检查是否有内容"""
        return any([
            self.content_text,
            self.content_json,
            self.content_binary,
            self.file_content
        ])
    
    @property
    def is_audio(self) -> bool:
        """是否为音频数据"""
        return self.data_type == DataType.AUDIO
    
    @property
    def is_image(self) -> bool:
        """是否为图片数据"""
        return self.data_type == DataType.IMAGE
    
    @property
    def is_video(self) -> bool:
        """是否为视频数据"""
        return self.data_type == DataType.VIDEO
    
    @property
    def is_text(self) -> bool:
        """是否为文本数据"""
        return self.data_type == DataType.TEXT


class IntentRecognitionAgent:
    """意图识别代理"""
    
    def __init__(self, agent_config: Dict[str, Any]):
        self.agent_id = agent_config["agent_id"]
        self.name = agent_config["name"]
        self.scan_interval_seconds = agent_config.get("scan_interval_seconds", 30)
        self.max_devices_per_scan = agent_config.get("max_devices_per_scan", 10)
        
        # LLM配置
        self.llm_service = LLMService()
        self.llm_provider = agent_config.get("llm_provider", "openai")
        self.llm_model = agent_config.get("llm_model", "gpt-4o")
        self.max_tokens = agent_config.get("max_tokens", 2000)
        self.temperature = agent_config.get("temperature", 0.3)
        
        # 系统提示词
        self.base_system_prompt = agent_config.get("base_system_prompt", self._get_default_system_prompt())
        self.intent_detection_prompt = agent_config.get("intent_detection_prompt", self._get_default_intent_prompt())
        
        # 状态管理
        self.is_running = False
        self.scan_task = None
        self._should_start = False  # 延迟启动标志
        self.db_manager = DatabaseManager()
        
        # 统计信息
        self.total_scans = 0
        self.total_intents_detected = 0
        self.total_tasks_created = 0
        
        logger.info(f"✅ 初始化意图识别代理: {self.agent_id}")
    
    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示词"""
        return """你是一个多模态智能意图识别代理，负责分析终端设备传输的数据并识别用户意图。

你的任务：
1. 分析设备传输的文本、音频、图片、视频、传感器数据
2. 结合设备特性和历史数据判断用户意图
3. 决定是否需要创建任务来响应用户需求
4. 构造详细的任务描述和上下文信息

判断原则：
- 明确的用户请求或指令
- 异常的传感器数据需要处理
- 重要的多媒体内容需要分析
- 紧急情况需要立即响应

**重要：你必须只返回有效的JSON格式响应，不要包含任何其他文本或解释。**

JSON格式要求：
{
  "intent_detected": true/false,
  "intent_type": "意图类型",
  "confidence": 0.0-1.0,
  "reasoning": "判断理由",
  "task_needed": true/false,
  "task_description": "任务描述",
  "task_priority": "low/medium/high/urgent"
}

只返回JSON，不要任何其他内容！"""
    
    def _get_default_intent_prompt(self) -> str:
        """获取默认意图检测提示词"""
        return """基于以下设备数据，分析是否存在需要处理的用户意图：

设备信息：
- 设备ID: {device_id}
- 设备名称: {device_name}
- 设备类型: {device_type}
- 设备位置: {device_location}
- 设备特性: {device_system_prompt}

数据摘要：
时间窗口: {time_window}
数据条目数: {data_count}
数据类型: {data_types}

最近数据内容：
{recent_data_summary}

请分析是否检测到明确的用户意图，并返回严格的JSON格式结果（不要包含markdown代码块或其他格式）：

{{
  "intent_detected": true/false,
  "intent_type": "具体意图类型",
  "confidence": 0.0到1.0的数值,
  "reasoning": "详细分析理由",
  "task_needed": true/false,
  "task_description": "如果需要任务则描述具体任务",
  "task_priority": "low/medium/high/urgent"
}}"""
    
    def start(self):
        """启动意图识别代理 - 延迟创建asyncio任务"""
        if not self.is_running:
            self.is_running = True
            # 不在这里直接创建task，而是标记为待启动
            self._should_start = True
            logger.info(f"✅ 标记意图识别代理启动: {self.agent_id}")
    
    async def _ensure_started(self):
        """确保代理已启动（在有事件循环的情况下）"""
        if self._should_start and self.scan_task is None:
            try:
                self.scan_task = asyncio.create_task(self._scan_loop())
                self._should_start = False
                logger.info(f"✅ 实际启动意图识别代理: {self.agent_id}")
            except RuntimeError as e:
                if "no running event loop" in str(e):
                    logger.debug(f"事件循环未就绪，延迟启动: {self.agent_id}")
                else:
                    raise e
    
    def stop(self):
        """停止意图识别代理"""
        self.is_running = False
        if self.scan_task:
            self.scan_task.cancel()
            logger.info(f"🔴 停止意图识别代理: {self.agent_id}")
    
    async def _scan_loop(self):
        """扫描循环"""
        while self.is_running:
            try:
                await self._perform_scan()
                await asyncio.sleep(self.scan_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 意图识别扫描异常: {e}")
                await asyncio.sleep(10)  # 异常后等待10秒
    
    async def _perform_scan(self):
        """执行扫描"""
        try:
            # 获取活跃设备
            devices = terminal_device_manager.get_all_devices(online_only=True)
            if not devices:
                return
            
            # 限制每次扫描的设备数量
            scan_devices = devices[:self.max_devices_per_scan]
            
            # 并发处理设备
            tasks = [self._analyze_device_data(device) for device in scan_devices]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 统计结果
            intents_detected = sum(1 for r in results if isinstance(r, dict) and r.get("intent_detected"))
            tasks_created = sum(1 for r in results if isinstance(r, dict) and r.get("task_created"))
            
            self.total_scans += 1
            self.total_intents_detected += intents_detected
            self.total_tasks_created += tasks_created
            
            if intents_detected > 0:
                logger.info(f"🎯 扫描完成: 检测到{intents_detected}个意图, 创建{tasks_created}个任务")
            
        except Exception as e:
            logger.error(f"❌ 执行扫描失败: {e}")
    
    async def _analyze_device_data(self, device) -> Dict[str, Any]:
        """分析单个设备的数据"""
        try:
            device_id = device.device_id
            
            # 获取设备的Redis Stream数据
            recent_data_raw = await event_stream_manager.read_stream_data(
                device_id=device_id,
                count=50,  # 最多50条
                block_ms=100  # 100ms超时
            )
            
            if not recent_data_raw:
                return {"intent_detected": False, "device_id": device_id}
            
            # 转换为StreamData对象
            recent_data = [StreamData(data) for data in recent_data_raw]
            
            # 在意图识别前进行音频转录处理
            processed_data = await self._process_audio_transcription(device_id, recent_data)
            
            # 分析数据
            analysis_result = await self._analyze_data_for_intent(device, processed_data)
            
            # 记录分析日志
            await self._log_intent_analysis(device, processed_data, analysis_result)
            
            # 如果检测到意图且需要创建任务
            if analysis_result.get("intent_detected") and analysis_result.get("task_needed"):
                task_created = await self._create_a2a_task(device, processed_data, analysis_result)
                analysis_result["task_created"] = task_created
            else:
                analysis_result["task_created"] = False
            
            return analysis_result
            
        except Exception as e:
            logger.error(f"❌ 分析设备数据失败 {device.device_id}: {e}")
            return {"intent_detected": False, "error": str(e), "device_id": device.device_id}
    
    async def _process_audio_transcription(
        self, 
        device_id: str, 
        data_entries: List[StreamData]
    ) -> List[StreamData]:
        """
        处理音频转录：将音频数据转录为文本，并添加到数据流中
        为未来支持原生多模态模型提供灵活性
        """
        processed_entries = list(data_entries)  # 复制原始数据
        transcription_entries = []
        
        try:
            # 查找未转录的音频数据
            untranscribed_audio = []
            for entry in data_entries:
                if (entry.data_type == DataType.AUDIO and 
                    entry.content_binary and 
                    not self._has_transcription_for_audio(data_entries, entry)):
                    untranscribed_audio.append(entry)
            
            if not untranscribed_audio:
                return processed_entries
            
            logger.info(f"🎵➤📝 开始转录音频: {device_id}, {len(untranscribed_audio)} 个文件")
            
            # 并发转录音频（限制并发数避免资源过载）
            semaphore = asyncio.Semaphore(3)  # 最多3个并发转录
            
            async def transcribe_single_audio(entry: StreamData) -> Optional[StreamData]:
                async with semaphore:
                    try:
                        # 从文件读取音频数据（如果需要）
                        audio_data = entry.content_binary
                        if not audio_data and entry.file_path:
                            with open(entry.file_path, 'rb') as f:
                                audio_data = f.read()
                        
                        if not audio_data:
                            logger.warning(f"⚠️ 音频数据为空: {entry.entry_id}")
                            return None
                        
                        # 获取文件名
                        filename = entry.metadata.get("filename", "audio.wav")
                        
                        # 调用转录服务
                        transcribed_text = await self._transcribe_audio_data(device_id, audio_data, filename)
                        
                        if transcribed_text and transcribed_text.strip():
                            # 创建转录文本条目数据
                            transcription_data = {
                                "entry_id": f"transcription_{entry.entry_id}",
                                "device_id": device_id,
                                "data_type": DataType.TEXT,
                                "content_text": transcribed_text.strip(),
                                "metadata": {
                                    "source": "multimodal_llm_agent_asr",
                                    "original_media_type": "audio",
                                    "original_entry_id": entry.entry_id,
                                    "original_filename": filename,
                                    "transcription_source": "glm-asr",
                                    "audio_file_path": entry.file_path,
                                    "transcribed_at": datetime.utcnow().isoformat()
                                },
                                "created_at": entry.created_at  # 保持原始时间戳
                            }
                            transcription_entry = StreamData(transcription_data)
                            
                            logger.info(f"✅ 音频转录成功: {device_id}, '{transcribed_text[:50]}...'")
                            return transcription_entry
                        else:
                            logger.warning(f"⚠️ 音频转录返回空结果: {device_id}, {filename}")
                            return None
                            
                    except Exception as e:
                        logger.error(f"❌ 转录音频失败 {device_id}: {e}")
                        return None
            
            # 执行并发转录
            transcription_tasks = [transcribe_single_audio(entry) for entry in untranscribed_audio]
            transcription_results = await asyncio.gather(*transcription_tasks, return_exceptions=True)
            
            # 收集成功的转录结果
            for result in transcription_results:
                if isinstance(result, StreamData):
                    transcription_entries.append(result)
                    # 也将转录文本添加到EventStream（用于后续处理）
                    await event_stream_manager.add_data_to_stream(
                        device_id=device_id,
                        data_type=DataType.TEXT,
                        content_text=result.content_text,
                        metadata=result.metadata
                    )
            
            # 将转录结果添加到处理后的数据中
            processed_entries.extend(transcription_entries)
            
            if transcription_entries:
                logger.info(f"🎵➤📝 音频转录完成: {device_id}, 成功转录 {len(transcription_entries)} 个文件")
            
            return processed_entries
            
        except Exception as e:
            logger.error(f"❌ 音频转录处理失败 {device_id}: {e}")
            return processed_entries
    
    def _has_transcription_for_audio(self, data_entries: List[StreamData], audio_entry: StreamData) -> bool:
        """检查音频是否已有对应的转录文本"""
        for entry in data_entries:
            if (entry.data_type == DataType.TEXT and 
                entry.metadata and 
                entry.metadata.get("original_entry_id") == audio_entry.entry_id):
                return True
        return False
    
    async def _transcribe_audio_data(self, device_id: str, audio_data: bytes, filename: str) -> str:
        """转录音频数据为文本"""
        try:
            # 验证音频格式
            if not self._is_valid_audio_format(filename):
                logger.warning(f"⚠️ 不支持的音频格式: {device_id}, {filename}")
                return ""
            
            # 检查数据大小
            if len(audio_data) > 25 * 1024 * 1024:  # 25MB GLM-ASR限制
                logger.warning(f"⚠️ 音频文件过大: {device_id}, {len(audio_data)} bytes")
                return ""
            
            # 调用LLM服务进行转录
            transcribed_text = await asyncio.to_thread(self.llm_service.transcribe_audio, audio_data)
            
            if transcribed_text and transcribed_text.strip():
                logger.debug(f"✅ 音频转录成功: {device_id}, 长度: {len(transcribed_text)} 字符")
                return transcribed_text.strip()
            else:
                logger.debug(f"⚠️ 音频转录返回空结果: {device_id}, {filename}")
                return ""
                
        except Exception as e:
            logger.error(f"❌ 音频转录异常 {device_id}: {e}")
            return ""
    
    def _is_valid_audio_format(self, filename: str) -> bool:
        """检查是否为支持的音频格式"""
        valid_extensions = ['.wav', '.mp3', '.m4a', '.flac']
        return any(filename.lower().endswith(ext) for ext in valid_extensions)
    
    async def _analyze_data_for_intent(
        self, 
        device, 
        recent_data: List[StreamData]
    ) -> Dict[str, Any]:
        """使用LLM分析数据意图（支持重试）"""
        max_retries = 2
        
        for attempt in range(max_retries + 1):
            try:
                # 构造数据摘要
                data_summary = self._create_data_summary(recent_data)
                
                # 构造分析提示词
                analysis_prompt = self.intent_detection_prompt.format(
                    device_id=device.device_id,
                    device_name=device.name,
                    device_type=device.device_type.value,
                    device_location=device.location or "未知",
                    device_system_prompt=device.system_prompt or "通用终端设备",
                    time_window="最近30分钟",
                    data_count=len(recent_data),
                    data_types=list(set(entry.data_type.value for entry in recent_data)),
                    recent_data_summary=data_summary
                )
                
                # 调用LLM进行分析
                # 组合系统提示词和分析提示词
                full_prompt = f"{self.base_system_prompt}\n\n{analysis_prompt}"
                
                # 使用LLMService的generate_response方法
                llm_response = await self.llm_service.generate_response(
                    prompt=full_prompt,
                    context={"device_id": device.device_id, "analysis_type": "intent_detection", "attempt": attempt + 1}
                )
                
                # 解析LLM响应
                result = self._parse_llm_response(llm_response)
                result["device_id"] = device.device_id
                result["llm_attempts"] = attempt + 1
                
                # 检查解析是否成功（非默认响应）
                if result.get("reasoning") != "LLM响应解析失败" and not result.get("reasoning", "").startswith("LLM响应格式无效"):
                    if attempt > 0:
                        logger.info(f"✅ LLM意图分析在第{attempt + 1}次尝试成功")
                    return result
                elif attempt < max_retries:
                    logger.warning(f"⚠️ LLM响应解析失败，尝试第{attempt + 2}次...")
                    await asyncio.sleep(1)  # 短暂延迟后重试
                else:
                    logger.error(f"❌ LLM意图分析在{max_retries + 1}次尝试后仍然失败")
                    return result
                
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"⚠️ LLM意图分析异常，尝试第{attempt + 2}次: {e}")
                    await asyncio.sleep(1)
                else:
                    logger.error(f"❌ LLM意图分析在{max_retries + 1}次尝试后仍然异常: {e}")
                    return {
                        "intent_detected": False,
                        "error": str(e),
                        "device_id": device.device_id,
                        "llm_attempts": attempt + 1
                    }
        
        # 这里不应该到达，但为了安全起见
        return {
            "intent_detected": False,
            "error": "未知错误",
            "device_id": device.device_id,
            "llm_attempts": max_retries + 1
        }
    
    def _create_data_summary(self, data_entries: List[StreamData]) -> str:
        """创建数据摘要"""
        try:
            summary_parts = []
            
            # 按数据类型分组
            type_groups = {}
            for entry in data_entries:
                data_type = entry.data_type.value
                if data_type not in type_groups:
                    type_groups[data_type] = []
                type_groups[data_type].append(entry)
            
            # 为每种类型创建摘要
            for data_type, entries in type_groups.items():
                count = len(entries)
                latest_entry = max(entries, key=lambda x: x.created_at)
                
                if data_type == "text":
                    # 文本数据摘要，区分普通文本和音频转录文本
                    regular_texts = []
                    transcribed_texts = []
                    
                    for entry in entries:
                        if entry.content_text:
                            # 检查是否为音频转录文本
                            metadata = entry.metadata or {}
                            if metadata.get("source") == "multimodal_llm_agent_asr":
                                transcribed_texts.append(entry.content_text[:100])
                            else:
                                regular_texts.append(entry.content_text[:100])
                    
                    # 构建摘要
                    text_summary_parts = []
                    if regular_texts:
                        text_summary_parts.append(f"普通文本({len(regular_texts)}条): {', '.join(regular_texts[-2:])}")
                    if transcribed_texts:
                        text_summary_parts.append(f"语音转录({len(transcribed_texts)}条): {', '.join(transcribed_texts[-2:])}")
                    
                    if text_summary_parts:
                        summary_parts.append(f"文本数据({count}条): {'; '.join(text_summary_parts)}")
                
                elif data_type == "json_data":
                    # JSON数据摘要
                    json_keys = set()
                    sample_data = []
                    for entry in entries[-2:]:  # 最近2条
                        if entry.content_json:
                            json_keys.update(entry.content_json.keys())
                            # 添加简要内容示例
                            if isinstance(entry.content_json, dict):
                                sample_data.append(str(entry.content_json)[:80])
                    
                    summary_parts.append(f"结构化数据({count}条): 字段[{', '.join(list(json_keys)[:5])}], 示例: {'; '.join(sample_data)}")
                
                elif data_type in ["audio", "image", "video"]:
                    # 多媒体数据摘要，包含转录信息
                    total_size = sum(e.size_bytes for e in entries)
                    
                    # 检查音频是否有转录文本
                    transcription_info = ""
                    if data_type == "audio":
                        transcribed_count = 0
                        for entry in entries:
                            metadata = entry.metadata or {}
                            if metadata.get("transcribed_text"):
                                transcribed_count += 1
                        if transcribed_count > 0:
                            transcription_info = f", {transcribed_count}条已转录为文字"
                    
                    summary_parts.append(f"{data_type}数据({count}条): 总大小 {total_size/1024/1024:.2f}MB{transcription_info}")
                
                elif data_type == "binary":
                    # 二进制数据摘要
                    total_size = sum(e.size_bytes for e in entries)
                    summary_parts.append(f"二进制数据({count}条): 总大小 {total_size/1024:.2f}KB")
            
            return "\n".join(summary_parts)
            
        except Exception as e:
            logger.error(f"❌ 创建数据摘要失败: {e}")
            return f"数据摘要创建失败: {str(e)}"
    
    def _parse_llm_response(self, llm_response: str) -> Dict[str, Any]:
        """解析LLM响应，完全信任LLM判断"""
        # 默认返回结果
        default_result = {
            "intent_detected": False,
            "intent_type": "unknown",
            "confidence": 0.0,
            "reasoning": "LLM响应解析失败",
            "task_needed": False,
            "task_description": "",
            "task_priority": "low"
        }
        
        if not llm_response or not llm_response.strip():
            logger.warning("⚠️ LLM返回空响应")
            return default_result
        
        try:
            # 清理响应文本
            cleaned_response = llm_response.strip()
            
            # 方法1: 直接解析JSON
            if cleaned_response.startswith('{') and cleaned_response.endswith('}'):
                try:
                    result = json.loads(cleaned_response)
                    logger.debug("✅ 直接解析JSON成功")
                    return self._validate_response_format(result)
                except json.JSONDecodeError as e:
                    logger.debug(f"直接JSON解析失败: {e}")
            
            # 方法2: 提取markdown代码块中的JSON
            json_patterns = [
                r'```json\s*(\{.*?\})\s*```',
                r'```\s*(\{.*?\})\s*```',
                r'`(\{.*?\})`'
            ]
            
            import re
            for pattern in json_patterns:
                matches = re.findall(pattern, cleaned_response, re.DOTALL)
                for match in matches:
                    try:
                        result = json.loads(match.strip())
                        logger.debug("✅ 从代码块中提取JSON成功")
                        return self._validate_response_format(result)
                    except json.JSONDecodeError:
                        continue
            
            # 方法3: 查找可能的JSON对象
            json_start = cleaned_response.find('{')
            json_end = cleaned_response.rfind('}')
            
            if json_start != -1 and json_end != -1 and json_end > json_start:
                json_candidate = cleaned_response[json_start:json_end + 1]
                try:
                    result = json.loads(json_candidate)
                    logger.debug("✅ 提取JSON对象成功")
                    return self._validate_response_format(result)
                except json.JSONDecodeError:
                    pass
            
            # 如果所有方法都失败，记录原始响应并返回默认值
            logger.warning(f"⚠️ 无法解析LLM响应为JSON: {cleaned_response[:200]}...")
            default_result["reasoning"] = f"LLM响应格式无效: {cleaned_response[:100]}..."
            return default_result
            
        except Exception as e:
            logger.error(f"❌ 解析LLM响应时发生异常: {e}")
            default_result["reasoning"] = f"解析异常: {str(e)}"
            return default_result
    
    def _validate_response_format(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """验证并标准化响应格式"""
        validated = {
            "intent_detected": bool(response.get("intent_detected", False)),
            "intent_type": str(response.get("intent_type", "unknown")),
            "confidence": max(0.0, min(1.0, float(response.get("confidence", 0.0)))),
            "reasoning": str(response.get("reasoning", "")),
            "task_needed": bool(response.get("task_needed", False)),
            "task_description": str(response.get("task_description", "")),
            "task_priority": str(response.get("task_priority", "low"))
        }
        
        # 验证task_priority值
        valid_priorities = ["low", "medium", "high", "urgent"]
        if validated["task_priority"] not in valid_priorities:
            validated["task_priority"] = "low"
        
        return validated
    
    async def _log_intent_analysis(
        self, 
        device, 
        recent_data: List[StreamData], 
        analysis_result: Dict[str, Any]
    ):
        """记录意图分析日志"""
        try:
            with self.db_manager.create_session() as db:
                log_entry = IntentRecognitionLog(
                    device_id=device.device_id,
                    log_id=str(uuid.uuid4()),
                    input_data_summary=self._create_data_summary(recent_data),
                    data_count=len(recent_data),
                    data_types=[entry.data_type.value for entry in recent_data],
                    time_window_start=min(entry.created_at for entry in recent_data) if recent_data else datetime.utcnow(),
                    time_window_end=max(entry.created_at for entry in recent_data) if recent_data else datetime.utcnow(),
                    intent_detected=analysis_result.get("intent_detected", False),
                    intent_type=analysis_result.get("intent_type"),
                    confidence_score=analysis_result.get("confidence", 0.0),
                    reasoning=analysis_result.get("reasoning", ""),
                    task_created=analysis_result.get("task_created", False),
                    task_id=analysis_result.get("task_id"),
                    task_description=analysis_result.get("task_description", ""),
                    a2a_request_data=analysis_result.get("a2a_request")
                )
                
                db.add(log_entry)
                db.commit()
                
        except Exception as e:
            logger.error(f"❌ 记录意图分析日志失败: {e}")
    
    async def _create_a2a_task(
        self, 
        device, 
        recent_data: List[StreamData], 
        analysis_result: Dict[str, Any]
    ) -> bool:
        """创建A2A任务"""
        try:
            # 构造丰富的上下文信息
            context = {
                "device_info": {
                    "device_id": device.device_id,
                    "name": device.name,
                    "type": device.device_type.value,
                    "location": device.location,
                    "capabilities": device.mcp_capabilities,
                    "system_prompt": device.system_prompt
                },
                "intent_analysis": {
                    "intent_type": analysis_result.get("intent_type"),
                    "confidence": analysis_result.get("confidence"),
                    "reasoning": analysis_result.get("reasoning"),
                    "priority": analysis_result.get("task_priority", "medium")
                },
                "data_context": {
                    "time_window": "最近30分钟",
                    "data_count": len(recent_data),
                    "data_types": list(set(entry.data_type.value for entry in recent_data)),
                    "data_summary": self._create_data_summary(recent_data)
                },
                "task_requirements": {
                    "description": analysis_result.get("task_description", ""),
                    "urgency": analysis_result.get("task_priority", "medium"),
                    "expected_capabilities": self._extract_required_capabilities(analysis_result)
                }
            }
            
            # 构造A2A请求
            task_id = str(uuid.uuid4())
            a2a_request = {
                "jsonrpc": "2.0",
                "method": "message/send",
                "id": task_id,
                "params": {
                    "message": {
                        "messageId": task_id,
                        "role": "user",
                        "parts": [
                            {
                                "kind": "text",
                                "text": self._construct_task_message(device, analysis_result, context)
                            }
                        ]
                    },
                    "configuration": {
                        "source": "intent_recognition_agent",
                        "device_id": device.device_id,
                        "intent_type": analysis_result.get("intent_type"),
                        "priority": analysis_result.get("task_priority", "medium"),
                        "context": context
                    }
                }
            }
            
            # 发送到A2A接口
            success = await self._send_a2a_request(a2a_request)
            
            if success:
                analysis_result["task_id"] = task_id
                analysis_result["a2a_request"] = a2a_request
                logger.info(f"✅ 创建A2A任务: {device.device_id} -> {task_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ 创建A2A任务失败: {e}")
            return False
    
    def _extract_required_capabilities(self, analysis_result: Dict[str, Any]) -> List[str]:
        """提取所需能力"""
        # 根据意图类型推断所需能力
        intent_type = analysis_result.get("intent_type", "").lower()
        
        if "分析" in intent_type or "analysis" in intent_type:
            return ["data_analysis", "ai_inference"]
        elif "控制" in intent_type or "control" in intent_type:
            return ["device_control", "system_monitoring"]
        elif "处理" in intent_type or "process" in intent_type:
            return ["data_processing", "file_operations"]
        elif "通信" in intent_type or "communication" in intent_type:
            return ["communication", "message_handling"]
        else:
            return ["general_assistance"]
    
    def _construct_task_message(
        self, 
        device, 
        analysis_result: Dict[str, Any], 
        context: Dict[str, Any]
    ) -> str:
        """构造任务消息"""
        return f"""基于终端设备 {device.name} (ID: {device.device_id}) 的数据分析，检测到以下用户意图：

意图类型: {analysis_result.get('intent_type', '未知')}
置信度: {analysis_result.get('confidence', 0.0):.2f}
优先级: {analysis_result.get('task_priority', 'medium')}

任务描述: {analysis_result.get('task_description', '处理设备数据并提供相应服务')}

设备上下文:
- 设备类型: {device.device_type.value}
- 设备位置: {device.location or '未知'}
- 设备能力: {', '.join(device.mcp_capabilities)}

数据概览:
- 时间窗口: 最近30分钟
- 数据条目: {context['data_context']['data_count']} 条
- 数据类型: {', '.join(context['data_context']['data_types'])}

分析推理: {analysis_result.get('reasoning', '基于设备数据模式分析')}

请根据以上信息确定合适的处理方案并执行相应任务。"""
    
    async def _send_a2a_request(self, a2a_request: Dict[str, Any]) -> bool:
        """发送A2A请求"""
        try:
            # 导入A2A主端点处理函数
            from src.user_interaction.main_simple import a2a_main_endpoint
            
            # 发送请求
            response = await a2a_main_endpoint(a2a_request)
            
            # 检查响应
            if response.get("jsonrpc") == "2.0" and "result" in response:
                logger.info(f"✅ A2A任务发送成功: {a2a_request['id']}")
                return True
            else:
                logger.error(f"❌ A2A任务发送失败: {response}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 发送A2A请求异常: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "is_running": self.is_running,
            "scan_interval_seconds": self.scan_interval_seconds,
            "total_scans": self.total_scans,
            "total_intents_detected": self.total_intents_detected,
            "total_tasks_created": self.total_tasks_created,
            "detection_rate": self.total_intents_detected / max(self.total_scans, 1),
            "task_creation_rate": self.total_tasks_created / max(self.total_intents_detected, 1)
        }


class MultimodalLLMAgentManager:
    """多模态LLM代理管理器"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.agents: Dict[str, IntentRecognitionAgent] = {}
        self._initialize_default_agent()
    
    def _initialize_default_agent(self):
        """初始化默认代理"""
        default_config = {
            "agent_id": "default_intent_agent",
            "name": "默认意图识别代理",
            "scan_interval_seconds": 30,
            "max_devices_per_scan": 10,
            "llm_provider": "openai",
            "llm_model": "gpt-4o",
            "max_tokens": 2000,
            "temperature": 0.3
        }
        
        agent = IntentRecognitionAgent(default_config)
        self.agents[default_config["agent_id"]] = agent
        
        # 不在模块导入时启动，而是等待事件循环就绪
        logger.info(f"🔄 创建默认意图识别代理: {default_config['agent_id']}，等待启动")
    
    def get_agent(self, agent_id: str) -> Optional[IntentRecognitionAgent]:
        """获取代理"""
        return self.agents.get(agent_id)
    
    def get_all_agents(self) -> Dict[str, IntentRecognitionAgent]:
        """获取所有代理"""
        return self.agents.copy()
    
    async def start_all_agents(self):
        """启动所有代理 - 确保在事件循环中启动"""
        for agent in self.agents.values():
            agent.start()  # 标记为启动
            await agent._ensure_started()  # 确保实际启动
        logger.info(f"✅ 启动了 {len(self.agents)} 个意图识别代理")
    
    async def stop_all_agents(self):
        """停止所有代理"""
        for agent in self.agents.values():
            agent.stop()
        
        # 等待所有任务停止
        tasks_to_wait = [agent.scan_task for agent in self.agents.values() if agent.scan_task]
        if tasks_to_wait:
            try:
                await asyncio.gather(*tasks_to_wait, return_exceptions=True)
            except Exception as e:
                logger.warning(f"停止代理任务时出现异常: {e}")
        
        logger.info(f"🔴 停止了 {len(self.agents)} 个意图识别代理")
    
    def get_overall_statistics(self) -> Dict[str, Any]:
        """获取整体统计"""
        total_scans = sum(agent.total_scans for agent in self.agents.values())
        total_intents = sum(agent.total_intents_detected for agent in self.agents.values())
        total_tasks = sum(agent.total_tasks_created for agent in self.agents.values())
        
        return {
            "active_agents": len([a for a in self.agents.values() if a.is_running]),
            "total_agents": len(self.agents),
            "total_scans": total_scans,
            "total_intents_detected": total_intents,
            "total_tasks_created": total_tasks,
            "overall_detection_rate": total_intents / max(total_scans, 1),
            "overall_task_rate": total_tasks / max(total_intents, 1),
            "agent_details": {
                agent_id: agent.get_statistics()
                for agent_id, agent in self.agents.items()
            }
        }


# 全局实例
multimodal_llm_agent_manager = MultimodalLLMAgentManager()
