from pydantic import BaseModel

from design_hub.config.showcase import Recipe, ShowcaseEntry
from design_hub.ports.media_url_signer import MediaUrlSigner


class RecipeOut(BaseModel):
    """做同款可复用配方（ISSUE-0053）：图型配比/比例/风格描述/modifiers/品类。

    仅用户可复用输入；**不含内部卡 prompt、overlay_texts、uploads**（口径铁律）。
    """

    category: str
    ratio: str
    plan: dict[str, int]  # 图型配比：白底/场景/卖点 → 张数
    styling: str  # 风格描述（listing_job.prompt）
    modifiers: dict[str, str]  # region/language/platform

    @classmethod
    def of(cls, recipe: Recipe) -> "RecipeOut":
        return cls(
            category=recipe.category,
            ratio=recipe.ratio,
            plan=dict(recipe.plan),
            styling=recipe.styling,
            modifiers=dict(recipe.modifiers),
        )


class ShowcaseItemOut(BaseModel):
    """GET /showcase 列表项：现签 url + 图型 + 首页说明 + 做同款配方（公开，无用户数据）。"""

    url: str
    image_type: str
    caption: str
    recipe: RecipeOut

    @classmethod
    def of(cls, entry: ShowcaseEntry, signer: MediaUrlSigner) -> "ShowcaseItemOut":
        return cls(
            url=signer.generated_url(entry.key),
            image_type=entry.image_type,
            caption=entry.caption,
            recipe=RecipeOut.of(entry.recipe),
        )
