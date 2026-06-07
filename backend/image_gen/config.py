from typing import Dict, Any, List
from pydantic import BaseModel, Field


class ModelScopeConfig(BaseModel):
    """魔搭社区配置"""
    api_key: str = ""
    model: str = "Tongyi-MAI/Z-Image-Turbo"
    timeout: int = 120


class YunwuConfig(BaseModel):
    """yunwu.ai 配置"""
    api_key: str = ""
    api_base: str = "https://yunwu.ai/v1"
    model: str = "jimeng-4.5"
    timeout: int = 120


class KlingApiConfig(BaseModel):
    """本地 kling-api 配置"""
    api_base: str = "http://127.0.0.1:18080"
    api_key: str = ""
    model: str = "kling-v2-1"
    timeout: int = 180
    size: str = "1024x1024"
    poll_interval: float = 3.0
    transport: str = "web"
    target_url: str = "https://klingai.com/app/image/new"
    response_format: str = "url"


class ImageApiConfig(BaseModel):
    """Image API 统一图片生成服务配置（支持 Jimeng/Doubao/XYQ/Kling/Qwen/Seedream）"""
    api_base: str = "http://127.0.0.1:8006"
    api_key: str = ""
    model: str = "seedream-5.0"
    timeout: int = 120
    ratio: str = "1:1"
    resolution: str = "2k"
    sample_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    negative_prompt: str = ""
    intelligent_ratio: bool = False
    response_format: str = "url"
    n: int = Field(default=1, ge=1, le=10)
    provider_options: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class GptImageConfig(BaseModel):
    """GPT-Image 中转站配置（仅支持图生图）"""
    api_base: str = ""
    api_key: str = ""
    model: str = "gpt-image-2"
    timeout: int = 180


class GptImageEditsConfig(BaseModel):
    """GPT-Image Edits 接口配置（multipart /v1/images/edits，仅支持图生图）"""
    api_base: str = "https://jeniya.top"
    api_key: str = ""
    model: str = "gpt-image-2-all"
    timeout: int = 180
    ratio: str = "1:1"
    resolution: str = "1k"
    quality: str = ""
    background: str = ""
    moderation: str = ""
    response_format: str = "url"


class ImageGenerationConfig(BaseModel):
    """图像生成配置"""
    enabled: bool = False
    provider: str = "modelscope"  # 当前提供商
    fallback_provider: str = "yunwu"  # 备用提供商
    enable_fallback: bool = True  # 是否启用自动降级
    modelscope: ModelScopeConfig = ModelScopeConfig()
    yunwu: YunwuConfig = YunwuConfig()
    kling_api: KlingApiConfig = KlingApiConfig()
    image_api: ImageApiConfig = ImageApiConfig()
    gpt_image: GptImageConfig = GptImageConfig()
    gpt_image_edits: GptImageEditsConfig = GptImageEditsConfig()
    default_base_image_path: str = "backend/data/default_base_image.jpg"
    trigger_keywords: List[str] = [
        "画", "生成图片", "生图", "绘制"
    ]
    generating_message: str = "🎨 正在为你生成图片，请稍候..."
    error_message: str = "😢 图片生成失败：{error}"
    success_message: str = "✨ 图片已生成完成！"
