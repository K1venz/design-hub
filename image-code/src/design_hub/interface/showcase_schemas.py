from pydantic import BaseModel

from design_hub.ports.media_url_signer import MediaUrlSigner
from design_hub.ports.showcase import PublicShowcaseItem

_CATEGORY_LABELS = {
    "FOOD": "食品",
    "FASHION": "服装",
    "BEAUTY": "美妆",
    "SHOES": "鞋类",
    "DIGITAL": "数码",
}


class RecipeOut(BaseModel):
    category: str
    ratio: str
    plan: dict[str, int]
    styling: str
    modifiers: dict[str, str]

    @classmethod
    def of(cls, item: PublicShowcaseItem) -> "RecipeOut":
        return cls(
            category=item.category,
            ratio=item.ratio,
            plan=dict(item.plan),
            styling=item.prompt,
            modifiers=dict(item.modifiers),
        )


class ShowcaseItemOut(BaseModel):
    image_id: int
    url: str
    image_type: str
    caption: str
    prompt: str
    download_allowed: bool
    width: int
    height: int
    recipe: RecipeOut

    @classmethod
    def of(
        cls,
        item: PublicShowcaseItem,
        signer: MediaUrlSigner,
    ) -> "ShowcaseItemOut":
        category = _CATEGORY_LABELS.get(item.category, item.category)
        return cls(
            image_id=item.image_id,
            url=signer.generated_url(item.preview_key),
            image_type=item.image_type,
            caption=f"{category} · {item.image_type}",
            prompt=item.prompt,
            download_allowed=item.download_allowed,
            width=item.width,
            height=item.height,
            recipe=RecipeOut.of(item),
        )


class ShowcaseDownloadOut(BaseModel):
    url: str
