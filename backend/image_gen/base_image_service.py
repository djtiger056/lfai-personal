"""Personal edition base image service.

Stores one global base image under data/personal/base_image/.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from backend.personal_storage import LEGACY_BASE_IMAGE_DIR, PERSONAL_BASE_IMAGE_DIR

logger = logging.getLogger(__name__)


class BaseImageService:
    ALLOWED_FORMATS = {".jpg", ".jpeg", ".png", ".webp"}
    MAX_FILE_SIZE = 5 * 1024 * 1024
    MAX_READ_SIZE = 10 * 1024 * 1024
    MIN_VALID_SIZE = 10 * 1024
    READ_TIMEOUT = 5.0
    BASE_IMAGE_DIR = "base_image"

    def __init__(self, user_data_manager=None, fallback_image_path: str = "backend/data/default_base_image.jpg"):
        project_root = Path(__file__).resolve().parents[2]
        if user_data_manager is not None and hasattr(user_data_manager, "base_path"):
            self.base_dir = Path(user_data_manager.base_path) / self.BASE_IMAGE_DIR
        else:
            self.base_dir = PERSONAL_BASE_IMAGE_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_base_image()
        fallback_path = Path(fallback_image_path)
        self.fallback_image_path = fallback_path if fallback_path.is_absolute() else project_root / fallback_path

    def _migrate_legacy_base_image(self) -> None:
        if self.base_dir != PERSONAL_BASE_IMAGE_DIR or not LEGACY_BASE_IMAGE_DIR.exists():
            return
        if any(self.base_dir.iterdir()):
            return
        try:
            for file in LEGACY_BASE_IMAGE_DIR.iterdir():
                if file.is_file() and file.suffix.lower() in self.ALLOWED_FORMATS:
                    target = self.base_dir / file.name
                    file.replace(target)
                    logger.info("旧底图已迁移到个人资料目录: %s -> %s", file, target)
                    break
        except Exception as e:
            logger.warning("迁移旧底图失败: %s", e)

    def _get_base_image_dir(self, username: str = "personal") -> Path:
        return self.base_dir

    def _get_mime_type(self, extension: str) -> str:
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(extension.lower(), "application/octet-stream")

    def _find_image_file(self) -> Optional[Path]:
        if not self.base_dir.exists():
            return None
        for file in self.base_dir.iterdir():
            if file.is_file() and file.suffix.lower() in self.ALLOWED_FORMATS:
                return file
        return None

    async def upload_base_image(self, username: str, file_data: bytes, filename: str) -> Dict:
        ext = Path(filename).suffix.lower()
        if ext not in self.ALLOWED_FORMATS:
            raise ValueError("不支持的格式，仅支持 JPEG/PNG/WebP")
        if len(file_data) > self.MAX_FILE_SIZE:
            raise ValueError("文件大小不能超过 5MB")

        self.base_dir.mkdir(parents=True, exist_ok=True)
        for existing_file in self.base_dir.iterdir():
            if existing_file.is_file():
                existing_file.unlink()
        safe_name = f"base{ext}"
        file_path = self.base_dir / safe_name
        file_path.write_bytes(file_data)
        mime_type = self._get_mime_type(ext)
        logger.info("个人版底图已上传: %s (%s bytes)", safe_name, len(file_data))
        return {
            "success": True,
            "filename": safe_name,
            "file_size": len(file_data),
            "mime_type": mime_type,
        }

    async def get_base_image(self, username: str = "personal") -> Optional[Dict]:
        image_file = self._find_image_file()
        if image_file is None:
            return None
        file_data = image_file.read_bytes()
        stat = image_file.stat()
        return {
            "image_data": base64.b64encode(file_data).decode("utf-8"),
            "filename": image_file.name,
            "file_size": stat.st_size,
            "mime_type": self._get_mime_type(image_file.suffix.lower()),
            "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    async def delete_base_image(self, username: str = "personal") -> bool:
        image_files = [
            f for f in self.base_dir.iterdir()
            if f.is_file() and f.suffix.lower() in self.ALLOWED_FORMATS
        ] if self.base_dir.exists() else []
        for image_file in image_files:
            image_file.unlink()
            logger.info("个人版底图已删除: %s", image_file)
        return bool(image_files)

    async def _read_and_encode(self, file_path: Path) -> Optional[str]:
        try:
            return await asyncio.wait_for(self._do_read_and_encode(file_path), timeout=self.READ_TIMEOUT)
        except Exception as e:
            logger.warning("底图读取/编码失败: %s, 错误: %s", file_path, e)
            return None

    async def _do_read_and_encode(self, file_path: Path) -> str:
        file_data = file_path.read_bytes()
        encoded = base64.b64encode(file_data).decode("utf-8")
        return f"data:{self._get_mime_type(file_path.suffix.lower())};base64,{encoded}"

    async def get_base_image_data_url(self, username: str = "personal") -> Optional[str]:
        image_file = self._find_image_file()
        if image_file is None:
            return None
        try:
            if image_file.stat().st_size > self.MAX_READ_SIZE:
                return None
        except OSError:
            return None
        return await self._read_and_encode(image_file)

    async def get_effective_base_image_data_url(self, username: str = "personal") -> Optional[str]:
        data_url = await self.get_base_image_data_url(username)
        if data_url is not None:
            return data_url
        if not self.fallback_image_path.exists():
            return None
        try:
            size = self.fallback_image_path.stat().st_size
        except OSError:
            return None
        if size > self.MAX_READ_SIZE or size < self.MIN_VALID_SIZE:
            return None
        return await self._read_and_encode(self.fallback_image_path)
