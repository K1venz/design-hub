from design_hub.domain.enums import ProjectStatus

# 4 态状态机（PRD §2.3）：需求录入 → 设计中 ⇌ 客户审稿 → 已交付
# 数据驱动（OCP）：改流转规则只改此表，不动校验逻辑。
ALLOWED_TRANSITIONS: dict[ProjectStatus, frozenset[ProjectStatus]] = {
    ProjectStatus.REQUIREMENT: frozenset({ProjectStatus.DESIGNING}),
    ProjectStatus.DESIGNING: frozenset({ProjectStatus.REVIEW}),
    ProjectStatus.REVIEW: frozenset({ProjectStatus.DESIGNING, ProjectStatus.DELIVERED}),
    ProjectStatus.DELIVERED: frozenset(),  # 终态
}


def can_transition(src: ProjectStatus, dst: ProjectStatus) -> bool:
    return dst in ALLOWED_TRANSITIONS.get(src, frozenset())
