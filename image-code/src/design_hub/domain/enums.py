from enum import StrEnum


class ModelType(StrEnum):
    IMAGE = "image"
    CHAT = "chat"
    VISION = "vision"


class ProviderType(StrEnum):
    OPENAI_COMPAT_IMAGE = "openai_compat_image"
    GEMINI_NATIVE_IMAGE = "gemini_native_image"
    DASHSCOPE_WAN_IMAGE = "dashscope_wan_image"
    OPENAI_COMPAT_CHAT = "openai_compat_chat"


class TaskEventType(StrEnum):
    TASK_STARTED = "task_started"
    MODEL_CALLED = "model_called"
    IMAGE_GENERATED = "image_generated"
    IMAGE_FAILED = "image_failed"  # 套图单张失败（带 image_type+error；单图流仍走 TASK_FAILED）
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"


class Role(StrEnum):
    """系统角色：值=app_user.role 的 DB 字符串契约（改值=数据迁移，须用户签字）。"""

    DESIGNER = "设计师"
    MANAGER = "管理者"
