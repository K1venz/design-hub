from pydantic import BaseModel

from design_hub.config.showcase import ShowcaseEntry
from design_hub.ports.media_url_signer import MediaUrlSigner


class ShowcaseItemOut(BaseModel):
    """GET /showcase 列表项：现签 url + 图型 + 首页说明（公开，无用户数据）。"""

    url: str
    image_type: str
    caption: str

    @classmethod
    def of(cls, entry: ShowcaseEntry, signer: MediaUrlSigner) -> "ShowcaseItemOut":
        return cls(
            url=signer.generated_url(entry.key),
            image_type=entry.image_type,
            caption=entry.caption,
        )
