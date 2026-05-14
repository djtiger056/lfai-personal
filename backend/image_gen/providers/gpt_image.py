import base64
import logging
import re
from io import BytesIO
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import ClientTimeout
from PIL import Image

from ..base import BaseImageProvider

logger = logging.getLogger(__name__)


class GptImageProvider(BaseImageProvider):
    """GPT-Image 图生图提供商（中转站）

    通过 OpenAI Chat Completions 兼容接口调用 gpt-4o-image 模型，
    仅支持图生图（需要传入参考图片），不支持纯文生图。
    计费：0.04 元/张
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_base = str(config.get("api_base", "")).rstrip("/")
        self.api_key = str(config.get("api_key", "") or "")
        self.model = str(config.get("model", "gpt-image-2") or "gpt-image-2")
        self.timeout = int(config.get("timeout", 120) or 120)

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def generate(self, prompt: str) -> Optional[bytes]:
        """纯文生图 — GPT-Image 不支持，直接返回 None"""
        logger.warning("[GptImage] 该提供商仅支持图生图，不支持纯文生图")
        return None

    async def generate_with_images(self, prompt: str, images: List[str]) -> Optional[bytes]:
        """图生图：基于参考图片和提示词生成图像

        使用 OpenAI Chat Completions 格式，将图片作为 image_url 传入 messages。

        Args:
            prompt: 图像修改/生成提示词
            images: 参考图片列表，支持 HTTP/HTTPS URL 或 Base64 Data URL 格式

        Returns:
            图像二进制数据（JPEG），失败返回 None
        """
        if not images:
            logger.error("[GptImage] 图生图需要至少一张参考图片")
            return None

        if not self.api_base:
            logger.error("[GptImage] 未配置 api_base")
            return None

        if not self.api_key:
            logger.error("[GptImage] 未配置 api_key，无法调用中转站")
            return None

        try:
            url = f"{self.api_base}/v1/chat/completions"

            # 构建 multimodal content
            content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
            for img in images:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img},
                })

            payload = {
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "user", "content": content}
                ],
            }

            timeout = ClientTimeout(
                connect=30,
                sock_connect=30,
                sock_read=self.timeout + 60,
                total=self.timeout + 90,
            )

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url, headers=self._build_headers(), json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(
                            f"[GptImage] 图生图请求失败: HTTP {response.status} - {error_text}"
                        )
                        return None

                    result = await response.json(content_type=None)

                # 解析响应：从 choices[0].message.content 中提取图片
                return await self._extract_image_from_response(session, result)

        except aiohttp.ClientError as e:
            logger.error(f"[GptImage] 网络错误: {e}")
            return None
        except TimeoutError as e:
            logger.error(f"[GptImage] 请求超时: {e}")
            return None
        except Exception as e:
            logger.error(f"[GptImage] 图生图异常: {e}")
            return None

    async def _extract_image_from_response(
        self, session: aiohttp.ClientSession, result: Dict[str, Any]
    ) -> Optional[bytes]:
        """从 Chat Completions 响应中提取图片数据

        GPT-Image 的响应格式：
        - content 可能是纯文本包含 URL
        - content 可能是 markdown 格式包含 ![](url)
        - content 可能是 base64 data URL
        - content 可能是结构化的 multimodal 内容列表
        """
        try:
            choices = result.get("choices", [])
            if not choices:
                logger.error("[GptImage] 响应中无 choices")
                return None

            message = choices[0].get("message", {})
            content = message.get("content", "")

            if not content:
                logger.error("[GptImage] 响应 message.content 为空")
                return None

            # 情况1: content 是列表（multimodal 响应）
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "image_url":
                            img_url = item.get("image_url", {}).get("url", "")
                            if img_url:
                                return await self._process_image_url(session, img_url)
                # 没有找到 image_url 类型，尝试从 text 中提取
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text", "")
                        img_bytes = await self._extract_image_from_text(session, text)
                        if img_bytes:
                            return img_bytes
                logger.error("[GptImage] multimodal 响应中未找到图片")
                return None

            # 情况2: content 是字符串
            if isinstance(content, str):
                return await self._extract_image_from_text(session, content)

            logger.error(f"[GptImage] 未知的 content 类型: {type(content)}")
            return None

        except Exception as e:
            logger.error(f"[GptImage] 解析响应异常: {e}")
            return None

    async def _extract_image_from_text(
        self, session: aiohttp.ClientSession, text: str
    ) -> Optional[bytes]:
        """从文本内容中提取图片（URL 或 base64）"""
        # 尝试提取 base64 data URL
        data_url_pattern = r'data:image/[^;]+;base64,([A-Za-z0-9+/=\s]+)'
        match = re.search(data_url_pattern, text)
        if match:
            try:
                b64_str = match.group(1).replace("\n", "").replace(" ", "")
                image_bytes = base64.b64decode(b64_str)
                return self._convert_to_jpeg(image_bytes)
            except Exception as e:
                logger.warning(f"[GptImage] base64 解码失败: {e}")

        # 尝试提取 markdown 图片 URL: ![...](url)
        md_pattern = r'!\[.*?\]\((https?://[^\s\)]+)\)'
        match = re.search(md_pattern, text)
        if match:
            return await self._process_image_url(session, match.group(1))

        # 尝试提取纯 URL（http/https 开头的图片链接）
        url_pattern = r'(https?://[^\s<>"\']+\.(?:png|jpg|jpeg|gif|webp|bmp)[^\s<>"\']*)'
        match = re.search(url_pattern, text, re.IGNORECASE)
        if match:
            return await self._process_image_url(session, match.group(1))

        # 尝试提取任何 https URL（可能是不带扩展名的图片链接）
        any_url_pattern = r'(https?://[^\s<>"\']+)'
        match = re.search(any_url_pattern, text)
        if match:
            return await self._process_image_url(session, match.group(1))

        logger.error(f"[GptImage] 无法从文本中提取图片: {text[:200]}")
        return None

    async def _process_image_url(
        self, session: aiohttp.ClientSession, url: str
    ) -> Optional[bytes]:
        """下载图片 URL 并转换为 JPEG"""
        # 如果是 data URL，直接解码
        if url.startswith("data:image"):
            match = re.match(r'data:image/[^;]+;base64,(.+)', url)
            if match:
                try:
                    image_bytes = base64.b64decode(match.group(1))
                    return self._convert_to_jpeg(image_bytes)
                except Exception as e:
                    logger.error(f"[GptImage] data URL 解码失败: {e}")
                    return None

        # HTTP(S) URL，下载图片
        try:
            download_timeout = ClientTimeout(connect=15, sock_read=60, total=90)
            async with aiohttp.ClientSession(timeout=download_timeout) as dl_session:
                async with dl_session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"[GptImage] 图片下载失败: HTTP {response.status}, URL: {url[:100]}")
                        return None
                    image_bytes = await response.read()
                    return self._convert_to_jpeg(image_bytes)
        except Exception as e:
            logger.error(f"[GptImage] 图片下载异常: {e}")
            return None

    def _convert_to_jpeg(self, image_bytes: bytes) -> Optional[bytes]:
        """将图片字节转换为 JPEG 格式"""
        try:
            image = Image.open(BytesIO(image_bytes))
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            img_buffer = BytesIO()
            image.save(img_buffer, format="JPEG", quality=95)
            return img_buffer.getvalue()
        except Exception as e:
            logger.error(f"[GptImage] 图片格式转换失败: {e}")
            return None

    async def test_connection(self) -> bool:
        """测试连接 — 发送请求验证 API 可达"""
        if not self.api_base or not self.api_key:
            logger.warning("[GptImage] 未配置 api_base 或 api_key")
            return False

        try:
            url = f"{self.api_base}/v1/models"
            timeout = ClientTimeout(connect=10, total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=self._build_headers()) as response:
                    # 只要能连通就算成功
                    return response.status < 500
        except Exception as e:
            logger.warning(f"[GptImage] 连接测试失败: {e}")
            return False
