"""Tests for BaseImageService get_base_image and delete_base_image methods."""

import asyncio
import base64
import tempfile
from pathlib import Path

import pytest

from backend.user.data_manager import UserDataManager
from backend.image_gen.base_image_service import BaseImageService


@pytest.fixture
def tmp_user_data(tmp_path):
    """Create a temporary user data directory."""
    return UserDataManager(base_path=str(tmp_path))


@pytest.fixture
def service(tmp_user_data, tmp_path):
    """Create a BaseImageService instance with temp directories."""
    fallback_path = str(tmp_path / "fallback.jpg")
    return BaseImageService(tmp_user_data, fallback_path)


class TestGetBaseImage:
    """Tests for get_base_image method."""

    def test_returns_none_when_no_directory(self, service):
        """No base_image directory -> returns None."""
        result = asyncio.run(service.get_base_image("testuser"))
        assert result is None

    def test_returns_none_when_directory_empty(self, service):
        """Directory exists but no image files -> returns None."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        result = asyncio.run(service.get_base_image("testuser"))
        assert result is None

    def test_returns_none_when_only_unsupported_files(self, service):
        """Directory has files but none with allowed extensions -> returns None."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "readme.txt").write_text("not an image")
        result = asyncio.run(service.get_base_image("testuser"))
        assert result is None

    def test_returns_image_data_for_jpeg(self, service):
        """Returns correct Base64 data and metadata for a JPEG file."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        image_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # fake JPEG
        (base_dir / "avatar.jpg").write_bytes(image_data)

        result = asyncio.run(service.get_base_image("testuser"))

        assert result is not None
        assert result["filename"] == "avatar.jpg"
        assert result["file_size"] == len(image_data)
        assert result["mime_type"] == "image/jpeg"
        assert result["image_data"] == base64.b64encode(image_data).decode("utf-8")
        assert "last_modified" in result

    def test_returns_image_data_for_png(self, service):
        """Returns correct metadata for a PNG file."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        (base_dir / "photo.png").write_bytes(image_data)

        result = asyncio.run(service.get_base_image("testuser"))

        assert result is not None
        assert result["filename"] == "photo.png"
        assert result["mime_type"] == "image/png"
        assert result["file_size"] == len(image_data)

    def test_returns_image_data_for_webp(self, service):
        """Returns correct metadata for a WebP file."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        image_data = b"RIFF" + b"\x00" * 60
        (base_dir / "img.webp").write_bytes(image_data)

        result = asyncio.run(service.get_base_image("testuser"))

        assert result is not None
        assert result["filename"] == "img.webp"
        assert result["mime_type"] == "image/webp"


class TestDeleteBaseImage:
    """Tests for delete_base_image method."""

    def test_returns_false_when_no_directory(self, service):
        """No base_image directory -> returns False."""
        result = asyncio.run(service.delete_base_image("testuser"))
        assert result is False

    def test_returns_false_when_directory_empty(self, service):
        """Directory exists but no image files -> returns False."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        result = asyncio.run(service.delete_base_image("testuser"))
        assert result is False

    def test_returns_false_when_only_unsupported_files(self, service):
        """Directory has non-image files -> returns False."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "notes.txt").write_text("not an image")
        result = asyncio.run(service.delete_base_image("testuser"))
        assert result is False
        # Non-image file should still exist
        assert (base_dir / "notes.txt").exists()

    def test_deletes_image_and_returns_true(self, service):
        """Deletes the image file and returns True."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        image_file = base_dir / "avatar.jpg"
        image_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        result = asyncio.run(service.delete_base_image("testuser"))

        assert result is True
        assert not image_file.exists()

    def test_get_returns_none_after_delete(self, service):
        """After deletion, get_base_image returns None."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        (base_dir / "avatar.png").write_bytes(b"\x89PNG" + b"\x00" * 50)

        # Delete
        asyncio.run(service.delete_base_image("testuser"))

        # Verify get returns None
        result = asyncio.run(service.get_base_image("testuser"))
        assert result is None
