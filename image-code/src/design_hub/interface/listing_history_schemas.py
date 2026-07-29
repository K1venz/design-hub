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
    edit_mode: str | None = None  # delta|full；None=原生单（列表 ✎ 徽标，ISSUE-0040）
    category: str | None = None  # 品类档（ISSUE-0060）；None=编辑单/旧数据
    operation_type: str | None = None

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
            edit_mode=s.edit_mode,
            category=s.category,
            operation_type=s.operation_type,
        )


class ListingSubmissionOut(BaseModel):
    job_id: str
    queue_state: str
    estimated_wait_seconds: int


class ListingImageOut(BaseModel):
    url: str
    # 可寻址 handle（ISSUE-0040 E-δ：二次编辑唯一身份源；SSE 不下发、读模型独有）
    image_key: str
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
    category: str | None = None  # 品类档（ISSUE-0060）：配方复用回填；None=编辑单/旧数据
    clone_mode: str | None = None  # 参考风格|完全复刻；None=非复刻（历史「复刻」徽标）
    input_roles: list[str | None] = []  # product|reference，与 input_urls 同序；None=旧数据
    # 二次编辑（ISSUE-0040）：迭代链回显（None=非编辑单）
    parent_job_id: str | None = None
    edit_mode: str | None = None  # delta|full（详情「✎ 微调/重做」徽标 + 回溯链接）
    source_image_url: str | None = None  # 「改自这张」只读回显（签名 url）
    source_image_type: str | None = None  # 「改自·场景图」徽标
    chain_cost: Decimal | None = None  # 迭代链累计（R5：根计源张单张 cost + 路径编辑单）
    operation_type: str | None = None

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
                    # 失败张（两阶段 ISSUE-0047）无产物、key 空：不签 url，前端据 status 展失败位
                    url=(signer.generated_url(im.image_key) if im.status == "成功" else ""),
                    image_key=im.image_key,
                    seed=im.seed,
                    cost=im.cost,
                    status=im.status,
                    image_type=im.image_type,
                )
                for im in d.images
            ],
            input_urls=[signer.upload_url(k) for k in d.input_keys],
            category=d.category,
            clone_mode=d.clone_mode,
            input_roles=list(d.input_roles) or [None] * len(d.input_keys),
            parent_job_id=d.parent_job_id,
            edit_mode=d.edit_mode,
            source_image_url=(
                signer.generated_url(d.source_image_key) if d.source_image_key else None
            ),
            source_image_type=d.source_image_type,
            chain_cost=d.chain_cost,
            operation_type=d.operation_type,
        )
