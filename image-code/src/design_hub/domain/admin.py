from enum import StrEnum


class ModerationStatus(StrEnum):
    NORMAL = "normal"
    BLOCKED = "blocked"


class ModerationReason(StrEnum):
    SEXUAL = "sexual"
    VIOLENCE = "violence"
    ILLEGAL = "illegal"
    INFRINGEMENT = "infringement"
    OTHER = "other"


class ModelCallStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    INTERRUPTED = "interrupted"


class ModelModality(StrEnum):
    IMAGE = "image"
    CHAT = "chat"


class ModelOperation(StrEnum):
    IMAGE_GENERATION = "image_generation"
    IMAGE_EDIT = "image_edit"
    CHAT_COMPLETION = "chat_completion"
    REVERSE_PROMPT = "reverse_prompt"


class AdminAction(StrEnum):
    USER_ROLE_UPDATE = "user.role.update"
    USER_STATUS_UPDATE = "user.status.update"
    IMAGE_MODERATION_UPDATE = "image.moderation.update"
    MODEL_CREATE = "model.create"
    MODEL_UPDATE = "model.update"
    MODEL_DELETE = "model.delete"
    MODEL_DEFAULT_SET = "model.default.set"
