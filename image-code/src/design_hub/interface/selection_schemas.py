from pydantic import BaseModel

from design_hub.domain.models import GeneratedImageRecord, UsableRate
from design_hub.ports.media_url_signer import MediaUrlSigner


class ImageOut(BaseModel):
    id: int
    url: str
    seed: int
    score: int | None
    kept: bool

    @classmethod
    def of(cls, r: GeneratedImageRecord, signer: MediaUrlSigner) -> "ImageOut":
        # r.url 实为 image_key；经签名器解析成可访问 url（ISSUE-0034）
        return cls(
            id=r.id, url=signer.generated_url(r.url), seed=r.seed, score=r.score, kept=r.kept
        )


class ScoreRequest(BaseModel):
    # 分值范围校验放在 SelectionService(非法→ValueError→400)，与 PRD「400 分值非法」一致
    score: int


class KeepRequest(BaseModel):
    kept: bool


class UsableRateOut(BaseModel):
    usable: int
    total: int
    rate: float

    @classmethod
    def of(cls, r: UsableRate) -> "UsableRateOut":
        return cls(usable=r.usable, total=r.total, rate=r.rate)
