import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Strategic Risk Intelligence System"
    API_V1_STR: str = "/api"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/risk_db")
    
    # AI - DeepSeek Configuration
    DEEPSEEK_API_KEY: Optional[str] = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")  # 可选: deepseek-chat, deepseek-reasoner
    
    # Crawler
    CRAWL_HEADLESS: bool = True
    LOW_MEMORY_MODE: bool = os.getenv("LOW_MEMORY_MODE", "false").lower() == "true"  # 低内存模式，禁用 Playwright

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
