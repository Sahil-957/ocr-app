from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Costing OCR Platform"
    secret_key: str = "change-this-in-production"
    access_token_expire_minutes: int = 720
    database_url: str = "sqlite:///./storage/app.db"
    storage_root: Path = Path("./storage")
    upload_root: Path = Path("./storage/uploads")
    export_root: Path = Path("./storage/exports")
    ocr_model_root: Path = Path("./storage/paddleocr")
    retain_days: int = 30
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123"
    confidence_threshold: float = 0.82

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
