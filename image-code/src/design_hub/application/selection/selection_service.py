from __future__ import annotations

from dataclasses import dataclass

from design_hub.domain.errors import NotFoundError
from design_hub.domain.models import GeneratedImageRecord, UsableRate
from design_hub.ports.image_repository import GeneratedImageRepository

USABLE_MIN_SCORE = 4  # PRD §1.2：评分 ≥4 星 计入「可用」


@dataclass
class SelectionService:
    """选稿+评分用例（SRP）：候选图打分/保留 + 任务可用率。依赖端口（DIP）。"""

    images: GeneratedImageRepository

    async def list_images(self, job_id: str) -> list[GeneratedImageRecord]:
        await self._require_job(job_id)
        return await self.images.list_by_job(job_id)

    async def score(self, job_id: str, image_id: int, score: int) -> GeneratedImageRecord:
        if not 1 <= score <= 5:
            raise ValueError("评分必须在 1..5 之间")
        await self._require_image_in_job(job_id, image_id)
        return await self.images.set_score(image_id, score)

    async def keep(self, job_id: str, image_id: int, *, kept: bool) -> GeneratedImageRecord:
        await self._require_image_in_job(job_id, image_id)
        return await self.images.set_kept(image_id, kept=kept)

    async def usable_rate(self, job_id: str) -> UsableRate:
        await self._require_job(job_id)
        imgs = await self.images.list_by_job(job_id)
        total = len(imgs)
        usable = sum(1 for i in imgs if i.score is not None and i.score >= USABLE_MIN_SCORE)
        rate = (usable / total) if total else 0.0
        return UsableRate(usable=usable, total=total, rate=rate)

    async def _require_job(self, job_id: str) -> None:
        if not await self.images.job_exists(job_id):
            raise NotFoundError(f"任务 {job_id} 不存在")

    async def _require_image_in_job(self, job_id: str, image_id: int) -> None:
        img = await self.images.get(image_id)
        if img is None or img.job_id != job_id:
            raise NotFoundError(f"任务 {job_id} 下不存在候选图 {image_id}")
