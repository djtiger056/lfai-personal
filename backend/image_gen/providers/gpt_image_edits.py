import base64
import logging
import re
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from aiohttp import ClientTimeout
from PIL import Image

from ..base import BaseImageProvider

logger = logging.getLogger(__name__)


class GptImageEditsProvider(BaseImageProvider):
    """GPT-Image 编辑接口提供商。

    按 OpenAI Images Edits 兼容格式调用 /v1/images/edits，使用 multipart/form-data
    上传参考图。该接口需要至少一张底图，因此仅实现图生图。
    """

    SIZE_BY_RATIO_RESOLUTION: Dict[str, Dict[str, str]] = {
        "1:1": {"1k": "1024x1024", "2k": "2048x2048", "4k": "4096x4096"},
        "4:3": {"1k": "768x1024", "2k": "2304x1728", "4k": "4608x3456"},
        "3:4": {"1k": "1024x768", "2k": "1728x2304", "4k": "3456x4608"},
        "16:9": {"1k": "1024x576", "2k": "2560x1440", "4k": "5120x2880"},
        "9:16": {"1k": "576x1024", "2k": "1440x2560", "4k": "2880x5120"},
        "3:2": {"1k": "1024x682", "2k": "2496x1664", "4k": "4992x3328"},
        "2:3": {"1k": "682x1024", "2k": "1664x2496", "4k": "3328x4992"},
        "21:9": {"1k": "1195x512", "2k": "3024x1296", "4k": "6048x2592"},
    }

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_base = str(config.get("api_base", "https://jeniya.top") or "").rstrip("/")
        self.api_key = str(config.get("api_key", "") or "")
        self.model = str(config.get("model", "gpt-image-2-all") or "gpt-image-2-all")
        self.timeout = int(config.get("timeout", 180) or 180)
        self.ratio = str(config.get("ratio", "1:1") or "1:1")
        self.resolution = str(config.get("resolution", "1k") or "1k").lower()
        self.quality = str(config.get("quality", "") or "")
        self.background = str(config.get("background", "") or "")
        self.moderation = str(config.get("moderation", "") or "")
        self.response_format = str(config.get("response_format", "url") or "url")

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _resolve_size(self) -> str:
        configured_size = str(self.config.get("size", "") or "").strip()
        if configured_size:
            return configured_size
        resolution_map = self.SIZE_BY_RATIO_RESOLUTION.get(self.ratio)
        if resolution_map:
            return resolution_map.get(self.resolution, resolution_map["1k"])
        return self.SIZE_BY_RATIO_RESOLUTION["1:1"].get(self.resolution, "1024x1024")

    async def generate(self, prompt: str) -> Optional[bytes]:
        logger.warning("[GptImageEdits] 该提供商需要参考图，不支持纯文生图")
        return None

    async def generate_with_images(self, prompt: str, images: List[str]) -> Optional[bytes]:
        if not images:
            logger.error("[GptImageEdits] 图生图需要至少一张参考图片")
            return None
        if not self.api_base:
            logger.error("[GptImageEdits] 未配置 api_base")
            return None

        timeout = ClientTimeout(
            connect=30,
            sock_connect=30,
            sock_read=self.timeout + 60,
            total=self.timeout + 90,
        )
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                form = aiohttp.FormData()
                added_images = 0
                for index, image_ref in enumerate(images):
                    upload = await self._load_image_for_upload(session, image_ref, index)
                    if upload is None:
                        continue
                    image_bytes, filename, mime_type = upload
                    form.add_field(
                        "image",
                        image_bytes,
                        filename=filename,
                        content_type=mime_type,
                    )
                    added_images += 1

                if added_images == 0:
                    logger.error("[GptImageEdits] 没有可上传的有效参考图片")
                    return None

                form.add_field("prompt", prompt)
                form.add_field("model", self.model)
                form.add_field("n", "1")
                form.add_field("size", self._resolve_size())
                if self.response_format:
                    form.add_field("response_format", self.response_format)
                if self.quality:
                    form.add_field("quality", self.quality)
                if self.background:
                    form.add_field("background", self.background)
                if self.moderation:
                    form.add_field("moderation", self.moderation)

                async with session.post(
                    f"{self.api_base}/v1/images/edits",
                    headers=self._build_headers(),
                    data=form,
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(
                            "[GptImageEdits] 请求失败: HTTP %s - %s",
                            response.status,
                            error_text,
                        )
                        return None
                    result = await response.json(content_type=None)

                return await self._extract_image_from_response(session, result)
        except aiohttp.ClientError as e:
            logger.error("[GptImageEdits] 网络错误: %s", e)
            return None
        except TimeoutError as e:
            logger.error("[GptImageEdits] 请求超时: %s", e)
            return None
        except Exception as e:
            logger.error("[GptImageEdits] 图生图异常: %s", e)
            return None

    async def _load_image_for_upload(
        self,
        session: aiohttp.ClientSession,
        image_ref: str,
        index: int,
    ) -> Optional[Tuple[bytes, str, str]]:
        if image_ref.startswith("data:image/"):
            return self._decode_data_url(image_ref, index)

        if image_ref.startswith(("http://", "https://")):
            try:
                async with session.get(image_ref) as response:
                    if response.status != 200:
                        logger.error("[GptImageEdits] 参考图下载失败: HTTP %s", response.status)
                        return None
                    image_bytes = await response.read()
                    mime_type = response.headers.get("Content-Type", "").split(";")[0].strip()
                    if not mime_type.startswith("image/"):
                        mime_type = self._detect_mime_type(image_bytes)
                    return image_bytes, self._filename_for_mime(index, mime_type), mime_type
            except Exception as e:
                logger.error("[GptImageEdits] 参考图下载异常: %s", e)
                return None

        logger.error("[GptImageEdits] 不支持的参考图格式，仅支持 HTTP URL 或 Base64 Data URL")
        return None

    def _decode_data_url(self, data_url: str, index: int) -> Optional[Tuple[bytes, str, str]]:
        match = re.match(r"data:(image/[^;]+);base64,(.+)", data_url, re.DOTALL)
        if not match:
            logger.error("[GptImageEdits] Data URL 格式无效")
            return None
        mime_type = match.group(1)
        try:
            image_bytes = base64.b64decode(match.group(2).replace("\n", "").replace(" ", ""))
            return image_bytes, self._filename_for_mime(index, mime_type), mime_type
        except Exception as e:
            logger.error("[GptImageEdits] Data URL 解码失败: %s", e)
            return None

    @staticmethod
    def _filename_for_mime(index: int, mime_type: str) -> str:
        ext = mime_type.split("/")[-1].lower()
        if ext == "jpeg":
            ext = "jpg"
        if ext not in {"jpg", "png", "webp"}:
            ext = "png"
        return f"image_{index}.{ext}"

    @staticmethod
    def _detect_mime_type(image_bytes: bytes) -> str:
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
            return "image/webp"
        return "image/png"

    async def _extract_image_from_response(
        self,
        session: aiohttp.ClientSession,
        result: Dict[str, Any],
    ) -> Optional[bytes]:
        data = result.get("data")
        if isinstance(data, list) and data:
            for item in data:
                image_bytes = await self._extract_image_from_item(session, item)
                if image_bytes:
                    return image_bytes

        choices = result.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            content = message.get("content", "")
            return await self._extract_image_from_text(session, content)

        logger.error("[GptImageEdits] 响应中未找到图片数据: %s", str(result)[:500])
        return None

    async def _extract_image_from_item(
        self,
        session: aiohttp.ClientSession,
        item: Any,
    ) -> Optional[bytes]:
        if not isinstance(item, dict):
            return None
        if item.get("url"):
            return await self._download_image(session, str(item["url"]))
        if item.get("b64_json"):
            try:
                return self._convert_to_jpeg(base64.b64decode(item["b64_json"]))
            except Exception as e:
                logger.error("[GptImageEdits] b64_json 解码失败: %s", e)
                return None
        return None

    async def _extract_image_from_text(
        self,
        session: aiohttp.ClientSession,
        content: Any,
    ) -> Optional[bytes]:
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "image_url":
                    image_url = part.get("image_url", {}).get("url", "")
                    if image_url:
                        return await self._download_image(session, image_url)
                text = part.get("text")
                if text:
                    image_bytes = await self._extract_image_from_text(session, text)
                    if image_bytes:
                        return image_bytes
            return None

        if not isinstance(content, str):
            return None

        data_url_match = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=\s]+)", content)
        if data_url_match:
            try:
                raw = base64.b64decode(data_url_match.group(1).replace("\n", "").replace(" ", ""))
                return self._convert_to_jpeg(raw)
            except Exception as e:
                logger.warning("[GptImageEdits] 文本中 base64 解码失败: %s", e)

        markdown_match = re.search(r"!\[.*?\]\((https?://[^\s)]+)\)", content)
        if markdown_match:
            return await self._download_image(session, markdown_match.group(1))

        url_match = re.search(r"(https?://[^\s<>\"']+)", content)
        if url_match:
            return await self._download_image(session, url_match.group(1))

        logger.error("[GptImageEdits] 无法从文本响应中提取图片: %s", content[:200])
        return None

    async def _download_image(
        self,
        session: aiohttp.ClientSession,
        image_url: str,
    ) -> Optional[bytes]:
        if image_url.startswith("data:image/"):
            decoded = self._decode_data_url(image_url, 0)
            if not decoded:
                return None
            return self._convert_to_jpeg(decoded[0])

        try:
            async with session.get(image_url) as response:
                if response.status != 200:
                    logger.error("[GptImageEdits] 图片下载失败: HTTP %s", response.status)
                    return None
                image_bytes = await response.read()
            return self._convert_to_jpeg(image_bytes)
        except Exception as e:
            logger.error("[GptImageEdits] 图片下载异常: %s", e)
            return None

    @staticmethod
    def _convert_to_jpeg(image_bytes: bytes) -> Optional[bytes]:
        try:
            image = Image.open(BytesIO(image_bytes))
            if image.mode in ("RGBA", "LA"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1])
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=95)
            return buffer.getvalue()
        except Exception as e:
            logger.error("[GptImageEdits] 图片格式转换失败: %s", e)
            return None

    async def test_connection(self) -> bool:
        if not self.api_base:
            logger.warning("[GptImageEdits] 未配置 api_base")
            return False

        try:
            timeout = ClientTimeout(connect=10, total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    f"{self.api_base}/v1/models",
                    headers=self._build_headers(),
                ) as response:
                    return response.status < 500
        except Exception as e:
            logger.warning("[GptImageEdits] 连接测试失败: %s", e)
            return False
