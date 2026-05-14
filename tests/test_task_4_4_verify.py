"""Verification tests for task 4.4: Data URL conversion logic."""

import asyncio
import base64
from pathlib import Path

import pytest

from backend.user.data_manager import UserDataManager
from backend.image_gen.base_image_service import BaseImageService


@pytest.fixture
def tmp_user_data(tmp_path):
    """Create a temporary user data directory."""
    return UserDataManager(base_path=str(tmp_path))


@pytest.fixture
def fallback_path(tmp_path):
    """Return a fallback image path."""
    return str(tmp_path / "fallback.jpg")


@pytest.fixture
def service(tmp_user_data, fallback_path):
    """Create a BaseImageService instance with temp directories."""
    return BaseImageService(tmp_user_data, fallback_path)


class TestGetBaseImageDataUrl:
    """Tests for get_base_image_data_url method."""

    def test_returns_none_when_no_directory(self, service):
        """No base_image directory -> returns None."""
        result = asyncio.run(service.get_base_image_data_url("testuser"))
        assert result is None

    def test_returns_none_when_directory_empty(self, service):
        """Directory exists but no image files -> returns None."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        result = asyncio.run(service.get_base_image_data_url("testuser"))
        assert result is None

    def test_returns_data_url_for_jpeg(self, service):
        """Returns correct data URL for a JPEG file."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        image_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        (base_dir / "avatar.jpg").write_bytes(image_data)

        result = asyncio.run(service.get_base_image_data_url("testuser"))

        expected_b64 = base64.b64encode(image_data).decode("utf-8")
        assert result == f"data:image/jpeg;base64,{expected_b64}"

    def test_returns_data_url_for_png(self, service):
        """Returns correct data URL for a PNG file."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        (base_dir / "photo.png").write_bytes(image_data)

        result = asyncio.run(service.get_base_image_data_url("testuser"))

        expected_b64 = base64.b64encode(image_data).decode("utf-8")
        assert result == f"data:image/png;base64,{expected_b64}"

    def test_returns_data_url_for_webp(self, service):
        """Returns correct data URL for a WebP file."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        image_data = b"RIFF" + b"\x00" * 60
        (base_dir / "img.webp").write_bytes(image_data)

        result = asyncio.run(service.get_base_image_data_url("testuser"))

        expected_b64 = base64.b64encode(image_data).decode("utf-8")
        assert result == f"data:image/webp;base64,{expected_b64}"

    def test_returns_none_when_file_exceeds_max_read_size(self, service):
        """File > 10MB -> returns None with warning."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        # Create a file just over 10MB
        large_data = b"\x00" * (10 * 1024 * 1024 + 1)
        (base_dir / "big.jpg").write_bytes(large_data)

        result = asyncio.run(service.get_base_image_data_url("testuser"))
        assert result is None


class TestGetEffectiveBaseImageDataUrl:
    """Tests for get_effective_base_image_data_url method."""

    def test_returns_user_image_when_available(self, service):
        """User has base image -> returns user's data URL."""
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        image_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        (base_dir / "avatar.jpg").write_bytes(image_data)

        result = asyncio.run(service.get_effective_base_image_data_url("testuser"))

        expected_b64 = base64.b64encode(image_data).decode("utf-8")
        assert result == f"data:image/jpeg;base64,{expected_b64}"

    def test_returns_fallback_when_no_user_image(self, service, tmp_path):
        """No user image, fallback exists -> returns fallback data URL."""
        fallback_path = Path(service.fallback_image_path)
        fallback_data = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        fallback_path.write_bytes(fallback_data)

        result = asyncio.run(service.get_effective_base_image_data_url("testuser"))

        expected_b64 = base64.b64encode(fallback_data).decode("utf-8")
        assert result == f"data:image/jpeg;base64,{expected_b64}"

    def test_returns_none_when_no_user_image_and_no_fallback(self, service):
        """No user image, no fallback -> returns None."""
        result = asyncio.run(service.get_effective_base_image_data_url("testuser"))
        assert result is None

    def test_returns_none_when_fallback_exceeds_max_size(self, service):
        """Fallback > 10MB -> returns None."""
        fallback_path = Path(service.fallback_image_path)
        large_data = b"\x00" * (10 * 1024 * 1024 + 1)
        fallback_path.write_bytes(large_data)

        result = asyncio.run(service.get_effective_base_image_data_url("testuser"))
        assert result is None

    def test_prefers_user_image_over_fallback(self, service):
        """User image takes priority over fallback."""
        # Set up user image
        base_dir = service._get_base_image_dir("testuser")
        base_dir.mkdir(parents=True, exist_ok=True)
        user_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        (base_dir / "user.png").write_bytes(user_data)

        # Set up fallback
        fallback_path = Path(service.fallback_image_path)
        fallback_data = b"\xff\xd8\xff\xe0" + b"\x00" * 50
        fallback_path.write_bytes(fallback_data)

        result = asyncio.run(service.get_effective_base_image_data_url("testuser"))

        # Should be user's PNG, not fallback JPEG
        expected_b64 = base64.b64encode(user_data).decode("utf-8")
        assert result == f"data:image/png;base64,{expected_b64}"
