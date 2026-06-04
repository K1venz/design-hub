from design_hub.domain.errors import DomainError

# gpt-image-2 仅支持三种尺寸；非方形比例归并到最接近的竖/横版。
# 覆盖 ISSUE-0021 确认的比例集 1:1 / 3:4 / 9:16 / 16:9（9:16→竖版、16:9→横版）。
_RATIO_TO_SIZE: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "3:4": (1024, 1536),
    "9:16": (1024, 1536),
    "4:3": (1536, 1024),
    "16:9": (1536, 1024),
}


def ratio_to_size(ratio: str) -> tuple[int, int]:
    try:
        return _RATIO_TO_SIZE[ratio]
    except KeyError:
        raise DomainError(f"不支持的比例：{ratio}") from None
