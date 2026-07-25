# gpt-image-2 1K 档请求尺寸；非方形长边固定 1536，并保持用户选择的精确比例。
# 其余比例 → fail-fast（ISSUE-0024 缺陷③：不收录超集）。
_RATIO_TO_SIZE: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "3:4": (1152, 1536),
    "4:3": (1536, 1152),
    "9:16": (864, 1536),
    "16:9": (1536, 864),
}


def ratio_to_size(ratio: str) -> tuple[int, int]:
    try:
        return _RATIO_TO_SIZE[ratio]
    except KeyError:
        options = " / ".join(_RATIO_TO_SIZE)
        raise ValueError(f"不支持的比例：{ratio}（可选 {options}）") from None
