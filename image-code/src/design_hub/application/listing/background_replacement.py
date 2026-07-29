from io import BytesIO

from PIL import Image, UnidentifiedImageError

from design_hub.application.listing.requests import (
    BackgroundSource,
    DescriptionBackground,
)

_SUPPORTED_RATIOS: tuple[tuple[str, float], ...] = (
    ("1:1", 1.0),
    ("3:4", 3 / 4),
    ("4:3", 4 / 3),
    ("9:16", 9 / 16),
    ("16:9", 16 / 9),
)

_DESCRIPTION_TEMPLATE = """任务：只替换图片 1 的背景。

目标背景：
{description}

必须保持不变：
- 商品主体的形状、比例、颜色、材质和结构
- Logo、包装文字、接口、按钮和细小部件
- 商品在画面中的方向和主体身份

允许调整：
- 为适应新背景而产生的自然阴影、反射和环境光
- 商品与背景接触区域的融合效果

禁止：
- 添加、删除或重绘商品部件
- 修改品牌、文字和包装信息
- 在背景中复制商品"""

_REFERENCE_TEMPLATE = """图片 1 是必须保留的商品源图。
图片 2 只作为目标背景和环境光参考。

将图片 1 的商品放入图片 2 的场景中。
{instruction}

必须保持商品形状、比例、颜色、材质、Logo、包装文字和所有结构细节。
可以根据场景生成自然阴影、反射和环境光，但不得把图片 2 中的物体误认为商品主体。"""


def closest_supported_ratio(data: bytes) -> str:
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("图片损坏或无法读取，请重新上传") from exc
    if width <= 0 or height <= 0:
        raise ValueError("图片损坏或无法读取，请重新上传")
    actual = width / height
    return min(
        _SUPPORTED_RATIOS,
        key=lambda item: abs(actual - item[1]),
    )[0]


def compose_background_replace_prompt(background: BackgroundSource) -> str:
    if isinstance(background, DescriptionBackground):
        return _DESCRIPTION_TEMPLATE.format(description=background.description)
    return _REFERENCE_TEMPLATE.format(instruction=background.instruction)
