"""應用程式設定。用 pydantic-settings 從環境變數 / .env 讀取，並以
`get_settings()` 提供單例，避免在模組層級放全域變數。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """所有可設定參數的單一來源。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    embed_model: str = "nomic-embed-text"
    chat_model: str = "qwen2.5:7b"

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "docqa"
    postgres_password: str = "docqa"
    postgres_db: str = "docqa"

    # 切塊 / 檢索
    chunk_size: int = 500
    chunk_overlap: int = 80
    top_k: int = 5

    @property
    def postgres_dsn(self) -> str:
        """組出 psycopg 連線字串。"""
        return (
            f"host={self.postgres_host} port={self.postgres_port} "
            f"user={self.postgres_user} password={self.postgres_password} "
            f"dbname={self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """回傳快取的 Settings 單例，避免每次都重新解析環境變數。"""
    return Settings()
