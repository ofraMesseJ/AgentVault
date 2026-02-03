from pydantic_settings import BaseSettings
from typing import Optional, List

class Settings(BaseSettings):
    GATEWAY_HOST: str = "0.0.0.0"
    GATEWAY_PORT: int = 18789
    DEFAULT_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"
    USE_LOCAL_MODELS: bool = True
    TELEGRAM_TOKEN: Optional[str] = None
    DISCORD_TOKEN: Optional[str] = None
    SLACK_TOKEN: Optional[str] = None
    GITHUB_TOKEN: Optional[str] = None
    SANDBOX_MODE: str = "native"
    MAX_EXECUTION_TIME: int = 30
    ALLOWED_PATHS: List[str] = ["./workspace"]
    MEMORY_BACKEND: str = "chroma"

    class Config:
        env_file = ".env"

settings = Settings()