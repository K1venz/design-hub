from collections.abc import Sequence

from design_hub.domain.models import Brief, BriefRecord, GenerationConfig


def compose_brief(
    *,
    customer_name: str,
    brief: BriefRecord | None,
    config: GenerationConfig,
    reference_images: Sequence[bytes],
) -> Brief:
    """合成域 Brief（D2 方案①）= 需求单(copy_text/taboo) + 出图配置 + 选中素材字节。

    纯映射、无 I/O：family/品类/子场景/档位/尺寸/风格/n 取自出图配置（单值）；
    copy_text/taboo 取自需求单（可缺）；reference_images 非空时 pipeline 自动走图生图 EDIT。
    product_desc/brand_name 不在 D2 出图配置内，置 None。
    """
    return Brief(
        customer=customer_name,
        subscene=config.subscene,
        family=config.family,
        tier=config.tier,
        style=config.style,
        category=config.category,
        size=config.size,
        n=config.n,
        copy_text=brief.copy_text if brief is not None else None,
        taboo=brief.taboo if brief is not None else None,
        product_desc=None,
        brand_name=None,
        reference_images=tuple(reference_images),
    )
