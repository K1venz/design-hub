from enum import StrEnum


class LensPurpose(StrEnum):
    SINGLE_PRODUCT = "单品精修"
    BIG_PERSPECTIVE = "大透视冲击"
    STRUCTURE = "结构展示"
    AMBIANCE = "场景氛围"


_LENS: dict[LensPurpose, str] = {
    LensPurpose.SINGLE_PRODUCT: "50mm标准镜头，f/1.8大光圈，浅景深，近景特写",
    LensPurpose.BIG_PERSPECTIVE: "24mm广角，低角度仰拍，第一人称视角，近大远小",
    LensPurpose.STRUCTURE: "45°斜角特写 + 轻微低角度仰拍，产品居中占 65-70%",
    LensPurpose.AMBIANCE: "中焦，柔焦，电影级光影，eye-level 平视",
}


class LensLibrary:
    """词库 E：镜头库（按用途的摄影术语）。"""

    def get(self, purpose: LensPurpose) -> str:
        if purpose not in _LENS:
            raise KeyError(f"No lens for purpose {purpose}")
        return _LENS[purpose]
