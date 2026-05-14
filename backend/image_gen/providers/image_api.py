import asyncio
import base64
import logging
from io import BytesIO
from typing import Optional, Dict, Any, List

import aiohttp
from aiohttp import ClientTimeout
from PIL import Image

from ..base import BaseImageProvider

logger = logging.getLogger(__name__)


class ImageApiProvider(BaseImageProvider):
    """Image API 图像生成提供商 — 统一接入 Jimeng/Doubao/XYQ/Kling 平台"""

    SUPPORTED_MODELS = {
        # Jimeng（即梦）
        "jimeng-2.1", "jimeng-3.0", "jimeng-3.1", "jimeng-4.0", "jimeng-4.1",
        "jimeng-4.5", "jimeng-4.6", "jimeng-5.0", "jimeng-xl-pro",
        # Doubao（豆包）
        "doubao-seedream-3.0", "doubao-seedream-4.0", "doubao-seedream-4.5",
        # XYQ（小云雀）
        "xyq-seedream-4.0", "xyq-seedream-4.5", "xyq-seedream-5.0",
        # Kling（可灵）
        "kling-v2-1", "kling-v3-omni", "kling-image-o1",
    }
    DEFAULT_MODEL = "doubao-seedream-4.5"

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_base = config.get("api_base", "http://127.0.0.1:18081")
        self.api_key = config.get("api_key", "")
        self.timeout = config.get("timeout", 120)
        self.ratio = config.get("ratio", "1:1")
        self.resolution = config.get("resolution", "2k")
        self.sample_strength = config.get("sample_strength", 0.5)

        # 模型设置：支持列表中的模型直接使用，其他模型也允许（服务端可能新增了模型）
        requested_model = config.get("model", self.DEFAULT_MODEL)
        if requested_model in self.SUPPORTED_MODELS:
            self.model = requested_model
        else:
            # 非已知模型仍然允许使用（服务端可能支持更多模型），仅记录 info
            logger.info(
                f"模型 '{requested_model}' 不在已知列表中，将直接透传给 Images API 服务"
            )
            self.model = requested_model

    async def generate(self, prompt: str) -> Optional[bytes]:
        """文生图：根据提示词生成图像

        Args:
            prompt: 图像生成提示词

        Returns:
            图像二进制数据（JPEG），失败返回 None
        """
        try:
            url = f"{self.api_base}/v1/images/generations"

            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["x-api-key"] = self.api_key

            data = {
                "model": self.model,
                "prompt": prompt,
                "ratio": self.ratio,
                "resolution": self.resolution,
                "n": 1,
                "response_format": "url",
            }

            timeout = ClientTimeout(
                connect=10,
                sock_connect=10,
                sock_read=self.timeout,
                total=self.timeout + 20,
            )

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(
                            f"Image API 文生图失败: HTTP {response.status} - {error_text}"
                        )
                        return None

                    result = await response.json(content_type=None)

                    if not result or "data" not in result or not result.get("data"):
                        logger.error(f"Image API 文生图失败: 响应中无 data 数组或为空, 实际响应: {result}")
                        return None

                    image_data = result["data"][0]

                    # 如果返回的是 URL，下载图片（带重试）
                    if "url" in image_data:
                        image_url = image_data["url"]
                        return await self._download_image_with_retry(image_url)

                    # 如果返回的是 Base64 数据
                    elif "b64_json" in image_data:
                        image_bytes = base64.b64decode(image_data["b64_json"])
                        image = Image.open(BytesIO(image_bytes))
                        img_buffer = BytesIO()
                        image.save(img_buffer, format="JPEG")
                        return img_buffer.getvalue()

                    logger.error("Image API 文生图失败: 响应中无 url 或 b64_json 字段")
                    return None

        except aiohttp.ClientError as e:
            logger.error(f"Image API 文生图网络错误: {str(e)}")
            return None
        except TimeoutError as e:
            logger.error(f"Image API 文生图超时: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Image API 文生图失败: {str(e)}")
            return None

    async def _download_image_with_retry(
        self, image_url: str, max_retries: int = 3
    ) -> Optional[bytes]:
        """下载图片 URL 并转换为 JPEG，带重试机制。

        Args:
            image_url: 图片 URL
            max_retries: 最大重试次数

        Returns:
            JPEG 图像二进制数据，失败返回 None
        """
        for attempt in range(max_retries):
            try:
                download_timeout = ClientTimeout(
                    connect=15,
                    sock_read=60,
                    total=90,
                )
                async with aiohttp.ClientSession(timeout=download_timeout) as dl_session:
                    async with dl_session.get(image_url) as img_response:
                        if img_response.status != 200:
                            logger.error(
                                f"Image API 图片下载失败: HTTP {img_response.status}"
                            )
                            return None
                        image_bytes = await img_response.read()
                        image = Image.open(BytesIO(image_bytes))
                        img_buffer = BytesIO()
                        image.save(img_buffer, format="JPEG")
                        return img_buffer.getvalue()
            except (aiohttp.ClientPayloadError, aiohttp.ClientError) as e:
                if attempt < max_retries - 1:
                    wait = (attempt + 1) * 2
                    logger.warning(
                        f"Image API 图片下载异常 (第{attempt+1}次): {e}, {wait}秒后重试"
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        f"Image API 图片下载失败 (已重试{max_retries}次): {e}"
                    )
                    return None
            except Exception as e:
                logger.error(f"Image API 图片下载异常: {e}")
                return None
        return None

    async def _extract_image_from_response(
        self, session: aiohttp.ClientSession, result: Dict[str, Any]
    ) -> Optional[bytes]:
        """从 API 响应中提取图像数据并转换为 JPEG

        支持两种响应格式：
        - url: 下载图片并转换为 JPEG（带重试）
        - b64_json: Base64 解码并转换为 JPEG

        Args:
            session: aiohttp 会话（保留参数兼容性，实际下载使用独立 session）
            result: API 响应 JSON 数据

        Returns:
            JPEG 图像二进制数据，失败返回 None
        """
        if not result or "data" not in result or not result.get("data"):
            logger.warning(f"Image API 响应中无 data 数组或为空, 实际响应: {str(result)[:500]}")
            return None

        image_data = result["data"][0]

        # 如果返回的是 URL，下载图片（带重试）
        if "url" in image_data:
            return await self._download_image_with_retry(image_data["url"])

        # 如果返回的是 Base64 数据
        elif "b64_json" in image_data:
            try:
                image_bytes = base64.b64decode(image_data["b64_json"])
                image = Image.open(BytesIO(image_bytes))
                img_buffer = BytesIO()
                image.save(img_buffer, format="JPEG")
                return img_buffer.getvalue()
            except Exception as e:
                logger.error(f"Image API Base64 解码失败: {e}")
                return None

        logger.warning("Image API 响应中无 url 或 b64_json 字段")
        return None

    async def _poll_task(
        self, session: aiohttp.ClientSession, task_id: str, headers: Dict[str, str]
    ) -> Optional[bytes]:
        """轮询异步任务直到完成或超时

        Args:
            session: aiohttp 会话
            task_id: 异步任务 ID
            headers: 请求头

        Returns:
            JPEG 图像二进制数据，失败返回 None
        """
        poll_url = f"{self.api_base}/v1/images/generations/{task_id}"
        poll_interval = 3  # 每 3 秒轮询一次
        elapsed = 0

        while elapsed < self.timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            try:
                async with session.get(poll_url, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json(content_type=None)
                        status = result.get("status", "") if result else ""

                        if status == "success":
                            return await self._extract_image_from_response(
                                session, result
                            )
                        elif status in ("failed", "error"):
                            logger.error(
                                f"Image API 异步任务失败: task_id={task_id}, "
                                f"status={status}"
                            )
                            return None
                        # 其他状态（pending/processing）继续轮询
                    else:
                        logger.error(
                            f"Image API 任务轮询失败: {response.status}"
                        )
                        return None
            except aiohttp.ClientError as e:
                logger.error(f"Image API 任务轮询网络错误: {e}")
                return None

        logger.error(f"Image API 异步任务超时: task_id={task_id}, timeout={self.timeout}s")
        return None

    async def generate_with_images(self, prompt: str, images: List[str]) -> Optional[bytes]:
        """图生图：基于参考图片和提示词生成图像

        Args:
            prompt: 图像生成提示词
            images: 参考图片列表，支持 HTTP/HTTPS URL 或 Base64 Data URL 格式

        Returns:
            图像二进制数据（JPEG），失败返回 None
        """
        try:
            url = f"{self.api_base}/v1/images/compositions"

            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["x-api-key"] = self.api_key

            data = {
                "model": self.model,
                "prompt": prompt,
                "images": images,
                "ratio": self.ratio,
                "resolution": self.resolution,
                "sample_strength": self.sample_strength,
                "n": 1,
                "response_format": "url",
            }

            timeout = ClientTimeout(
                connect=10,
                sock_connect=10,
                sock_read=self.timeout,
                total=self.timeout + 20,
            )

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json(content_type=None)

                        logger.info(f"Image API 图生图响应: {str(result)[:500]}")

                        if not result:
                            logger.error("Image API 图生图失败: 响应体为空")
                            return None

                        # 处理异步任务响应
                        if "task_id" in result:
                            logger.info(
                                f"Image API 图生图返回异步任务: "
                                f"task_id={result['task_id']}"
                            )
                            return await self._poll_task(
                                session, result["task_id"], headers
                            )

                        # 直接返回结果
                        return await self._extract_image_from_response(
                            session, result
                        )
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"Image API 图生图失败: "
                            f"status={response.status}, body={error_text}"
                        )
                        return None

        except aiohttp.ClientError as e:
            logger.error(f"Image API 图生图网络错误: {e}")
            return None
        except Exception as e:
            logger.error(f"Image API 图生图异常: {e}")
            return None

    async def test_connection(self) -> bool:
        """测试与 Image API 服务的连接

        发送 GET 请求到 {api_base}/ping，验证返回 HTTP 200。
        优先检查 JSON body 是否包含 {"ok": true}，
        若响应非 JSON（纯文本 "pong" 等），只要 HTTP 200 即视为连接成功。

        Returns:
            连接是否成功
        """
        try:
            url = f"{self.api_base}/ping"
            timeout = ClientTimeout(connect=10, total=25)

            headers: Dict[str, str] = {}
            if self.api_key:
                headers["x-api-key"] = self.api_key

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(
                            f"Image API 连接测试失败: HTTP {response.status}"
                        )
                        return False

                    # HTTP 200 — 尝试解析 JSON
                    try:
                        result = await response.json(content_type=None)
                        if isinstance(result, dict) and result.get("ok") is True:
                            return True
                        # JSON 解析成功但没有 ok=true，仍视为连接可达
                        logger.info(
                            f"Image API 连接测试: HTTP 200, JSON 响应: {result}"
                        )
                        return True
                    except Exception:
                        # 非 JSON 响应（纯文本 "pong" 等），HTTP 200 即视为成功
                        text = await response.text()
                        logger.info(
                            f"Image API 连接测试: HTTP 200, 纯文本响应: {text[:100]}"
                        )
                        return True

        except Exception as e:
            logger.warning(f"Image API 连接测试失败: {e}")
            return False
