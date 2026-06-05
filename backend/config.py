"""
Looploop 配置文件

通过环境变量读取所有配置项。开发时复制 .env.example 为 .env 并填入实际值。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    # --- LLM ---
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"

    # --- 文本处理 ---
    chunk_max_tokens: int = 1500
    chunk_overlap_ratio: float = 0.2

    # --- 安全解析 ---
    max_retries: int = 3

    # --- 应用 ---
    app_name: str = "Looploop"
    app_version: str = "0.1.0"
    debug: bool = False

    # --- CORS ---
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
