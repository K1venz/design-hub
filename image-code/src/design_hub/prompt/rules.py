from math import gcd

from ..domain.enums import ModelName

# 法则 10：即梦/MJ 风模型用 --ar，GPT/Seedream/千问 用中文比例
_TAG_STYLE_MODELS = {ModelName.WANXIANG_27, ModelName.LINGDONG_2}


def format_ratio(size: tuple[int, int], model: ModelName) -> str:
    width, height = size
    divisor = gcd(width, height)
    ratio_w, ratio_h = width // divisor, height // divisor
    if model in _TAG_STYLE_MODELS:
        return f"--ar {ratio_w}:{ratio_h}"
    orientation = "竖版" if height >= width else "横版"
    return f"{ratio_w}:{ratio_h}{orientation}"


def typography_block(copy_text: str | None) -> str:
    # 法则 6：文字/版式信息独立成段
    if not copy_text:
        return ""
    return f"\n【文字排版】{copy_text}（内容+位置+字号+字重+字体+颜色独立成段）"
