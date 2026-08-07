from io import BytesIO

import pytest
from PIL import Image

from design_hub.application.showcase.preview import render_showcase_preview


def _image_bytes(*, size: tuple[int, int], format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, (120, 60, 30)).save(output, format=format)
    return output.getvalue()


@pytest.mark.parametrize(
    ("size", "format", "expected_size"),
    [
        ((2400, 1200), "JPEG", (1200, 600)),
        ((800, 400), "PNG", (800, 400)),
    ],
)
def test_showcase_preview_preserves_ratio_without_upscaling(
    size: tuple[int, int],
    format: str,
    expected_size: tuple[int, int],
) -> None:
    preview = render_showcase_preview(_image_bytes(size=size, format=format))

    assert (preview.width, preview.height) == expected_size
    with Image.open(BytesIO(preview.data)) as image:
        assert image.format == "WEBP"
        assert image.size == expected_size


def test_showcase_preview_rejects_malformed_image() -> None:
    with pytest.raises(ValueError, match="^公开预览图无法解码$"):
        render_showcase_preview(b"not-an-image")
