from enum import StrEnum


class ModelName(StrEnum):
    GPT_IMAGE_2 = "gpt-image-2"
    SEEDREAM_5 = "seedream-5"
    WANXIANG_27 = "wanxiang-2.7-pro"
    LINGDONG_2 = "lingdong-2"


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
