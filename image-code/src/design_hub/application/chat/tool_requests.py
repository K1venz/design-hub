"""Chat 专属写工具参数。

Chat 不接收、不推断品类；这里的严格 schema 是文本 LLM 可见的唯一写工具契约，
再显式转换成 Listing 应用请求。
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from design_hub.application.listing.requests import CloneRequest, ListingGenerateRequest

Prompt = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ChatGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_ids: list[str]
    prompt: Prompt
    ratio: str
    n: int | None = None
    plan: dict[str, int] | None = None
    overlay_texts: list[str] | None = None
    modifiers: dict[str, str] = Field(default_factory=dict)

    def to_listing(self) -> ListingGenerateRequest:
        return ListingGenerateRequest(**self.model_dump(), category=None)


class ChatCloneRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_upload_ids: list[str]
    reference_upload_ids: list[str]
    clone_mode: str
    ratio: str
    prompt: str = ""
    modifiers: dict[str, str] = Field(default_factory=dict)

    def to_listing(self) -> CloneRequest:
        return CloneRequest(**self.model_dump(), category=None)
