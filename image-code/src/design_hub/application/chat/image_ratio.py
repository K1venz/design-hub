from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

_DEFAULT_RATIO = "1:1"
_MAX_RELATIVE_ERROR = 0.01
_SUPPORTED_RATIOS = {
    "1:1": 1.0,
    "3:4": 3 / 4,
    "9:16": 9 / 16,
    "16:9": 16 / 9,
}


def detect_supported_ratio(data: bytes) -> str:
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = ImageOps.exif_transpose(image).size
    except (UnidentifiedImageError, OSError):
        return _DEFAULT_RATIO
    if width <= 0 or height <= 0:
        return _DEFAULT_RATIO
    actual = width / height
    ratio, expected = min(
        _SUPPORTED_RATIOS.items(),
        key=lambda item: abs(actual - item[1]) / item[1],
    )
    relative_error = abs(actual - expected) / expected
    return ratio if relative_error <= _MAX_RELATIVE_ERROR else _DEFAULT_RATIO
