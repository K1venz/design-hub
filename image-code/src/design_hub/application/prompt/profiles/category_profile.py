from dataclasses import dataclass

from design_hub.domain.enums import Category


@dataclass(frozen=True)
class CategoryProfile:
    """品类画像（物性/技法）：怎么拍这类东西。"""

    category: Category
    lens: str  # 镜头
    composition: str  # 构图
    position: str  # 位置
    angle: str  # 角度
    light_form: str  # 光型（方向/硬度，不含色温）
    props: str  # 品类道具/装饰
    guard: str  # 防御词（材质保真/防漂移）
    negatives: tuple[str, ...]  # 品类负面侧重
    fidelity: str  # 材质保真侧重（图生图 EDIT 模式用）
