from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/inventory_db"
    redis_url: str = "redis://localhost:6379/0"
    app_env: str = "development"

    # Groq model — llama-3.1-8b-instant is free, fast, and great at JSON output
    groq_model: str = "llama-3.1-8b-instant"

    # Cache TTL in seconds
    cache_ttl: int = 300

    # Batch prediction limit
    batch_limit: int = 20

    # MCP server base URLs
    inventory_mcp_url: str = "http://inventory-mcp:8001"
    supplier_mcp_url: str = "http://supplier-mcp:8002"


settings = Settings()
