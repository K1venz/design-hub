from ..domain.enums import Category

_BRAND_POOL: dict[Category, list[str]] = {
    Category.DIGITAL_3C: ["Thermo Arc", "Volt Edge", "Nimbus Core"],
    Category.APPAREL: ["Urban Loop", "Field Mark", "Crane & Co"],
    Category.BEAUTY: ["Lumi Veil", "Petal Form", "Aura Skin"],
    Category.FOOD: ["Harvest Lane", "Grain & Ember", "Pure Crumb"],
    Category.WITH_PERSON: ["Modeluxe", "Form Atelier", "Mode Nord"],
    Category.MIRROR: ["Clearon", "Mirage Lab", "Glass Theory"],
}


class BrandNameGenerator:
    """虚构品牌名生成：按品类出候选英文名，规避真实品牌版权。"""

    def candidates(self, category: Category, count: int = 3) -> list[str]:
        pool = _BRAND_POOL.get(category, ["Generica", "Marque One", "Brandly"])
        return pool[:count]
