import asyncio
import subprocess
import tempfile
import os
from typing import Optional, Dict, Any, Union
from .config import ASRConfig
from .providers.siliconflow_asr import SiliconFlowASRProvider
from .providers.qwen_asr import QwenASRProvider
from .providers.assemblyai_asr import AssemblyAIASRProvider


class ASRManager:
    """ASR语音识别管理器"""

    def __init__(self, config: ASRConfig):
        self.config = config
        self.provider = self._create_provider()

    def _create_provider(self):
        """创建ASR提供商实例"""
        if self.config.provider == "siliconflow":
            return SiliconFlowASRProvider(self.config.siliconflow.dict())
        elif self.config.provider == "qwen":
            return QwenASRProvider(self.config.qwen.dict())
        elif self.config.provider == "assemblyai":
            return AssemblyAIASRProvider(self.config.assemblyai.dict())
        else:
            raise ValueError(f"不支持的ASR提供商: {self.config.provider}")

    def update_config(self, config: Union[ASRConfig, Dict[str, Any]]):
        """更新配置并重建提供商"""
        if isinstance(config, ASRConfig):
            self.config = config
        else:
            self.config = ASRConfig(**config)
        self.provider = self._create_provider()

    @staticmethod
    def _is_amr_audio(audio_data: bytes, filename: str = "") -> bool:
        """检测是否为AMR格式音频"""
        # AMR文件魔数: #!AMR\n (0x23 0x21 0x41 0x4d 0x52 0x0a)
        if audio_data[:6] == b'#!AMR\n':
            return True
        if audio_data[:5] == b'#!AMR':
            return True
        if filename.lower().endswith('.amr'):
            return True
        return False

    @staticmethod
    async def _convert_amr_to_mp3(audio_data: bytes) -> bytes:
        """使用ffmpeg将AMR音频转换为MP3格式"""
        with tempfile.NamedTemporaryFile(suffix='.amr', delete=False) as amr_file:
            amr_file.write(audio_data)
            amr_path = amr_file.name

        mp3_path = amr_path.replace('.amr', '.mp3')
        try:
            proc = await asyncio.create_subprocess_exec(
                'ffmpeg', '-y', '-i', amr_path,
                '-ar', '16000', '-ac', '1', '-b:a', '64k',
                mp3_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                raise Exception(f"ffmpeg转换失败: {stderr.decode('utf-8', errors='replace')}")

            with open(mp3_path, 'rb') as f:
                return f.read()
        finally:
            for p in (amr_path, mp3_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    async def transcribe_audio(self, audio_data: bytes, filename: str = "audio.mp3") -> str:
        """
        语音转文本（自动处理AMR格式转换）

        Args:
            audio_data: 音频文件的二进制数据
            filename: 文件名

        Returns:
            识别结果文本
        """
        try:
            # 检测AMR格式并自动转换
            if self._is_amr_audio(audio_data, filename):
                print(f"[ASR] 检测到AMR格式音频 ({len(audio_data)} bytes)，正在转换为MP3...")
                audio_data = await self._convert_amr_to_mp3(audio_data)
                filename = "audio.mp3"
                print(f"[ASR] 转换完成，MP3大小: {len(audio_data)} bytes")

            return await self.provider.transcribe(audio_data, filename)
        except Exception as e:
            print(f"语音识别失败: {str(e)}")
            raise Exception(f"语音识别失败: {str(e)}")

    async def test_connection(self) -> bool:
        """测试连接"""
        try:
            return await self.provider.test_connection()
        except Exception as e:
            print(f"测试连接失败: {str(e)}")
            return False
