from dataclasses import dataclass

from design_hub.domain.enums import ProjectStatus
from design_hub.domain.errors import DomainError
from design_hub.domain.models import ProjectRecord
from design_hub.domain.project_status import can_transition
from design_hub.ports.repositories import CustomerRepository, ProjectRepository
from design_hub.ports.revision_repository import RevisionRepository


@dataclass
class ProjectService:
    """项目用例（SRP）：创建/查询 + 状态机流转校验 + 交付强校验。依赖端口（DIP）。"""

    projects: ProjectRepository
    customers: CustomerRepository
    revisions: RevisionRepository

    async def create(self, *, customer_id: int, name: str) -> ProjectRecord:
        if not name.strip():
            raise ValueError("项目名称不能为空")
        if await self.customers.get(customer_id) is None:
            raise DomainError(f"客户 {customer_id} 不存在")
        return await self.projects.create(customer_id=customer_id, name=name)

    async def get(self, project_id: int) -> ProjectRecord | None:
        return await self.projects.get(project_id)

    async def list(self, *, customer_id: int | None = None) -> list[ProjectRecord]:
        return await self.projects.list(customer_id=customer_id)

    async def transition(
        self, project_id: int, target: ProjectStatus, *, force: bool = False
    ) -> ProjectRecord:
        current = await self.projects.get(project_id)
        if current is None:
            raise DomainError(f"项目 {project_id} 不存在")
        if not can_transition(current.status, target):
            raise DomainError(f"非法状态流转：{current.status.value} → {target.value}")
        # 交付强校验（WP-D）：转「已交付」前若有未完成改稿条目则拒；管理者 force 可跳过
        if target is ProjectStatus.DELIVERED and not force:
            if await self.revisions.has_open_items(project_id):
                raise DomainError("项目存在未完成改稿条目，不能交付（管理者可 ?force=true 跳过）")
        return await self.projects.set_status(project_id, target)
