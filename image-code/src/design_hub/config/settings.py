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

    @classmethod
    def from_kms(cls) -> "Settings":
        # Production secrets pulled from Aliyun KMS at startup; not on disk.
        raise NotImplementedError("KMS loader wired in deployment milestone")
