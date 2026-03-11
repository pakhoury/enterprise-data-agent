"""Oracle MCP Server — exposes Oracle DB operations via Model Context Protocol.

Provides tools for read-only SQL execution, schema discovery, and table descriptions.
Each server instance represents one Oracle warehouse (East, West, HQ, etc.).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    TextContent,
    Tool,
)
from pydantic import AnyUrl

from src.config import OracleConfig, ServerConfig
from src.oracle_client import OracleClient, ReadOnlyViolationError

load_dotenv()

logger = structlog.get_logger(__name__)

oracle_config = OracleConfig()
server_config = ServerConfig()
oracle_client = OracleClient(oracle_config, read_only=server_config.read_only)

app = Server(server_config.server_name)


# ---------------------------------------------------------------------------
# Resources — table metadata for agent discovery
# ---------------------------------------------------------------------------


@app.list_resources()
async def list_resources() -> list[Resource]:
    """List all accessible tables as MCP resources."""
    try:
        tables = await oracle_client.get_all_tables()
        resources = []
        for table in tables:
            table_name = table.get("TABLE_NAME", "")
            owner = table.get("OWNER", "")
            num_rows = table.get("NUM_ROWS", "unknown")
            resources.append(
                Resource(
                    uri=AnyUrl(f"oracle://{server_config.warehouse_id}/{owner}/{table_name}"),
                    name=f"{owner}.{table_name}",
                    description=f"Table {table_name} in schema {owner} (~{num_rows} rows)",
                    mimeType="application/json",
                )
            )
        return resources
    except Exception as exc:
        logger.error("list_resources_failed", error=str(exc))
        return []


@app.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    """Read detailed schema for a specific table resource."""
    uri_str = str(uri)
    parts = uri_str.replace("oracle://", "").split("/")
    if len(parts) < 3:
        return json.dumps({"error": f"Invalid resource URI: {uri_str}"})

    _warehouse_id, owner, table_name = parts[0], parts[1], parts[2]

    try:
        schema = await oracle_client.describe_table(table_name, owner)
        comments = await oracle_client.get_table_comments(table_name, owner)
        schema["comments"] = comments
        return json.dumps(schema, default=str, indent=2)
    except Exception as exc:
        logger.error("read_resource_failed", uri=uri_str, error=str(exc))
        return json.dumps({"error": str(exc)})


# ---------------------------------------------------------------------------
# Tools — SQL execution and schema operations
# ---------------------------------------------------------------------------


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Expose available database tools."""
    return [
        Tool(
            name="run_sql",
            description=(
                "Execute a read-only SQL SELECT query against the Oracle warehouse. "
                "Only SELECT statements are allowed. Returns results as JSON array of objects. "
                f"Max {server_config.max_rows} rows returned."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL SELECT query to execute. Must be read-only.",
                    },
                    "max_rows": {
                        "type": "integer",
                        "description": f"Maximum rows to return (default: {server_config.max_rows}).",
                        "default": server_config.max_rows,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_schema",
            description="List all accessible tables and views in the Oracle warehouse with row counts and metadata.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="describe_table",
            description=(
                "Get detailed schema for a specific table: columns, types, constraints, indexes, "
                "sample rows, and comments."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table to describe (case-insensitive).",
                    },
                    "owner": {
                        "type": "string",
                        "description": "Schema owner (optional, defaults to current user).",
                    },
                },
                "required": ["table_name"],
            },
        ),
        Tool(
            name="get_table_comments",
            description="Retrieve table and column descriptions/comments for a specific table.",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table.",
                    },
                    "owner": {
                        "type": "string",
                        "description": "Schema owner (optional).",
                    },
                },
                "required": ["table_name"],
            },
        ),
        Tool(
            name="health_check",
            description="Check the health and connectivity status of this Oracle warehouse MCP server.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch tool calls to Oracle client methods."""
    try:
        if name == "run_sql":
            query = arguments.get("query", "")
            max_rows = arguments.get("max_rows", server_config.max_rows)
            results = await oracle_client.execute_query(query, max_rows=max_rows)
            return [TextContent(type="text", text=json.dumps(results, default=str, indent=2))]

        elif name == "get_schema":
            tables = await oracle_client.get_all_tables()
            return [TextContent(type="text", text=json.dumps(tables, default=str, indent=2))]

        elif name == "describe_table":
            table_name = arguments.get("table_name", "")
            owner = arguments.get("owner")
            result = await oracle_client.describe_table(table_name, owner)
            return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]

        elif name == "get_table_comments":
            table_name = arguments.get("table_name", "")
            owner = arguments.get("owner")
            result = await oracle_client.get_table_comments(table_name, owner)
            return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]

        elif name == "health_check":
            status = {
                "server_name": server_config.server_name,
                "warehouse_id": server_config.warehouse_id,
                "warehouse_label": server_config.warehouse_label,
                "connected": oracle_client.is_connected,
                "read_only": server_config.read_only,
                "max_rows": server_config.max_rows,
            }
            return [TextContent(type="text", text=json.dumps(status, indent=2))]

        else:
            return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]

    except ReadOnlyViolationError as exc:
        logger.warning("read_only_violation", tool=name, error=str(exc))
        return [TextContent(type="text", text=json.dumps({"error": str(exc)}))]
    except Exception as exc:
        logger.error("tool_call_failed", tool=name, error=str(exc))
        return [TextContent(type="text", text=json.dumps({"error": f"Tool '{name}' failed: {str(exc)}"}))]


def main() -> None:
    """Entry point for the MCP server."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.get_level_from_name(server_config.log_level)
        ),
    )
    logger.info(
        "starting_mcp_server",
        server=server_config.server_name,
        warehouse=server_config.warehouse_id,
        transport=server_config.transport,
    )

    async def run_stdio() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
