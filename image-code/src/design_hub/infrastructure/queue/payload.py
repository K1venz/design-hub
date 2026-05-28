from typing import Any

from design_hub.domain.enums import Category, Style, SubScene, TemplateFamily, Tier
from design_hub.domain.models import Brief


def brief_to_payload(brief: Brief) -> dict[str, Any]:
    """Brief → JSON 友好载荷（不含参考图字节，异步流程经独立上传引用）。"""
    return {
        "customer": brief.customer,
        "subscene": brief.subscene.value,
        "family": brief.family.value,
        "tier": brief.tier.value,
        "style": brief.style.value,
        "category": brief.category.value,
        "width": brief.size[0],
        "height": brief.size[1],
        "n": brief.n,
        "copy_text": brief.copy_text,
        "taboo": brief.taboo,
        "product_desc": brief.product_desc,
        "brand_name": brief.brand_name,
    }


def payload_to_brief(payload: dict[str, Any]) -> Brief:
    return Brief(
        customer=payload["customer"],
        subscene=SubScene(payload["subscene"]),
        family=TemplateFamily(payload["family"]),
        tier=Tier(payload["tier"]),
        style=Style(payload["style"]),
        category=Category(payload["category"]),
        size=(payload["width"], payload["height"]),
        n=payload["n"],
        copy_text=payload.get("copy_text"),
        taboo=payload.get("taboo"),
        product_desc=payload.get("product_desc"),
        brand_name=payload.get("brand_name"),
    )
