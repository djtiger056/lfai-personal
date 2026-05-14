import logging
import re
from typing import Optional

from .base_image_service import BaseImageService
from .config import ImageGenerationConfig
from .providers.kling_api import KlingApiProvider
from .providers.modelscope import ModelScopeProvider
from .providers.yunwu import YunwuProvider
from .providers.image_api import ImageApiProvider
from .providers.gpt_image import GptImageProvider
from backend.user.data_manager import user_data_manager

logger = logging.getLogger(__name__)


class ImageGenerationManager:
    """图像生成管理器"""

    PROVIDER_MAP = {
        "modelscope": (ModelScopeProvider, "modelscope"),
        "yunwu": (YunwuProvider, "yunwu"),
        "kling_api": (KlingApiProvider, "kling_api"),
        "image_api": (ImageApiProvider, "image_api"),
        "gpt_image": (GptImageProvider, "gpt_image"),
    }

    def __init__(self, config: ImageGenerationConfig):
        self.config = config
        self.primary_provider = self._create_provider(self.config.provider)
        self.fallback_provider = None
        if self.config.enable_fallback and self.config.fallback_provider != self.config.provider:
            try:
                self.fallback_provider = self._create_provider(self.config.fallback_provider)
                print(f"[ImageGen] 已初始化备用提供商: {self.config.fallback_provider}")
            except Exception as e:
                print(f"[ImageGen] 初始化备用提供商失败: {e}")

        # 初始化底图管理服务（用于图生图自动触发）
        self.base_image_service = BaseImageService(
            user_data_manager=user_data_manager,
            fallback_image_path=self.config.default_base_image_path,
        )

    def _create_provider(self, provider_name: str):
        """创建图像生成提供商实例"""
        if provider_name not in self.PROVIDER_MAP:
            raise ValueError(f"不支持的图像生成提供商: {provider_name}")
        provider_class, config_key = self.PROVIDER_MAP[provider_name]
        config_section = getattr(self.config, config_key)
        return provider_class(config_section.dict())

    def update_config(self, config: ImageGenerationConfig):
        """更新配置"""
        self.config = config
        self.primary_provider = self._create_provider(self.config.provider)
        self.fallback_provider = None
        if self.config.enable_fallback and self.config.fallback_provider != self.config.provider:
            try:
                self.fallback_provider = self._create_provider(self.config.fallback_provider)
                print(f"[ImageGen] 已更新备用提供商: {self.config.fallback_provider}")
            except Exception as e:
                print(f"[ImageGen] 更新备用提供商失败: {e}")

        # 重新创建底图服务（配置可能变更了 default_base_image_path）
        self.base_image_service = BaseImageService(
            user_data_manager=user_data_manager,
            fallback_image_path=self.config.default_base_image_path,
        )

    def should_trigger_image_generation(self, message: str) -> Optional[str]:
        """检查是否应该触发图像生成"""
        if not self.config.enabled:
            return None

        message = message.strip()
        for keyword in self.config.trigger_keywords:
            if keyword in message:
                prompt = self._extract_prompt(message, keyword)
                if prompt:
                    return prompt
        return None

    def _extract_prompt(self, message: str, keyword: str) -> Optional[str]:
        """从消息中提取提示词"""
        patterns = [
            rf"{keyword}[:：]\s*(.+)",
            rf"{keyword}(.+)",
            rf"帮我{keyword}(.+)",
            rf"请{keyword}(.+)",
            rf"{keyword}，(.+)",
        ]

        special_patterns = [
            r"帮我生图[，,]\s*主题是\s*(.+)",
            r"请生图[，,]\s*主题是\s*(.+)",
            r"生图[，,]\s*主题是\s*(.+)",
        ]

        for pattern in special_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                prompt = re.sub(r'[。，！？,.!?]+$', '', match.group(1).strip())
                if prompt:
                    return prompt

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                prompt = re.sub(r'[。，！？,.!?]+$', '', match.group(1).strip())
                if prompt:
                    return prompt

        return None

    async def generate_image(self, prompt: str, user_id: Optional[str] = None) -> Optional[bytes]:
        """生成图像（支持图生图自动触发和自动降级）

        降级链：
        - provider == "image_api" 且 user_id 有效：I2I → T2I (same provider) → fallback → None
        - provider == "gpt_image" 且 user_id 有效：I2I → fallback → None（不支持文生图）
        - 其他情况：T2I (primary) → fallback → None
        """
        # 当 provider 为 gpt_image 时，仅支持图生图
        if self.config.provider == "gpt_image" and user_id:
            try:
                base_image_url = await self.base_image_service.get_effective_base_image_data_url(user_id)
                if base_image_url:
                    result = await self.primary_provider.generate_with_images(prompt, [base_image_url])
                    if result:
                        logger.info(f"[ImageGen] gpt_image 图生图成功, user_id={user_id}")
                        return result
                    logger.warning("[ImageGen] gpt_image 图生图返回空结果")
                else:
                    logger.warning(f"[ImageGen] 用户 {user_id} 无可用底图, gpt_image 无法生成（仅支持图生图）")
            except Exception as e:
                logger.warning(f"[ImageGen] gpt_image 图生图异常: {e}")

            # gpt_image 不支持文生图，直接尝试 fallback
            if self.config.enable_fallback and self.fallback_provider:
                try:
                    result = await self.fallback_provider.generate(prompt)
                    if result:
                        logger.info(f"[ImageGen] 备用提供商 {self.config.fallback_provider} 生成成功")
                        return result
                except Exception as e:
                    logger.warning(f"[ImageGen] 备用提供商也失败: {e}")

            logger.error("[ImageGen] 所有提供商均失败")
            return None

        # 当 provider 为 image_api 且 user_id 有效时，尝试图生图
        if self.config.provider == "image_api" and user_id:
            try:
                # 获取有效底图 Data URL
                base_image_url = await self.base_image_service.get_effective_base_image_data_url(user_id)
                if base_image_url:
                    # 尝试图生图
                    result = await self.primary_provider.generate_with_images(prompt, [base_image_url])
                    if result:
                        logger.info(f"[ImageGen] image_api 图生图成功, user_id={user_id}")
                        return result
                    logger.warning("[ImageGen] image_api 图生图返回空结果, 回退到文生图")
                else:
                    logger.warning(f"[ImageGen] 用户 {user_id} 无可用底图, 回退到文生图")
            except Exception as e:
                logger.warning(f"[ImageGen] image_api 图生图异常: {e}, 回退到文生图")

            # I2I 失败，回退到同 provider 的文生图
            try:
                result = await self.primary_provider.generate(prompt)
                if result:
                    logger.info("[ImageGen] image_api 文生图成功 (I2I 回退)")
                    return result
            except Exception as e:
                logger.warning(f"[ImageGen] image_api 文生图也失败: {e}")

            # 同 provider T2I 也失败，尝试 fallback
            if self.config.enable_fallback and self.fallback_provider:
                try:
                    result = await self.fallback_provider.generate(prompt)
                    if result:
                        logger.info(f"[ImageGen] 备用提供商 {self.config.fallback_provider} 生成成功")
                        return result
                except Exception as e:
                    logger.warning(f"[ImageGen] 备用提供商也失败: {e}")

            logger.error("[ImageGen] 所有提供商均失败")
            return None

        # 非 image_api 或无 user_id：使用现有文生图流程
        try:
            result = await self.primary_provider.generate(prompt)
            if result:
                logger.info(f"[ImageGen] 主提供商 {self.config.provider} 生成成功")
                return result
        except Exception as e:
            logger.warning(f"[ImageGen] 主提供商 {self.config.provider} 失败: {e}")

        if self.config.enable_fallback and self.fallback_provider:
            try:
                result = await self.fallback_provider.generate(prompt)
                if result:
                    logger.info(f"[ImageGen] 备用提供商 {self.config.fallback_provider} 生成成功")
                    return result
            except Exception as e:
                logger.warning(f"[ImageGen] 备用提供商 {self.config.fallback_provider} 失败: {e}")

        logger.error("[ImageGen] 所有提供商均失败")
        return None

    async def test_connection(self) -> bool:
        """测试连接（支持降级）"""
        try:
            if await self.primary_provider.test_connection():
                print(f"[ImageGen] 主提供商 {self.config.provider} 连接正常")
                return True
        except Exception as e:
            print(f"[ImageGen] 主提供商 {self.config.provider} 连接失败: {str(e)}")

        if self.config.enable_fallback and self.fallback_provider:
            try:
                if await self.fallback_provider.test_connection():
                    print(f"[ImageGen] 备用提供商 {self.config.fallback_provider} 连接正常")
                    return True
            except Exception as e:
                print(f"[ImageGen] 备用提供商 {self.config.fallback_provider} 连接失败: {str(e)}")

        return False
