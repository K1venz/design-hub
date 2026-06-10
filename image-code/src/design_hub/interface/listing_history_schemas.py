from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from design_hub.ports.listing_query import ListingJobDetail, ListingJobSummary
from design_hub.ports.media_url_signer import MediaUrlSigner


class ListingJobSummaryOut(BaseModel):
    job_id: str
    status: str
    platform: str | None
    ratio: str
    n: int
    total_cost: Decimal
    created_at: datetime
    first_image_url: str | None
    image_count: int

    @classmethod
    def of(cls, s: ListingJobSummary, signer: MediaUrlSigner) -> "ListingJobSummaryOut":
        return cls(
            job_id=s.job_id,
            status=s.status,
            platform=s.platform,
            ratio=s.ratio,
            n=s.n,
            total_cost=s.total_cost,
            created_at=s.created_at,
            first_image_url=(
                signer.generated_url(s.first_image_key) if s.first_image_key else None
            ),
            image_count=s.image_count,
        )


class ListingImageOut(BaseModel):
    url: str
    seed: int
    cost: Decimal
    status: str
    image_type: str | None = None  # 白底|场景|卖点；None=单图流


class ListingJobDetailOut(BaseModel):
    job_id: str
    prompt: str
    modifiers: dict[str, str]
    platform: str | None
    ratio: str
    size: str
    n: int
    status: str
    total_cost: Decimal
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    images: list[ListingImageOut]
    input_urls: list[str]
    clone_mode: str | None = None  # 参考风格|高度复刻；None=非复刻（历史「复刻」徽标）
    input_roles: list[str | None] = []  # product|reference，与 input_urls 同序；None=旧数据

    @classmethod
    def of(cls, d: ListingJobDetail, signer: MediaUrlSigner) -> "ListingJobDetailOut":
        return cls(
            job_id=d.job_id,
            prompt=d.prompt,
            modifiers=d.modifiers,
            platform=d.platform,
            ratio=d.ratio,
            size=d.size,
            n=d.n,
            status=d.status,
            total_cost=d.total_cost,
            error=d.error,
            created_at=d.created_at,
            completed_at=d.completed_at,
            images=[
                ListingImageOut(
                    url=signer.generated_url(im.image_key),
                    seed=im.seed,
                    cost=im.cost,
                    status=im.status,
                    image_type=im.image_type,
                )
                for im in d.images
            ],
            input_urls=[signer.upload_url(k) for k in d.input_keys],
            clone_mode=d.clone_mode,
            input_roles=list(d.input_roles) or [None] * len(d.input_keys),
        )
