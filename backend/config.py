import yaml
from typing import Dict, Any
from pathlib import Path

from backend.personal_storage import (
    EXAMPLE_CONFIG_PATH,
    PERSONAL_CONFIG_PATH,
    PERSONAL_CUSTOM_PROMPT_WORDS_PATH,
    PERSONAL_PROMPTS_DIR,
    ROOT_CONFIG_PATH,
    LEGACY_CUSTOM_PROMPT_WORDS_PATH,
    ensure_personal_dirs,
)
from backend.utils.config_sanitizer import sanitize_adapters_config


class Config:
    """配置管理类"""

    PROMPT_FILES = {
        "system_prompt": "system_prompt.md",
        "system_rules": "system_rules.md",
        "roleplay_prompt": "roleplay_prompt.md",
    }
    
    def __init__(self, config_path: str | None = None):
        self.config_path = Path(config_path) if config_path else PERSONAL_CONFIG_PATH
        if not self.config_path.is_absolute():
            project_root = Path(__file__).parent.parent
            self.config_path = project_root / self.config_path
        self.example_config_path = EXAMPLE_CONFIG_PATH
        self._ensure_config_file()
        self._config = self._load_config()
        self._ensure_prompt_files()
        self._ensure_personal_asset_paths()

    def _ensure_config_file(self) -> None:
        """确保个人版运行时配置文件存在。

        个人版后续只读写 data/personal/config.yaml。首次启动时优先从根目录
        config.yaml 初始化；如果根目录也没有，则使用 config.example.yaml。
        """
        ensure_personal_dirs()
        if self.config_path.exists():
            return

        source_path = ROOT_CONFIG_PATH if ROOT_CONFIG_PATH.exists() else self.example_config_path
        if source_path.exists():
            data = self._load_yaml_file(source_path)
            if "adapters" in data:
                data["adapters"] = sanitize_adapters_config(data["adapters"])
            self._save_yaml_file(self.config_path, data)
            return

        raise FileNotFoundError(
            f"配置文件未找到: {self.config_path}，且缺少示例文件: {self.example_config_path}"
        )

    @staticmethod
    def _load_yaml_file(path: Path) -> Dict[str, Any]:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}

    @staticmethod
    def _save_yaml_file(path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data or {}, f, default_flow_style=False, allow_unicode=True)

    def _prompt_path(self, key: str) -> Path:
        filename = self.PROMPT_FILES[key]
        return PERSONAL_PROMPTS_DIR / filename

    def _ensure_prompt_files(self) -> None:
        changed = False
        for key in self.PROMPT_FILES:
            value = self._config.get(key)
            if isinstance(value, str) and value.strip():
                prompt_path = self._prompt_path(key)
                if not prompt_path.exists():
                    prompt_path.write_text(value.strip(), encoding="utf-8")
            if key in self._config:
                self._config.pop(key, None)
                changed = True
        if changed:
            self._save_config()

    def _ensure_personal_asset_paths(self) -> None:
        changed = False
        enhancer_cfg = self._config.get("prompt_enhancer")
        if isinstance(enhancer_cfg, dict):
            custom_path = enhancer_cfg.get("custom_word_bank_path")
            if custom_path in (None, "", "data/custom_prompt_words.yaml"):
                enhancer_cfg["custom_word_bank_path"] = "data/personal/custom_prompt_words.yaml"
                changed = True
            if (
                LEGACY_CUSTOM_PROMPT_WORDS_PATH.exists()
                and not PERSONAL_CUSTOM_PROMPT_WORDS_PATH.exists()
            ):
                PERSONAL_CUSTOM_PROMPT_WORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
                LEGACY_CUSTOM_PROMPT_WORDS_PATH.replace(PERSONAL_CUSTOM_PROMPT_WORDS_PATH)

        if changed:
            self._save_config()

    def get_prompt_value(self, key: str, default: str = "") -> str:
        if key not in self.PROMPT_FILES:
            return default
        prompt_path = self._prompt_path(key)
        if not prompt_path.exists():
            return default
        try:
            return prompt_path.read_text(encoding="utf-8").strip()
        except Exception:
            return default

    def set_prompt_value(self, key: str, value: str) -> None:
        if key not in self.PROMPT_FILES:
            raise KeyError(f"未知提示词配置: {key}")
        prompt_path = self._prompt_path(key)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(value or "", encoding="utf-8")

    def delete_prompt_value(self, key: str) -> None:
        if key not in self.PROMPT_FILES:
            raise KeyError(f"未知提示词配置: {key}")
        prompt_path = self._prompt_path(key)
        if prompt_path.exists():
            prompt_path.unlink()

    def get_prompt_updated_at(self, key: str) -> str | None:
        if key not in self.PROMPT_FILES:
            return None
        prompt_path = self._prompt_path(key)
        if not prompt_path.exists():
            return None
        try:
            from datetime import datetime

            return datetime.fromtimestamp(prompt_path.stat().st_mtime).isoformat()
        except Exception:
            return None

    def as_dict(self, include_prompts: bool = False) -> Dict[str, Any]:
        data = dict(self._config)
        if "adapters" in data:
            data["adapters"] = sanitize_adapters_config(data["adapters"])
        if include_prompts:
            data["system_prompt"] = self.system_prompt
            data["system_rules"] = self.system_rules
            data["roleplay_prompt"] = self.get("roleplay_prompt", "")
        return data
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            return self._load_yaml_file(self.config_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"配置文件未找到: {self.config_path}")
        except yaml.YAMLError as e:
            raise ValueError(f"配置文件格式错误: {e}")
    
    @property
    def llm_config(self) -> Dict[str, Any]:
        """获取LLM配置"""
        return self._config.get('llm', {})
    
    @property
    def system_prompt(self) -> str:
        """获取系统提示词（人设层）"""
        return self.get_prompt_value("system_prompt", "")

    @property
    def system_rules(self) -> str:
        """获取功能协议层提示词（视觉/语音/委派等协议，与人设分离）"""
        return self.get_prompt_value("system_rules", '')
    
    @property
    def adapters_config(self) -> Dict[str, Any]:
        """获取适配器配置"""
        return sanitize_adapters_config(self._config.get('adapters', {}))
    
    @property
    def server_config(self) -> Dict[str, Any]:
        """获取服务器配置"""
        return self._config.get('server', {})
    
    @property
    def tts_config(self) -> Dict[str, Any]:
        """获取TTS配置"""
        return self._config.get('tts', {})

    @property
    def voice_gateway_config(self):
        """获取语音网关配置"""
        from backend.voice_gateway.config import VoiceGatewayConfig
        gateway_dict = self._config.get('voice_gateway', {})
        return VoiceGatewayConfig.from_dict(gateway_dict)
    
    @property
    def image_gen_config(self):
        """获取图像生成配置"""
        from backend.image_gen.config import ImageGenerationConfig
        image_gen_dict = self._config.get('image_generation', {})
        return ImageGenerationConfig(**image_gen_dict)

    @property
    def video_gen_config(self):
        """获取视频生成配置"""
        from backend.video_gen.config import VideoGenerationConfig
        video_gen_dict = self._config.get('video_generation', {})
        return VideoGenerationConfig(**video_gen_dict)
    
    @property
    def vision_config(self):
        """获取视觉识别配置"""
        from backend.vision.config import VisionRecognitionConfig
        vision_dict = self._config.get('vision', {})
        return VisionRecognitionConfig(**vision_dict)

    @property
    def prompt_enhancer_config(self):
        """获取提示词增强配置"""
        from backend.prompt_enhancer.config import PromptEnhancerConfig
        enhancer_dict = self._config.get('prompt_enhancer', {})
        return PromptEnhancerConfig(**enhancer_dict)

    @property
    def asr_config(self):
        """获取ASR语音识别配置"""
        from backend.asr.config import ASRConfig
        asr_dict = self._config.get('asr', {})
        return ASRConfig(**asr_dict)

    @property
    def emote_config(self):
        """获取表情包发送配置"""
        from backend.emote.models import EmoteConfig
        emote_dict = self._config.get('emotes', {})
        return EmoteConfig(**emote_dict)

    @property
    def memory_config(self):
        """获取记忆系统配置"""
        from backend.memory.models import MemoryConfig
        # 兼容历史配置：早期版本可能把记忆配置放在 llm.memory 下
        legacy_memory_dict = self._config.get('llm', {}).get('memory', {})
        memory_dict = self._config.get('memory', {})

        merged_memory_dict: Dict[str, Any] = {}
        if isinstance(legacy_memory_dict, dict):
            self._deep_update(merged_memory_dict, legacy_memory_dict)
        if isinstance(memory_dict, dict):
            # 顶层 memory 优先级更高
            self._deep_update(merged_memory_dict, memory_dict)

        memory_dict = merged_memory_dict
        return MemoryConfig(**memory_dict)

    @property
    def agent_delegate_config(self):
        """获取 Agent 委派配置"""
        from backend.agent_delegate.config import AgentDelegateConfig
        delegate_dict = self._config.get('agent_delegate', {})
        return AgentDelegateConfig.from_dict(delegate_dict)

    @property
    def clock_config(self) -> Dict[str, Any]:
        """获取时钟插件相关配置"""
        return self._config.get('clock', {})
    
    @property
    def proactive_chat_config(self) -> Dict[str, Any]:
        """获取主动聊天配置"""
        cerebellum_cfg = self._config.get('cerebellum', {})
        if isinstance(cerebellum_cfg, dict):
            proactive_cfg = cerebellum_cfg.get('proactive_chat')
            if isinstance(proactive_cfg, dict):
                return proactive_cfg
        return self._config.get('proactive_chat', {})

    @property
    def qq_access_control_config(self) -> Dict[str, Any]:
        """获取 QQ 访问控制配置"""
        qq_config = self._config.get('adapters', {}).get('qq', {})
        return qq_config.get('access_control', {
            'enabled': False,
            'mode': 'disabled',
            'whitelist': [],
            'blacklist': [],
            'deny_message': '抱歉，你没有权限使用此机器人。'
        })

    def get(self, key: str, default=None):
        """获取配置项"""
        if key in self.PROMPT_FILES:
            return self.get_prompt_value(key, default if isinstance(default, str) else "")
        if key == "adapters":
            return sanitize_adapters_config(self._config.get(key, default))
        return self._config.get(key, default)
    
    def _deep_update(self, target: Dict[str, Any], source: Dict[str, Any]):
        """深度合并字典，递归处理嵌套字典
        
        Args:
            target: 目标字典（将被更新）
            source: 源字典（提供更新值）
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                # 递归合并嵌套字典
                self._deep_update(target[key], value)
            else:
                # 直接更新值（或覆盖整个字典）
                target[key] = value
    
    def update_config(self, section: str, config_dict: Any):
        """更新配置并保存到文件
        
        Args:
            section: 配置节名称，如 'image_generation'
            config_dict: 要更新的配置字典
        """
        if section in self.PROMPT_FILES:
            self.set_prompt_value(section, str(config_dict or ""))
            self._config.pop(section, None)
            self._save_config()
            return

        if not isinstance(config_dict, dict):
            self._config[section] = config_dict
            self._save_config()
            return

        if section == "adapters":
            config_dict = sanitize_adapters_config(config_dict)
            existing_adapters = self._config.get("adapters")
            if isinstance(existing_adapters, dict):
                self._config["adapters"] = sanitize_adapters_config(existing_adapters)

        # 更新内存中的配置
        if section not in self._config:
            self._config[section] = {}
        if not isinstance(self._config.get(section), dict):
            self._config[section] = {}
        
        # 深度合并配置
        self._deep_update(self._config[section], config_dict)
        if section == "adapters":
            self._config[section] = sanitize_adapters_config(self._config[section])
        
        # 保存到文件
        self._save_config()

    def refresh_from_file(self):
        """重新从配置文件载入，便于热更新"""
        self._config = self._load_config()
        self._ensure_prompt_files()
        self._ensure_personal_asset_paths()
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            if "adapters" in self._config:
                self._config["adapters"] = sanitize_adapters_config(self._config["adapters"])
            self._save_yaml_file(self.config_path, self._config)
        except Exception as e:
            raise Exception(f"配置文件保存失败: {e}")


# 全局配置实例
config = Config()
