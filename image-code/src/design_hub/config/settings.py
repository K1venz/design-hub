from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.development", extra="ignore")

    # 默认 sqlite（零基础设施）；生产/本地 MySQL 经环境变量 DB_URL 覆盖，密钥不入库
    db_url: str = "sqlite+aiosqlite:///./design_hub.db"
    redis_url: str = "redis://127.0.0.1:6379/0"
    dashscope_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")

    @classmethod
    def from_kms(cls) -> "Settings":
        # Production secrets pulled from Aliyun KMS at startup; not on disk.
        raise NotImplementedError("KMS loader wired in deployment milestone")
