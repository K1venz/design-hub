from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env（本地真凭据，gitignored）覆盖 .env.development（占位，可入库）
    model_config = SettingsConfigDict(
        env_file=(".env.development", ".env"), extra="ignore"
    )

    # 默认 sqlite（零基础设施）；生产/本地 MySQL 经环境变量 DB_URL 覆盖，密钥不入库
    db_url: str = "sqlite+aiosqlite:///./design_hub.db"
    redis_url: str = "redis://127.0.0.1:6379/0"
    dashscope_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")

    # gpt-image-2 中转站（apinebula/诗云），走 OpenAI 兼容协议
    gpt_image_base_url: str = ""
    gpt_image_api_key: SecretStr = SecretStr("")
    gpt_image_model: str = ""
    # 本地出图落点（图生图 b64 解码后写入；gitignored）
    image_output_dir: str = "./generated"
    # 本地素材落点（上传产品图/参考图写入；gitignored）
    asset_output_dir: str = "./assets"

    @classmethod
    def from_kms(cls) -> "Settings":
        # Production secrets pulled from Aliyun KMS at startup; not on disk.
        raise NotImplementedError("KMS loader wired in deployment milestone")
