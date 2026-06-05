"""项目级任务/候选图列举 HTTP schema（ISSUE-0012）。"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from design_hub.ports.media_url_signer import MediaUrlSigner
from design_hub.ports.project_catalog import ProjectImage, ProjectJob


class ProjectJobOut(BaseModel):
    job_id: str
    round_no: int
    subscene: str
    family: str
    tier: str
    category: str
    used_model: str
    candidate_count: int
    total_cost: Decimal
    status: str
    created_at: datetime

    @classmethod
    def of(cls, j: ProjectJob) -> "ProjectJobOut":
        return cls(
            job_id=j.job_id,
            round_no=j.round_no,
            subscene=j.subscene,
            family=j.family,
            tier=j.tier,
            category=j.category,
            used_model=j.used_model,
            candidate_count=j.candidate_count,
            total_cost=j.total_cost,
            status=j.status,
            created_at=j.created_at,
        )


class ProjectImageOut(BaseModel):
    image_id: int
    job_id: str
    url: str
    seed: int
    score: int | None
    kept: bool
    round_no: int
    subscene: str

    @classmethod
    def of(cls, i: ProjectImage, signer: MediaUrlSigner) -> "ProjectImageOut":
        return cls(
            image_id=i.image_id,
            job_id=i.job_id,
            url=signer.generated_url(i.url),  # i.url 实为 image_key（ISSUE-0034）
            seed=i.seed,
            score=i.score,
            kept=i.kept,
            round_no=i.round_no,
            subscene=i.subscene,
        )
