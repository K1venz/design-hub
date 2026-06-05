from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from design_hub.ports.listing_query import ListingJobDetail, ListingJobSummary


def _img_url(base_url: str, key: str) -> str:
    """key → 可访问 url（复用 ISSUE-0029：{IMAGE_PUBLIC_BASE_URL}/img/{key}）。"""
    return f"{base_url}/img/{key}"


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
    def of(cls, s: ListingJobSummary, base_url: str) -> "ListingJobSummaryOut":
        return cls(
            job_id=s.job_id,
            status=s.status,
            platform=s.platform,
            ratio=s.ratio,
            n=s.n,
            total_cost=s.total_cost,
            created_at=s.created_at,
            first_image_url=(_img_url(base_url, s.first_image_key) if s.first_image_key else None),
            image_count=s.image_count,
        )


class ListingImageOut(BaseModel):
    url: str
    seed: int
    cost: Decimal
    status: str


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

    @classmethod
    def of(cls, d: ListingJobDetail, base_url: str) -> "ListingJobDetailOut":
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
                    url=_img_url(base_url, im.image_key),
                    seed=im.seed,
                    cost=im.cost,
                    status=im.status,
                )
                for im in d.images
            ],
            input_urls=[_img_url(base_url, k) for k in d.input_keys],
        )
