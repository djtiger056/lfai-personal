import aiohttp
import asyncio
from typing import Dict, Any


class AssemblyAIASRProvider:
    """AssemblyAI ASR提供商（异步文件转录）"""

    def __init__(self, config: Dict[str, Any]):
        self.api_base = config.get('api_base', 'https://api.assemblyai.com')
        self.api_key = config.get('api_key', '')
        self.model = config.get('model', 'universal-3-pro')
        self.timeout = config.get('timeout', 60)

        if not self.api_key:
            raise ValueError("AssemblyAI API密钥未配置")

    async def transcribe(self, audio_data: bytes, filename: str = "audio.mp3") -> str:
        """
        语音转文本（上传 -> 提交转录 -> 轮询结果）

        Args:
            audio_data: 音频文件的二进制数据
            filename: 文件名

        Returns:
            识别结果文本
        """
        headers = {"authorization": self.api_key}

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: 上传音频文件
                upload_url = await self._upload_file(session, headers, audio_data, filename)

                # Step 2: 提交转录请求
                transcript_id = await self._submit_transcription(session, headers, upload_url)

                # Step 3: 轮询获取结果
                text = await self._poll_result(session, headers, transcript_id)
                return text

        except asyncio.TimeoutError:
            raise Exception("语音识别超时")
        except aiohttp.ClientError as e:
            raise Exception(f"网络请求失败: {str(e)}")
        except Exception as e:
            raise Exception(f"语音识别失败: {str(e)}")

    async def _upload_file(self, session: aiohttp.ClientSession, headers: dict,
                           audio_data: bytes, filename: str) -> str:
        """上传音频文件，返回 upload_url"""
        url = f"{self.api_base}/v2/upload"
        upload_headers = {"authorization": self.api_key}

        async with session.post(
            url,
            data=audio_data,
            headers={**upload_headers, "Content-Type": "application/octet-stream"},
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"上传音频失败 (HTTP {response.status}): {error_text}")
            result = await response.json()
            return result["upload_url"]

    async def _submit_transcription(self, session: aiohttp.ClientSession,
                                     headers: dict, audio_url: str) -> str:
        """提交转录请求，返回 transcript_id"""
        url = f"{self.api_base}/v2/transcript"
        payload = {
            "audio_url": audio_url,
            "speech_models": [self.model],
            "language_detection": True,
        }

        async with session.post(
            url,
            json=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"提交转录请求失败 (HTTP {response.status}): {error_text}")
            result = await response.json()
            return result["id"]

    async def _poll_result(self, session: aiohttp.ClientSession,
                           headers: dict, transcript_id: str) -> str:
        """轮询转录结果"""
        url = f"{self.api_base}/v2/transcript/{transcript_id}"
        max_polls = self.timeout // 3 + 1

        for _ in range(max_polls):
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"查询转录结果失败 (HTTP {response.status}): {error_text}")

                result = await response.json()
                status = result.get("status")

                if status == "completed":
                    text = result.get("text", "")
                    if not text:
                        raise Exception("转录完成但结果为空")
                    return text
                elif status == "error":
                    error_msg = result.get("error", "未知错误")
                    raise Exception(f"转录失败: {error_msg}")

                # 还在处理中，等待后重试
                await asyncio.sleep(3)

        raise Exception("转录结果轮询超时")

    async def test_connection(self) -> bool:
        """测试连接（检查API Key是否有效）"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_base}/v2/transcript",
                    headers={"authorization": self.api_key},
                    params={"limit": 1},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    # 200 或 401 可判断 key 有效/无效
                    return response.status == 200
        except Exception:
            return bool(self.api_key)
