from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str | None = None
    api_key: str = ""
    model: str = ""
    timeout_seconds: float = 60.0


class SimplexConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SIMPLEX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = "https://dxb5.simplexworld.com"
    tenant_path: str = ""
    location_id: str = ""
    api_key: str = ""
    timeout_seconds: float = 30.0
