from io import BytesIO

import pytest
from PIL import Image

from design_hub.application.chat.image_ratio import detect_supported_ratio


def _png(width: int, height: int) -> bytes:
    out = BytesIO()
    Image.new("RGB", (width, height)).save(out, format="PNG")
    return out.getvalue()


def _image_with_orientation(
    width: int, height: int, orientation: int, image_format: str
) -> bytes:
    out = BytesIO()
    exif = Image.Exif()
    exif[274] = orientation
    Image.new("RGB", (width, height)).save(out, format=image_format, exif=exif)
    return out.getvalue()


def test_detects_supported_ratios_and_rounding_error() -> None:
    assert detect_supported_ratio(_png(800, 800)) == "1:1"
    assert detect_supported_ratio(_png(800, 1067)) == "3:4"
    assert detect_supported_ratio(_png(900, 1600)) == "9:16"
    assert detect_supported_ratio(_png(1600, 900)) == "16:9"


def test_falls_back_to_square_for_unsupported_or_invalid_image() -> None:
    assert detect_supported_ratio(_png(800, 1000)) == "1:1"
    assert detect_supported_ratio(b"not-an-image") == "1:1"


def test_reads_dimensions_without_decoding_pixels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _png(900, 1600)

    def fail_load(self: Image.Image) -> None:
        raise AssertionError("pixel data must not be decoded")

    monkeypatch.setattr(Image.Image, "load", fail_load)

    assert detect_supported_ratio(data) == "9:16"


@pytest.mark.parametrize("image_format", ["JPEG", "PNG", "WEBP"])
def test_respects_exif_orientation_without_transposing_pixels(
    image_format: str,
) -> None:
    data = _image_with_orientation(1600, 900, 6, image_format)

    assert detect_supported_ratio(data) == "9:16"


@pytest.mark.parametrize("image_format", ["JPEG", "PNG", "WEBP"])
def test_falls_back_for_truncated_image(image_format: str) -> None:
    data = _image_with_orientation(900, 1600, 1, image_format)

    assert detect_supported_ratio(data[:-100]) == "1:1"


def test_falls_back_for_decompression_bomb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)

    assert detect_supported_ratio(_png(10, 10)) == "1:1"
