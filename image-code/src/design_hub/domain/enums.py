from enum import StrEnum


class SubScene(StrEnum):
    S1 = "S1"  # 商品主图换背景
    S3 = "S3"  # 商品场景图
    S4 = "S4"  # 多角度/姿势裂变


class Tier(StrEnum):
    DRAFT = "draft"
    STANDARD = "standard"
    REFINE = "refine"


class TemplateFamily(StrEnum):
    F1 = "family_1"  # 大透视广告海报
    F2 = "family_2"  # 结构光效/X射线
    F3 = "family_3"  # 极简电商主图
    F4 = "family_4"  # 高端商业摄影
    F5 = "family_5"  # 氛围沉浸场景
    F6 = "family_6"  # 双语规范+排版
    F7 = "family_7"  # 中式节庆促销
    F8 = "family_8"  # 字效/标题字
    F9 = "family_9"  # 创意超现实


class Style(StrEnum):
    LUXURY = "高端轻奢"
    NORDIC = "极简北欧"
    GUOCHAO = "国潮中式"
    TECH = "科技未来"
    FRESH = "清新自然"
    SPORT = "运动机能"
    FESTIVE = "喜庆节日"


class Category(StrEnum):
    DIGITAL_3C = "3C数码"
    APPAREL = "服饰配件"
    BEAUTY = "美妆护肤"
    FOOD = "食品"
    WITH_PERSON = "含人物"
    MIRROR = "镜面玻璃"


class MaterialType(StrEnum):
    MAIN = "主图"
    DETAIL = "详情"
    POSTER = "海报"
    LEAFLET = "折页"
    OFFLINE = "线下"


class ModelName(StrEnum):
    GPT_IMAGE_2 = "gpt-image-2"
    QWEN_IMAGE_PRO = "qwen-image-pro"
    SEEDREAM_5 = "seedream-5"
    WANXIANG_27 = "wanxiang-2.7-pro"
    LINGDONG_2 = "lingdong-2"


class ProjectStatus(StrEnum):
    REQUIREMENT = "需求录入"
    DESIGNING = "设计中"
    REVIEW = "客户审稿"
    DELIVERED = "已交付"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class AssetKind(StrEnum):
    PRODUCT = "产品图"
    REFERENCE = "参考图"


class RevisionStatus(StrEnum):
    OPEN = "进行中"
    DONE = "已完成"


class TaskEventType(StrEnum):
    TASK_STARTED = "task_started"
    MODEL_CALLED = "model_called"
    IMAGE_GENERATED = "image_generated"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
