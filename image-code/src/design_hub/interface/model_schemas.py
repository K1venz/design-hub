from pydantic import BaseModel


class ImageModelCatalogItemOut(BaseModel):
    id: str
    display_name: str
    is_default: bool
