import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from design_hub.application.pipeline import GenerationPipeline
from design_hub.application.project.brief_to_brief import compose_brief
from design_hub.domain.errors import NotFoundError
from design_hub.domain.models import Brief, GenerationConfig, GenerationResult
from design_hub.ports.asset_store import AssetStore
from design_hub.ports.job_repository import JobRepository
from design_hub.ports.repositories import (
    AssetRepository,
    BriefRepository,
    CustomerRepository,
    ProjectRepository,
)


@dataclass(frozen=True)
class ProjectGenerationOutcome:
    """项目下出图结果：引擎结果 + 归属（project_id/round_no/job_id）。"""

    job_id: str
    project_id: int
    round_no: int
    result: GenerationResult


@dataclass
class ProjectGenerationService:
    """项目下出图用例（SRP）：按出图配置合成域 Brief → 复用 pipeline → 落库挂 project_id+round_no。

    一张需求单可发 N 次出图（每次一个 GenerationConfig），每个 job 挂当前轮次（D2 方案①）。
    """

    projects: ProjectRepository
    customers: CustomerRepository
    briefs: BriefRepository
    assets: AssetRepository
    store: AssetStore
    pipeline: GenerationPipeline
    jobs: JobRepository

    async def compose(self, project_id: int, config: GenerationConfig) -> tuple[Brief, int]:
        """合成域 Brief 并取出当前轮次（同步/异步出图共用）。"""
        project = await self.projects.get(project_id)
        if project is None:
            raise NotFoundError(f"项目 {project_id} 不存在")
        customer = await self.customers.get(project.customer_id)
        if customer is None:
            raise NotFoundError(f"客户 {project.customer_id} 不存在")
        brief_record = await self.briefs.get(project_id)
        reference_images = await self._load_assets(project_id, config.asset_ids)
        brief = compose_brief(
            customer_name=customer.name,
            brief=brief_record,
            config=config,
            reference_images=reference_images,
        )
        return brief, project.current_round

    async def generate(
        self, project_id: int, config: GenerationConfig, *, user_id: str
    ) -> ProjectGenerationOutcome:
        brief, round_no = await self.compose(project_id, config)
        result = await self.pipeline.run(brief, user_id)
        job_id = uuid.uuid4().hex
        await self.jobs.save_completed(
            job_id=job_id,
            user_id=user_id,
            brief=brief,
            result=result,
            project_id=project_id,
            round_no=round_no,
        )
        return ProjectGenerationOutcome(
            job_id=job_id, project_id=project_id, round_no=round_no, result=result
        )

    async def _load_assets(
        self, project_id: int, asset_ids: Sequence[int]
    ) -> tuple[bytes, ...]:
        if not asset_ids:
            return ()
        found = {a.id: a for a in await self.assets.get_many(asset_ids)}
        missing = [i for i in asset_ids if i not in found]
        if missing:
            raise NotFoundError(f"素材不存在：{missing}")
        wrong = [i for i in asset_ids if found[i].project_id != project_id]
        if wrong:
            raise ValueError(f"素材不属于项目 {project_id}：{wrong}")
        return tuple([await self.store.load(found[i].url) for i in asset_ids])
