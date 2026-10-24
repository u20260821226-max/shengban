from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_secret_key: str = "development-only-change-me"
    database_url: str = "sqlite:///./shengban.db"
    storage_root: Path = Path("./storage")
    omr_provider: str = "unconfigured"
    omr_api_base_url: str = ""
    omr_api_key: str = ""
    audio_renderer: str = "unconfigured"
    audio_api_base_url: str = ""
    audio_api_key: str = ""


settings = Settings()
