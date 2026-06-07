import base64
from io import BytesIO

from PIL import Image

from backend.image_gen.providers.gpt_image_edits import GptImageEditsProvider


def _png_data_url() -> str:
    image = Image.new("RGBA", (8, 8), (255, 0, 0, 128))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def test_resolve_size_uses_ratio_and_resolution():
    provider = GptImageEditsProvider({
        "ratio": "9:16",
        "resolution": "2k",
    })

    assert provider._resolve_size() == "1440x2560"


def test_resolve_size_allows_explicit_size_override():
    provider = GptImageEditsProvider({
        "ratio": "1:1",
        "resolution": "4k",
        "size": "1024x1536",
    })

    assert provider._resolve_size() == "1024x1536"


def test_decode_data_url_prepares_upload_metadata():
    provider = GptImageEditsProvider({})

    decoded = provider._decode_data_url(_png_data_url(), 0)

    assert decoded is not None
    image_bytes, filename, mime_type = decoded
    assert filename == "image_0.png"
    assert mime_type == "image/png"
    assert image_bytes.startswith(b"\x89PNG")


def test_convert_to_jpeg_flattens_alpha_channel():
    provider = GptImageEditsProvider({})
    decoded = provider._decode_data_url(_png_data_url(), 0)

    assert decoded is not None
    converted = provider._convert_to_jpeg(decoded[0])

    assert converted is not None
    with Image.open(BytesIO(converted)) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
