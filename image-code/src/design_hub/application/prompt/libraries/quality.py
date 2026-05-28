from design_hub.domain.enums import ModelName

_QUALITY: dict[ModelName, str] = {
    ModelName.GPT_IMAGE_2: "8K超高清，电影级画质，商业广告质感，极致细节，锐利清晰",
    ModelName.SEEDREAM_5: "8K, 商业广告, 锐利细节, 高色彩还原",
    ModelName.QWEN_IMAGE_PRO: "超高清，商业摄影质感，精致细节",
    ModelName.WANXIANG_27: "(masterpiece:1.2), (8k:1.1), sharp focus, commercial photography",
    ModelName.LINGDONG_2: "(masterpiece:1.2), (8k:1.1), sharp focus, commercial photography",
}


class QualityLibrary:
    """词库 D：质量增强词（按模型语言/格式）。"""

    def get(self, model: ModelName) -> str:
        if model not in _QUALITY:
            raise KeyError(f"No quality words for model {model}")
        return _QUALITY[model]
