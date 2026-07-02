from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env（本地真凭据，gitignored）覆盖 .env.development（占位，可入库）
    model_config = SettingsConfigDict(
        env_file=(".env.development", ".env"), extra="ignore"
    )

    # 默认 sqlite（零基础设施）；生产/本地 MySQL 经环境变量 DB_URL 覆盖，密钥不入库
    db_url: str = "sqlite+aiosqlite:///./design_hub.db"
    dashscope_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")

    # gpt-image-2 中转站（apinebula/诗云），走 OpenAI 兼容协议
    gpt_image_base_url: str = ""
    gpt_image_api_key: SecretStr = SecretStr("")
    gpt_image_model: str = ""
    # 文本 LLM（方案 C「帮我设计」Agent）：配 TEXT_LLM_* 三项即启真实适配器，否则用 Mock。
    # ⚠️ 现有 GPT_IMAGE key 仅图像权限（探明实测文本 403）；文本需用户另开 key/access。
    text_llm_base_url: str = ""
    text_llm_api_key: SecretStr = SecretStr("")
    text_llm_model: str = ""
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
    # 本地出图落点（图生图 b64 解码后写入；gitignored）
    image_output_dir: str = "./generated"
    # 出图 url 公网前缀（ISSUE-0029）：非空→绝对 https://host/img/<name>；空→相对 /img/<name>
    image_public_base_url: str = ""
    # 本地素材落点（上传产品图/参考图写入；gitignored）
    asset_output_dir: str = "./assets"
    # 本地导出归档落点（WP-E：多格式/改尺寸/zip 输出；gitignored）
    export_output_dir: str = "./exports"
    # WP-G 鉴权：JWT HS256 密钥（生产经 .env 覆盖，默认占位仅供本地/CI）+ 有效期
    jwt_secret: SecretStr = SecretStr("dev-insecure-secret-change-me-min-32-bytes")
    jwt_ttl_hours: int = 24
    # ISSUE-0015 自建认证：启动 seed 管理员（邮箱/密码走 .env，空=不 seed；建议首登后改密）
    seed_admin_email: str = ""
    seed_admin_password: SecretStr = SecretStr("")
    # 监控（ISSUE-0008）：Sentry DSN，空则不接入（本地/CI no-op）
    sentry_dsn: str = ""
    # 安全加固 A-2 纵深：/docs /redoc /openapi.json 路由开关。代码默认关：
    # prod 不配即闭、忘配=安全。qa/本地要浏览文档在各自 gitignored .env 设
    # DOCS_ENABLED=true；勿写进 .env.development（会随镜像带上 prod）。
    docs_enabled: bool = False

    # 火山引擎 TOS 对象存储：配了 tos_access_key + 两桶即启用 Tos 适配器，否则回退本地存储
    tos_access_key: SecretStr = SecretStr("")
    tos_secret_key: SecretStr = SecretStr("")
    tos_region: str = ""  # 如 cn-shanghai
    tos_endpoint: str = ""  # 如 tos-cn-shanghai.volces.com
    tos_generate_bucket: str = ""  # 出图结果桶
    tos_upload_bucket: str = ""  # 用户上传图桶
    tos_signed_url_ttl: int = 3600  # 预签名 url 有效期（秒）

    @classmethod
    def from_kms(cls) -> "Settings":
        # Production secrets pulled from Aliyun KMS at startup; not on disk.
        raise NotImplementedError("KMS loader wired in deployment milestone")
