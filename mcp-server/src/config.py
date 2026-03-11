"""Configuration for the Oracle MCP Server."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class OracleConfig(BaseSettings):
    """Oracle database connection configuration."""

    model_config = {"env_prefix": "ORACLE_"}

    host: str = "localhost"
    port: int = 1521
    service_name: str = "ORCL"
    user: str = "readonly_user"
    password: str = "changeme"
    wallet_location: str = ""
    wallet_password: str = ""
    min_connections: int = 2
    max_connections: int = 10
    connection_timeout: int = 30


class ServerConfig(BaseSettings):
    """MCP Server configuration."""

    model_config = {"env_prefix": "MCP_"}

    server_name: str = "oracle-warehouse"
    warehouse_id: str = "hq"
    warehouse_label: str = "HQ Warehouse"
    read_only: bool = True
    max_rows: int = 1000
    query_timeout: int = 60
    log_level: str = "INFO"
    transport: str = "streamable-http"
    http_host: str = "0.0.0.0"
    http_port: int = 8080
