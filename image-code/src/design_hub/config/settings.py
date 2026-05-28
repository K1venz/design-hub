from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.development", extra="ignore")

    dashscope_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")

    @classmethod
    def from_kms(cls) -> "Settings":
        # Production secrets pulled from Aliyun KMS at startup; not on disk.
        raise NotImplementedError("KMS loader wired in deployment milestone")
