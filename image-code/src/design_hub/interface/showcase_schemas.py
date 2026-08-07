from pydantic import BaseModel

from design_hub.ports.media_url_signer import MediaUrlSigner
from design_hub.ports.showcase import PublicShowcaseItem, PublicShowcaseRecipe

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
    def of(
        cls,
        recipe: PublicShowcaseRecipe,
        prompt: str,
    ) -> "RecipeOut":
        return cls(
            category=recipe.category,
            ratio=recipe.ratio,
            plan=dict(recipe.plan),
            styling=prompt,
            modifiers=dict(recipe.modifiers),
        )


class ShowcaseItemOut(BaseModel):
    image_id: int
    url: str
    image_type: str | None
    caption: str
    prompt: str
    download_allowed: bool
    width: int
    height: int
    recipe: RecipeOut | None

    @classmethod
    def of(
        cls,
        item: PublicShowcaseItem,
        signer: MediaUrlSigner,
    ) -> "ShowcaseItemOut":
        image_type = item.image_type or "单图"
        category = (
            _CATEGORY_LABELS.get(item.recipe.category, item.recipe.category)
            if item.recipe is not None
            else None
        )
        return cls(
            image_id=item.image_id,
            url=signer.generated_url(item.preview_key),
            image_type=item.image_type,
            caption=(f"{category} · {image_type}" if category else image_type),
            prompt=item.prompt,
            download_allowed=item.download_allowed,
            width=item.width,
            height=item.height,
            recipe=(
                RecipeOut.of(item.recipe, item.prompt)
                if item.recipe is not None
                else None
            ),
        )


class ShowcaseDownloadOut(BaseModel):
    url: str
