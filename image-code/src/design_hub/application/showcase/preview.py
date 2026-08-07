from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

_MAX_EDGE = 1200
_WEBP_QUALITY = 82


@dataclass(frozen=True)
class ShowcasePreview:
    data: bytes
    width: int
    height: int


def render_showcase_preview(source: bytes) -> ShowcasePreview:
    try:
        with Image.open(BytesIO(source)) as opened:
            image = ImageOps.exif_transpose(opened)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGB")
            image.thumbnail(
                (_MAX_EDGE, _MAX_EDGE),
                Image.Resampling.LANCZOS,
            )
            output = BytesIO()
            image.save(
                output,
                format="WEBP",
                quality=_WEBP_QUALITY,
                method=6,
            )
            width, height = image.size
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("公开预览图无法解码") from exc
    return ShowcasePreview(
        data=output.getvalue(),
        width=width,
        height=height,
    )
