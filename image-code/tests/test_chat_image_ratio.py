from io import BytesIO

from PIL import Image

from design_hub.application.chat.image_ratio import detect_supported_ratio


def _png(width: int, height: int) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height)).save(output, format="PNG")
    return output.getvalue()


def test_detects_supported_ratios_and_rounding_error() -> None:
    assert detect_supported_ratio(_png(800, 800)) == "1:1"
    assert detect_supported_ratio(_png(800, 1067)) == "3:4"
    assert detect_supported_ratio(_png(900, 1600)) == "9:16"
    assert detect_supported_ratio(_png(1600, 900)) == "16:9"


def test_falls_back_to_square_for_unsupported_or_invalid_image() -> None:
    assert detect_supported_ratio(_png(800, 1000)) == "1:1"
    assert detect_supported_ratio(b"not-an-image") == "1:1"
