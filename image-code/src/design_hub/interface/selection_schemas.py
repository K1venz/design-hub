from pydantic import BaseModel

from design_hub.domain.models import GeneratedImageRecord, UsableRate


class ImageOut(BaseModel):
    id: int
    url: str
    seed: int
    score: int | None
    kept: bool

    @classmethod
    def of(cls, r: GeneratedImageRecord) -> "ImageOut":
        return cls(id=r.id, url=r.url, seed=r.seed, score=r.score, kept=r.kept)


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
