import asyncio
import base64
from io import BytesIO
from typing import Any, Dict, Optional

import aiohttp
from aiohttp import ClientTimeout
from PIL import Image

from ..base import BaseImageProvider


class KlingApiProvider(BaseImageProvider):
    """Kling API 图像生成提供商。"""

    DEFAULT_SIZE = "1024x1024"

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = str(config.get("api_base", "http://127.0.0.1:18080")).rstrip("/")
        self.api_key = str(config.get("api_key", "") or "")
        self.model = str(config.get("model", "kling-v2-1") or "kling-v2-1")
        self.timeout = int(config.get("timeout", 180) or 180)
        self.size = str(config.get("size", self.DEFAULT_SIZE) or self.DEFAULT_SIZE)
        self.poll_interval = float(config.get("poll_interval", 3.0) or 3.0)
        self.target_url = str(
            config.get("target_url", "https://klingai.com/app/image/new")
            or "https://klingai.com/app/image/new"
        )
        self.transport = str(config.get("transport", "web") or "web")
        self.response_format = str(config.get("response_format", "url") or "url")

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _build_payload(self, prompt: str, async_mode: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "size": self.size,
            "response_format": self.response_format,
            "provider_options": {
                "transport": self.transport,
                "target_url": self.target_url,
            },
        }
        if async_mode:
            payload["async"] = True
        return payload

    async def _download_image(self, session: aiohttp.ClientSession, image_url: str) -> Optional[bytes]:
        async with session.get(image_url) as response:
            if response.status != 200:
                return None
            image_bytes = await response.read()
            image = Image.open(BytesIO(image_bytes))
            img_buffer = BytesIO()
            image.save(img_buffer, format="JPEG")
            return img_buffer.getvalue()

    async def _decode_b64_image(self, encoded: str) -> Optional[bytes]:
        try:
            image_bytes = base64.b64decode(encoded)
            image = Image.open(BytesIO(image_bytes))
            img_buffer = BytesIO()
            image.save(img_buffer, format="JPEG")
            return img_buffer.getvalue()
        except Exception:
            return None

    async def _extract_image_bytes(self, session: aiohttp.ClientSession, data: Dict[str, Any]) -> Optional[bytes]:
        image_list = data.get("data") or []
        if not image_list:
            return None
        first = image_list[0] or {}

        if first.get("b64_json"):
            return await self._decode_b64_image(first["b64_json"])

        image_url = first.get("url")
        if image_url:
            return await self._download_image(session, image_url)
        return None

    async def _poll_task_result(self, session: aiohttp.ClientSession, task_id: str) -> Optional[bytes]:
        status_url = f"{self.base_url}/v1/images/generations/{task_id}"
        start = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - start < self.timeout:
            async with session.get(status_url, headers=self._build_headers()) as response:
                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(f"Kling 查询任务失败: {response.status} - {body}")
                payload = await response.json()

            data = payload.get("data") or {}
            task_status = str(data.get("task_status") or "").lower()
            if task_status in {"succeed", "success", "done"}:
                task_result = data.get("task_result") or {}
                return await self._extract_image_bytes(session, task_result)
            if task_status in {"failed", "error", "cancelled"}:
                error_message = data.get("error") or payload.get("error") or "任务失败"
                raise RuntimeError(f"Kling 生图任务失败: {error_message}")

            await asyncio.sleep(self.poll_interval)
        raise TimeoutError("Kling 生图任务轮询超时")

    async def generate(self, prompt: str) -> Optional[bytes]:
        timeout = ClientTimeout(
            connect=15,
            sock_connect=15,
            sock_read=self.timeout,
            total=self.timeout + 20,
        )
        async with aiohttp.ClientSession(timeout=timeout) as session:
            payload = self._build_payload(prompt, async_mode=True)
            url = f"{self.base_url}/v1/images/generations"
            async with session.post(url, headers=self._build_headers(), json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise RuntimeError(f"Kling 生图提交失败: {response.status} - {error_text}")
                result = await response.json()

            data = result.get("data") or {}
            task_id = data.get("task_id")
            if task_id:
                return await self._poll_task_result(session, str(task_id))

            return await self._extract_image_bytes(session, result)

    async def test_connection(self) -> bool:
        timeout = ClientTimeout(connect=10, sock_connect=10, sock_read=20, total=25)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.base_url}/ping") as response:
                return response.status == 200
