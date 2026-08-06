from pydantic import BaseModel

from design_hub.domain.tasking import RenderTier


class ImageRenderTierOut(BaseModel):
    id: RenderTier
    label: str
    ratios: list[str]
    supports_references: bool


class ImageModelCapabilitiesOut(BaseModel):
    render_tiers: list[ImageRenderTierOut]
    max_count: int


class ModelCatalogItemOut(BaseModel):
    id: str
    display_name: str
    is_default: bool
    image_capabilities: ImageModelCapabilitiesOut | None = None
