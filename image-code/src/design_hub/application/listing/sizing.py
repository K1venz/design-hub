# gpt-image-2 支持的尺寸；比例集对齐 ISSUE-0021 用户确认值（1:1 / 3:4 / 9:16 / 16:9）。
# 非方形归并到竖/横版。其余比例 → fail-fast（ISSUE-0024 缺陷③：不收录超集）。
_RATIO_TO_SIZE: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "3:4": (1024, 1536),
    "9:16": (1024, 1536),
    "16:9": (1536, 1024),
}


def ratio_to_size(ratio: str) -> tuple[int, int]:
    try:
        return _RATIO_TO_SIZE[ratio]
    except KeyError:
        raise ValueError(f"不支持的比例：{ratio}") from None
