from io import BytesIO

from PIL import Image, UnidentifiedImageError

_DEFAULT_RATIO = "1:1"
_MAX_RELATIVE_ERROR = 0.01
_EXIF_ORIENTATION = 274
_ORIENTATIONS_THAT_SWAP_DIMENSIONS = frozenset({5, 6, 7, 8})
_SUPPORTED_RATIOS = {
    "1:1": 1 / 1,
    "3:4": 3 / 4,
    "4:3": 4 / 3,
    "9:16": 9 / 16,
    "16:9": 16 / 9,
}


def _jpeg_has_end_marker(data: bytes) -> bool:
    return data.rstrip(b"\x00\t\n\r ").endswith(b"\xff\xd9")


def detect_supported_ratio(data: bytes) -> str:
    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
            raw_exif = image.info.get("exif")
            image.verify()
        if image_format == "JPEG" and not _jpeg_has_end_marker(data):
            return _DEFAULT_RATIO
        exif = Image.Exif()
        if raw_exif is not None:
            if not isinstance(raw_exif, bytes):
                raise ValueError("invalid EXIF payload")
            exif.load(raw_exif)
        orientation = exif.get(_EXIF_ORIENTATION)
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
    ):
        return _DEFAULT_RATIO
    if orientation in _ORIENTATIONS_THAT_SWAP_DIMENSIONS:
        width, height = height, width
    if width <= 0 or height <= 0:
        return _DEFAULT_RATIO
    actual = width / height
    ratio, expected = min(
        _SUPPORTED_RATIOS.items(),
        key=lambda item: abs(actual - item[1]) / item[1],
    )
    relative_error = abs(actual - expected) / expected
    return ratio if relative_error <= _MAX_RELATIVE_ERROR else _DEFAULT_RATIO
