"""Configuration for the Agent Service."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class WarehouseConfig(BaseSettings):
    """Configuration for a single MCP warehouse connection."""

    warehouse_id: str
    label: str
    mcp_command: str = "python"
    mcp_args: list[str] = Field(default_factory=lambda: ["-m", "src.server"])
    mcp_cwd: str = "/app/mcp-server"
    mcp_env: dict[str, str] = Field(default_factory=dict)


class RedisConfig(BaseSettings):
    """Redis cache configuration."""

    model_config = {"env_prefix": "REDIS_"}

    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    default_ttl: int = 3600
    sales_ttl: int = 300
    targets_ttl: int = 3600
    max_connections: int = 20


class RagConfig(BaseSettings):
    """RAG / vector store configuration."""

    model_config = {"env_prefix": "RAG_"}

    collection_name: str = "warehouse_metadata"
    persist_directory: str = "/data/chromadb"
    embedding_model: str = "text-embedding-3-small"
    search_top_k: int = 5


class LlmConfig(BaseSettings):
    """LLM configuration."""

    model_config = {"env_prefix": "LLM_"}

    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.1
    max_tokens: int = 4096
    api_key: str = ""


class AgentServiceConfig(BaseSettings):
    """Top-level agent service configuration."""

    model_config = {"env_prefix": "AGENT_"}

    host: str = "0.0.0.0"
    port: int = 8001
    log_level: str = "INFO"
    max_iterations: int = 10
    warehouses_config_path: str = "/app/config/warehouses.json"
