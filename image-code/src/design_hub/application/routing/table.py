from design_hub.domain.enums import ModelName, TemplateFamily

# 含真人/复杂版式：强制 GPT-image，忽略档位
FORCED_GPT_FAMILIES: frozenset[TemplateFamily] = frozenset(
    {
        TemplateFamily.F1,
        TemplateFamily.F2,
        TemplateFamily.F6,
        TemplateFamily.F8,
        TemplateFamily.F9,
    }
)

# 标准档：模板族 → 首选模型（V1 4 族）
FAMILY_PRIMARY: dict[TemplateFamily, ModelName] = {
    TemplateFamily.F3: ModelName.SEEDREAM_5,
    TemplateFamily.F4: ModelName.GPT_IMAGE_2,
    TemplateFamily.F5: ModelName.SEEDREAM_5,
    TemplateFamily.F7: ModelName.QWEN_IMAGE_PRO,
}

REFINE_MODEL: ModelName = ModelName.GPT_IMAGE_2
DRAFT_MODEL_S4: ModelName = ModelName.WANXIANG_27
DRAFT_MODEL_DEFAULT: ModelName = ModelName.LINGDONG_2

DEFAULT_CANDIDATES = 6
MAX_CANDIDATES = 12

# 同档位备选链（绝不跨档升级）
FALLBACKS: dict[ModelName, tuple[ModelName, ...]] = {
    ModelName.SEEDREAM_5: (ModelName.QWEN_IMAGE_PRO,),
    ModelName.QWEN_IMAGE_PRO: (ModelName.SEEDREAM_5,),
    ModelName.GPT_IMAGE_2: (ModelName.SEEDREAM_5,),
    ModelName.LINGDONG_2: (ModelName.WANXIANG_27,),
    ModelName.WANXIANG_27: (ModelName.LINGDONG_2,),
}
