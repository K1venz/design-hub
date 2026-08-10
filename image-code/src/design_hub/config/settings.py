from email.utils import parseaddr
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env（本地真凭据，gitignored）覆盖 .env.development（占位，可入库）
    model_config = SettingsConfigDict(
        env_file=(".env.development", ".env"), extra="ignore"
    )

    # 默认 sqlite（零基础设施）；生产/本地 MySQL 经环境变量 DB_URL 覆盖，密钥不入库
    db_url: str = "sqlite+aiosqlite:///./design_hub.db"
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_health_interval_seconds: float = Field(default=2.0, gt=0)
    redis_health_stale_seconds: float = Field(default=6.0, gt=0)
    outbox_batch_size: int = Field(default=100, gt=0, le=1000)
    queue_soft_wait_seconds: int = Field(default=300, gt=0)
    queue_confirm_wait_seconds: int = Field(default=900, gt=0)
    queue_hard_depth: int = Field(default=2000, gt=0)
    provider_standard_concurrency: int = Field(default=3, gt=0)
    provider_4k_concurrency: int = Field(default=1, gt=0)
    provider_slot_lease_seconds: int = Field(default=30, gt=0)
    provider_slot_refresh_seconds: int = Field(default=10, gt=0)
    worker_read_count: int = Field(default=8, gt=0, le=100)
    worker_read_block_ms: int = Field(default=1000, gt=0, le=30_000)
    worker_reclaim_idle_ms: int = Field(default=30_000, gt=0)
    worker_heartbeat_seconds: float = Field(default=15.0, gt=0)
    worker_dispatch_interval_seconds: float = Field(default=0.2, gt=0)
    worker_shutdown_timeout_seconds: float = Field(default=30, gt=0, le=120)
    queue_rolling_item_seconds: float = Field(default=60, gt=0)

    # Provider credentials, endpoints, upstream model names, and protocol options are
    # database-only. Environment settings contain operational network budgets only.
    gpt_image_request_timeout: float = Field(default=300.0, gt=0)
    nano_banana_request_timeout: float = Field(default=300.0, gt=0)
    nano_banana_max_retries: int = Field(default=1, ge=0, le=10)
    text_llm_request_timeout: float = Field(default=120.0, gt=0)
    # 对话会话级出图闸（#884②）：单会话最多出图单数，保守默认 5，可配。
    chat_session_max_jobs: int = 5
    # 套图并发窗口（ISSUE-0047）：apikey 轮换后新 key 分组并发档位低，5 路并发打满上游 429
    # → 套图「只出 1 张」。保守默认 3；ops 可经 .env 下调至 2 而无需改码。单图流 n=1 恒 1 路，
    # 任何 ≥1 的取值都不改其行为。
    listing_concurrency: int = 3
    # gpt-image 中转站瞬时错误（429/超时/5xx）重试预算（ISSUE-0007/0047，仅 I/O 域，4xx 不重试）
    gpt_image_max_retries: int = 5
    # 指数退避基数（秒）：第 n 次退避 ~ base*2^(n-1)，叠 equal-jitter 抖动错峰
    gpt_image_retry_backoff: float = 2.0
    gpt_image_retry_max_sleep: float = 30.0  # 单次退避封顶（秒），防指数增长失控
    # 总重试墙钟预算（秒，ISSUE-0055 (i)）：封顶整个重试窗口，持久 5xx 超此即穷尽落「失败」，
    # 不让用户干等 max_retries×退避（实测上游持续 500 曾拖 ~8 分钟）。只 gate 重试、不砍成功请求。
    gpt_image_retry_max_elapsed: float = 90.0
    # Single-request timeout and total retry wall-clock budget for the 4K Images API.
    gpt_image_4k_timeout: float = Field(default=1800.0, gt=0)
    # 异步任务出图 provider（ISSUE-0065，provider_type=apinebula_async_image）：轮询节奏 + 总墙钟。
    # 异步排队可能比同步 90s 长，故独立更宽默认；超墙钟=穷尽 fail-closed（同 0055 (i) 语义）。
    gpt_image_async_poll_interval: float = 6.0
    gpt_image_async_poll_max_elapsed: float = 300.0
    wan_request_timeout: float = Field(default=60.0, gt=0)
    wan_poll_interval: float = Field(default=6.0, ge=0)
    wan_poll_max_elapsed: float = Field(default=900.0, gt=0)
    wan_retry_count: int = Field(default=2, ge=0, le=10)
    wan_retry_backoff: float = Field(default=1.0, ge=0)
    wan_max_download_bytes: int = Field(
        default=64 * 1024 * 1024,
        gt=0,
    )
    # 本地出图落点（图生图 b64 解码后写入；gitignored）
    image_output_dir: str = "./generated"
    # 出图 url 公网前缀（ISSUE-0029）：非空→绝对 https://host/img/<name>；空→相对 /img/<name>
    image_public_base_url: str = ""
    # 本地素材落点（上传产品图/参考图写入；gitignored）
    asset_output_dir: str = "./assets"
    # 本地导出归档落点（WP-E：多格式/改尺寸/zip 输出；gitignored）
    export_output_dir: str = "./exports"
    runtime_log_dir: Path = Path("./exports/.runtime-logs")
    runtime_log_max_bytes: int = Field(
        default=50 * 1024 * 1024,
        gt=0,
    )
    # WP-G 鉴权：JWT HS256 密钥（生产经 .env 覆盖，默认占位仅供本地/CI）+ 有效期
    jwt_secret: SecretStr = SecretStr("dev-insecure-secret-change-me-min-32-bytes")
    jwt_ttl_hours: int = 24
    # 滑动续期半衰期（小时，ISSUE-0058）：令牌签发超此→鉴权时签新 24h 令牌放 X-Renewed-Token 头
    jwt_renew_after_hours: int = 12
    model_verification_ttl_seconds: int = Field(default=600, gt=0)
    # RSA private-key PEM encrypts authentication passwords and other application secrets.
    auth_rsa_private_key_pem: SecretStr = SecretStr("")
    # Production deployment enables this with REQUIRE_PERSISTENT_SECRET_CIPHER=true.
    require_persistent_secret_cipher: bool = False
    # ISSUE-0015 自建认证：启动 seed 管理员（邮箱/密码走 .env，空=不 seed；建议首登后改密）
    seed_admin_email: str = ""
    seed_admin_password: SecretStr = SecretStr("")
    # Password reset email delivery is explicit: production uses smtp; local tests use log.
    mail_delivery_mode: Literal["log", "smtp"] = "log"
    smtp_host: str = ""
    smtp_port: int = Field(default=587, gt=0, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from_name: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    email_verification_code_pepper: SecretStr = SecretStr("")
    password_reset_code_ttl_seconds: int = Field(default=600, gt=0, le=3600)
    password_reset_resend_cooldown_seconds: int = Field(default=60, gt=0, le=600)
    password_reset_max_attempts: int = Field(default=5, gt=0, le=20)
    # 监控（ISSUE-0008）：Sentry DSN，空则不接入（本地/CI no-op）
    sentry_dsn: str = ""
    # 安全加固 A-2 纵深：/docs /redoc /openapi.json 路由开关。代码默认关：
    # prod 不配即闭、忘配=安全。qa/本地要浏览文档在各自 gitignored .env 设
    # DOCS_ENABLED=true；勿写进 .env.development（会随镜像带上 prod）。
    docs_enabled: bool = False

    @model_validator(mode="after")
    def validate_worker_lease_timing(self) -> "Settings":
        if self.worker_heartbeat_seconds * 1000 >= self.worker_reclaim_idle_ms:
            raise ValueError("worker heartbeat must be shorter than delivery reclaim idle")
        if self.mail_delivery_mode == "smtp":
            missing = [
                name
                for name, value in (
                    ("SMTP_HOST", self.smtp_host.strip()),
                    ("SMTP_FROM_NAME", self.smtp_from_name.strip()),
                    ("SMTP_FROM", self.smtp_from.strip()),
                    (
                        "EMAIL_VERIFICATION_CODE_PEPPER",
                        self.email_verification_code_pepper.get_secret_value().strip(),
                    ),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"SMTP mail delivery requires: {', '.join(missing)}"
                )
            display_name, mailbox = parseaddr(self.smtp_from, strict=True)
            if display_name or mailbox != self.smtp_from.strip() or "@" not in mailbox:
                raise ValueError("SMTP_FROM must be a valid mailbox address")
        return self

    # 火山引擎 TOS 对象存储：配了 tos_access_key + 两桶即启用 Tos 适配器，否则回退本地存储
    tos_access_key: SecretStr = SecretStr("")
    tos_secret_key: SecretStr = SecretStr("")
    tos_region: str = ""  # 如 cn-shanghai
    tos_endpoint: str = ""  # 如 tos-cn-shanghai.volces.com
    tos_generate_bucket: str = ""  # 出图结果桶
    tos_upload_bucket: str = ""  # 用户上传图桶
    tos_signed_url_ttl: int = 3600  # 预签名 url 有效期（秒）
