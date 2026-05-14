"""用户底图管理服务

管理每个用户的底图文件（AI 伴侣大头照），用于图生图时保持外观一致性。
每用户最多一张底图，存储在 user_data/{username}/base_image/ 目录下。
"""

import asyncio
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from backend.user.data_manager import UserDataManager

logger = logging.getLogger(__name__)


class BaseImageService:
    """用户底图管理服务"""

    # 允许的图片格式
    ALLOWED_FORMATS = {".jpg", ".jpeg", ".png", ".webp"}
    # 上传文件大小上限：5MB
    MAX_FILE_SIZE = 5 * 1024 * 1024
    # 读取文件大小上限：10MB
    MAX_READ_SIZE = 10 * 1024 * 1024
    # 底图最小有效大小：10KB（低于此值视为占位图，不用于图生图）
    MIN_VALID_SIZE = 10 * 1024
    # 读取/编码超时：5 秒
    READ_TIMEOUT = 5.0
    # 底图存储子目录名
    BASE_IMAGE_DIR = "base_image"

    def __init__(self, user_data_manager: UserDataManager, fallback_image_path: str):
        """
        初始化底图管理服务。

        Args:
            user_data_manager: 用户数据管理器实例，用于获取用户数据目录
            fallback_image_path: 系统兜底图片路径，当用户未上传底图时使用
        """
        self.user_data_manager = user_data_manager
        self.fallback_image_path = fallback_image_path

    def _get_base_image_dir(self, username: str) -> Path:
        """获取用户底图存储目录路径。

        Args:
            username: 用户名

        Returns:
            用户底图目录的 Path 对象 (user_data/{username}/base_image/)
        """
        user_dir = self.user_data_manager._get_user_dir(username)
        return user_dir / self.BASE_IMAGE_DIR

    def _get_mime_type(self, extension: str) -> str:
        """根据文件扩展名返回对应的 MIME 类型。

        Args:
            extension: 文件扩展名（含点号，如 ".jpg"）

        Returns:
            对应的 MIME 类型字符串
        """
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        return mime_map.get(extension.lower(), "application/octet-stream")

    async def upload_base_image(self, username: str, file_data: bytes, filename: str) -> Dict:
        """上传用户底图。

        验证文件格式和大小，清除已有底图后保存新文件（每用户最多一张）。

        Args:
            username: 用户名
            file_data: 图片文件二进制数据
            filename: 原始文件名

        Returns:
            包含上传结果信息的字典

        Raises:
            ValueError: 文件格式不支持或文件大小超限时抛出
        """
        # 1. 验证文件格式
        ext = Path(filename).suffix.lower()
        if ext not in self.ALLOWED_FORMATS:
            raise ValueError(
                f"不支持的格式 '{ext}'，仅支持 JPEG/PNG/WebP（{', '.join(sorted(self.ALLOWED_FORMATS))}）"
            )

        # 2. 验证文件大小
        if len(file_data) > self.MAX_FILE_SIZE:
            raise ValueError(
                f"文件大小 {len(file_data)} 字节超过限制，最大允许 {self.MAX_FILE_SIZE} 字节（5MB）"
            )

        # 3. 确保底图目录存在
        base_image_dir = self._get_base_image_dir(username)
        base_image_dir.mkdir(parents=True, exist_ok=True)

        # 4. 清除已有文件（每用户最多一张）
        for existing_file in base_image_dir.iterdir():
            if existing_file.is_file():
                existing_file.unlink()

        # 5. 保存新文件
        file_path = base_image_dir / filename
        file_path.write_bytes(file_data)

        # 6. 确定 MIME 类型
        mime_type = self._get_mime_type(ext)

        logger.info(f"用户 {username} 上传底图: {filename} ({len(file_data)} bytes, {mime_type})")

        return {
            "success": True,
            "filename": filename,
            "file_size": len(file_data),
            "mime_type": mime_type,
        }

    async def get_base_image(self, username: str) -> Optional[Dict]:
        """获取用户当前底图信息（Base64 编码数据 + 元数据）。

        Args:
            username: 用户名

        Returns:
            包含图片数据和元数据的字典，无底图时返回 None
        """
        # 1. 获取底图目录
        base_image_dir = self._get_base_image_dir(username)

        # 2. 目录不存在则返回 None
        if not base_image_dir.exists():
            return None

        # 3. 查找第一个允许格式的文件
        image_file: Optional[Path] = None
        for file in base_image_dir.iterdir():
            if file.is_file() and file.suffix.lower() in self.ALLOWED_FORMATS:
                image_file = file
                break

        # 4. 无文件则返回 None
        if image_file is None:
            return None

        # 5. 读取文件二进制数据
        file_data = image_file.read_bytes()

        # 6. Base64 编码
        base64_encoded = base64.b64encode(file_data).decode("utf-8")

        # 7. 获取文件 stat 信息
        stat = image_file.stat()

        # 8. 确定 MIME 类型
        mime_type = self._get_mime_type(image_file.suffix.lower())

        return {
            "image_data": base64_encoded,
            "filename": image_file.name,
            "file_size": stat.st_size,
            "mime_type": mime_type,
            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    async def delete_base_image(self, username: str) -> bool:
        """删除用户底图。

        Args:
            username: 用户名

        Returns:
            删除成功返回 True，无底图时返回 False
        """
        # 1. 获取底图目录
        base_image_dir = self._get_base_image_dir(username)

        # 2. 目录不存在则返回 False
        if not base_image_dir.exists():
            return False

        # 3. 查找所有允许格式的文件
        image_files = [
            f for f in base_image_dir.iterdir()
            if f.is_file() and f.suffix.lower() in self.ALLOWED_FORMATS
        ]

        # 4. 无文件则返回 False
        if not image_files:
            return False

        # 5. 删除所有找到的文件（通常最多一个）
        for image_file in image_files:
            image_file.unlink()
            logger.info(f"用户 {username} 删除底图: {image_file.name}")

        return True

    async def _read_and_encode(self, file_path: Path) -> Optional[str]:
        """读取文件并编码为 Data URL，带超时保护。

        Args:
            file_path: 要读取的文件路径

        Returns:
            Data URL 字符串，超时或读取失败时返回 None
        """
        try:
            return await asyncio.wait_for(
                self._do_read_and_encode(file_path),
                timeout=self.READ_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(f"底图编码超时 (>{self.READ_TIMEOUT}s): {file_path}")
            return None
        except Exception as e:
            logger.warning(f"底图读取/编码失败: {file_path}, 错误: {e}")
            return None

    async def _do_read_and_encode(self, file_path: Path) -> str:
        """实际执行文件读取和 Base64 编码。

        Args:
            file_path: 要读取的文件路径

        Returns:
            Data URL 字符串
        """
        file_data = file_path.read_bytes()
        encoded = base64.b64encode(file_data).decode("utf-8")
        ext = file_path.suffix.lower()
        mime_type = self._get_mime_type(ext)
        return f"data:{mime_type};base64,{encoded}"

    async def get_base_image_data_url(self, username: str) -> Optional[str]:
        """获取用户底图的 Data URL 格式字符串。

        读取用户底图文件并转换为 data:image/{type};base64,{data} 格式。

        Args:
            username: 用户名

        Returns:
            Data URL 字符串，无底图或读取失败时返回 None
        """
        # 1. 获取底图目录，检查是否存在
        base_image_dir = self._get_base_image_dir(username)
        if not base_image_dir.exists():
            return None

        # 2. 查找第一个允许格式的文件
        image_file: Optional[Path] = None
        for file in base_image_dir.iterdir():
            if file.is_file() and file.suffix.lower() in self.ALLOWED_FORMATS:
                image_file = file
                break

        # 3. 无文件则返回 None
        if image_file is None:
            return None

        # 4. 检查文件大小 - 超过 MAX_READ_SIZE (10MB) 时记录警告并返回 None
        try:
            file_size = image_file.stat().st_size
        except OSError as e:
            logger.warning(f"底图文件不可读: {image_file}, 错误: {e}")
            return None

        if file_size > self.MAX_READ_SIZE:
            logger.warning(
                f"底图文件过大 ({file_size} bytes > {self.MAX_READ_SIZE} bytes): {image_file}"
            )
            return None

        # 5. 使用超时保护读取文件并编码为 Data URL
        return await self._read_and_encode(image_file)

    async def get_effective_base_image_data_url(self, username: str) -> Optional[str]:
        """获取有效的底图 Data URL（优先用户底图，其次系统兜底图片）。

        选择逻辑：
        1. 优先使用用户上传的底图
        2. 用户无底图时使用系统 fallback 图片
        3. 都不存在时返回 None

        Args:
            username: 用户名

        Returns:
            Data URL 字符串，都不可用时返回 None
        """
        # 1. 优先尝试用户底图
        user_data_url = await self.get_base_image_data_url(username)
        if user_data_url is not None:
            return user_data_url

        # 2. 用户无底图，尝试 fallback 图片
        fallback_path = Path(self.fallback_image_path)
        if not fallback_path.exists():
            logger.warning(f"用户 {username} 无底图，且系统兜底图片不存在: {fallback_path}")
            return None

        # 3. 检查 fallback 文件是否可读
        try:
            fallback_size = fallback_path.stat().st_size
        except OSError as e:
            logger.warning(f"系统兜底图片不可读: {fallback_path}, 错误: {e}")
            return None

        # 4. 检查 fallback 文件大小
        if fallback_size > self.MAX_READ_SIZE:
            logger.warning(
                f"系统兜底图片过大 ({fallback_size} bytes > {self.MAX_READ_SIZE} bytes): {fallback_path}"
            )
            return None

        # 4.1 检查 fallback 文件是否过小（占位图不适合用于图生图）
        if fallback_size < self.MIN_VALID_SIZE:
            logger.warning(
                f"系统兜底图片过小 ({fallback_size} bytes < {self.MIN_VALID_SIZE} bytes)，"
                f"疑似占位图，跳过图生图: {fallback_path}"
            )
            return None

        # 5. 读取 fallback 并编码为 Data URL（带超时保护）
        result = await self._read_and_encode(fallback_path)
        if result is None:
            logger.warning(f"用户 {username} 无底图，且系统兜底图片读取失败: {fallback_path}")
        return result
