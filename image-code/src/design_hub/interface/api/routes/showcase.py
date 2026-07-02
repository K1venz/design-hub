"""公开首页「成果展示区」（无鉴权）。

清单打进代码库（config/showcase.py，人工精选）；桶保持私有，对每项现签
预签名 url。除 key/图型/说明外不含任何用户数据或 prompt。
"""

from fastapi import APIRouter

from design_hub.config.showcase import SHOWCASE_ENTRIES
from design_hub.interface.api.deps import MediaSignerDep
from design_hub.interface.showcase_schemas import ShowcaseItemOut

router = APIRouter(tags=["showcase"])


@router.get("/showcase")
async def showcase(signer: MediaSignerDep) -> list[ShowcaseItemOut]:
    """公开成果展示：精选出图现签 url，按清单序返回；清单空 → []。"""
    return [ShowcaseItemOut.of(entry, signer) for entry in SHOWCASE_ENTRIES]
