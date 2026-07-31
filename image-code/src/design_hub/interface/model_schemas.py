from pydantic import BaseModel


class ModelCatalogItemOut(BaseModel):
    id: str
    display_name: str
    is_default: bool
