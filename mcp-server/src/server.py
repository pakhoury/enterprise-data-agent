"""Oracle MCP Server — exposes Oracle DB operations via Model Context Protocol.

Provides tools for read-only SQL execution, schema discovery, and table descriptions.
Each server instance represents one Oracle warehouse (East, West, HQ, etc.).

Uses Streamable HTTP transport for production-grade HTTP-based communication.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from src.config import OracleConfig, ServerConfig
from src.oracle_client import OracleClient, ReadOnlyViolationError

load_dotenv()

logger = structlog.get_logger(__name__)

oracle_config = OracleConfig()
server_config = ServerConfig()
oracle_client = OracleClient(oracle_config, read_only=server_config.read_only)

app = FastMCP(
    server_config.server_name,
    host=server_config.http_host,
    port=server_config.http_port,
)


# ---------------------------------------------------------------------------
# Tools — SQL execution and schema operations
# ---------------------------------------------------------------------------


@app.tool()
async def run_sql(
    query: str,
    max_rows: int = 1000,
) -> str:
    """Execute a read-only SQL SELECT query against the Oracle warehouse.

    Only SELECT statements are allowed. Returns results as JSON array of objects.
    """
    try:
        effective_max = min(max_rows, server_config.max_rows)
        results = await oracle_client.execute_query(query, max_rows=effective_max)
        return json.dumps(results, default=str, indent=2)
    except ReadOnlyViolationError as exc:
        logger.warning("read_only_violation", tool="run_sql", error=str(exc))
        return json.dumps({"error": str(exc)})
    except Exception as exc:
        logger.error("run_sql_failed", error=str(exc))
        return json.dumps({"error": f"run_sql failed: {exc}"})


@app.tool()
async def get_schema() -> str:
    """List all accessible tables and views in the Oracle warehouse with row counts and metadata."""
    try:
        tables = await oracle_client.get_all_tables()
        return json.dumps(tables, default=str, indent=2)
    except Exception as exc:
        logger.error("get_schema_failed", error=str(exc))
        return json.dumps({"error": f"get_schema failed: {exc}"})


@app.tool()
async def describe_table(
    table_name: str,
    owner: str | None = None,
) -> str:
    """Get detailed schema for a specific table: columns, types, constraints, indexes, sample rows, and comments."""
    try:
        result = await oracle_client.describe_table(table_name, owner)
        return json.dumps(result, default=str, indent=2)
    except Exception as exc:
        logger.error("describe_table_failed", table=table_name, error=str(exc))
        return json.dumps({"error": f"describe_table failed: {exc}"})


@app.tool()
async def get_table_comments(
    table_name: str,
    owner: str | None = None,
) -> str:
    """Retrieve table and column descriptions/comments for a specific table."""
    try:
        result = await oracle_client.get_table_comments(table_name, owner)
        return json.dumps(result, default=str, indent=2)
    except Exception as exc:
        logger.error("get_table_comments_failed", table=table_name, error=str(exc))
        return json.dumps({"error": f"get_table_comments failed: {exc}"})


@app.tool()
async def health_check() -> str:
    """Check the health and connectivity status of this Oracle warehouse MCP server."""
    status: dict[str, Any] = {
        "server_name": server_config.server_name,
        "warehouse_id": server_config.warehouse_id,
        "warehouse_label": server_config.warehouse_label,
        "connected": oracle_client.is_connected,
        "read_only": server_config.read_only,
        "max_rows": server_config.max_rows,
        "transport": "streamable-http",
    }
    return json.dumps(status, indent=2)


# ---------------------------------------------------------------------------
# Resources — table metadata for agent discovery
# ---------------------------------------------------------------------------


@app.resource("oracle://{warehouse_id}/{owner}/{table_name}")
async def read_table_resource(warehouse_id: str, owner: str, table_name: str) -> str:
    """Read detailed schema for a specific table resource."""
    try:
        schema = await oracle_client.describe_table(table_name, owner)
        comments = await oracle_client.get_table_comments(table_name, owner)
        schema["comments"] = comments
        return json.dumps(schema, default=str, indent=2)
    except Exception as exc:
        logger.error(
            "read_resource_failed",
            owner=owner,
            table=table_name,
            error=str(exc),
        )
        return json.dumps({"error": str(exc)})


def main() -> None:
    """Entry point for the MCP server using Streamable HTTP transport."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.get_level_from_name(server_config.log_level)
        ),
    )
    logger.info(
        "starting_mcp_server",
        server=server_config.server_name,
        warehouse=server_config.warehouse_id,
        transport="streamable-http",
        host=server_config.http_host,
        port=server_config.http_port,
    )

    app.run(transport="streamable-http")


if __name__ == "__main__":
    main()
