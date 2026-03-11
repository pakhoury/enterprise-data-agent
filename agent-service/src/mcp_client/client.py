"""MCP Client Manager — connects to multiple Oracle MCP servers.

Each warehouse gets its own MCP client session. The manager provides
a unified interface for the agent to call tools across warehouses.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.config import WarehouseConfig

logger = structlog.get_logger(__name__)


class McpWarehouseClient:
    """MCP client for a single Oracle warehouse."""

    def __init__(self, config: WarehouseConfig) -> None:
        self._config = config
        self._session: ClientSession | None = None
        self._stdio_context: Any = None
        self._session_context: Any = None

    @property
    def warehouse_id(self) -> str:
        return self._config.warehouse_id

    @property
    def label(self) -> str:
        return self._config.label

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    async def connect(self) -> None:
        """Establish MCP connection to the warehouse server."""
        try:
            server_params = StdioServerParameters(
                command=self._config.mcp_command,
                args=self._config.mcp_args,
                cwd=self._config.mcp_cwd if self._config.mcp_cwd else None,
                env={**self._config.mcp_env} if self._config.mcp_env else None,
            )

            self._stdio_context = stdio_client(server_params)
            read_stream, write_stream = await self._stdio_context.__aenter__()

            self._session_context = ClientSession(read_stream, write_stream)
            self._session = await self._session_context.__aenter__()
            await self._session.initialize()

            logger.info("mcp_client_connected", warehouse=self._config.warehouse_id, label=self._config.label)
        except Exception as exc:
            logger.error("mcp_client_connect_failed", warehouse=self._config.warehouse_id, error=str(exc))
            raise

    async def disconnect(self) -> None:
        """Close the MCP connection."""
        try:
            if self._session_context:
                await self._session_context.__aexit__(None, None, None)
            if self._stdio_context:
                await self._stdio_context.__aexit__(None, None, None)
            self._session = None
            logger.info("mcp_client_disconnected", warehouse=self._config.warehouse_id)
        except Exception as exc:
            logger.warning("mcp_client_disconnect_error", warehouse=self._config.warehouse_id, error=str(exc))

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools on the MCP server."""
        if not self._session:
            raise RuntimeError(f"MCP client for {self._config.warehouse_id} not connected")

        result = await self._session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in result.tools
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the MCP server and return the text result."""
        if not self._session:
            raise RuntimeError(f"MCP client for {self._config.warehouse_id} not connected")

        logger.debug("mcp_tool_call", warehouse=self._config.warehouse_id, tool=tool_name, args=arguments)

        result = await self._session.call_tool(tool_name, arguments)

        # Extract text from response contents
        texts = []
        for content in result.content:
            if hasattr(content, "text"):
                texts.append(content.text)

        return "\n".join(texts)

    async def list_resources(self) -> list[dict[str, Any]]:
        """List available resources (tables) on the MCP server."""
        if not self._session:
            raise RuntimeError(f"MCP client for {self._config.warehouse_id} not connected")

        result = await self._session.list_resources()
        return [
            {
                "uri": str(resource.uri),
                "name": resource.name,
                "description": resource.description,
            }
            for resource in result.resources
        ]


class McpClientManager:
    """Manages MCP client connections to multiple warehouses."""

    def __init__(self) -> None:
        self._clients: dict[str, McpWarehouseClient] = {}

    @property
    def warehouse_ids(self) -> list[str]:
        """Get all registered warehouse IDs."""
        return list(self._clients.keys())

    def get_client(self, warehouse_id: str) -> McpWarehouseClient:
        """Get a specific warehouse client."""
        if warehouse_id not in self._clients:
            raise KeyError(f"Unknown warehouse: {warehouse_id}")
        return self._clients[warehouse_id]

    async def register_warehouse(self, config: WarehouseConfig) -> None:
        """Register and connect to a new warehouse MCP server."""
        client = McpWarehouseClient(config)
        await client.connect()
        self._clients[config.warehouse_id] = client
        logger.info("warehouse_registered", warehouse=config.warehouse_id)

    async def call_tool(self, warehouse_id: str, tool_name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on a specific warehouse's MCP server."""
        client = self.get_client(warehouse_id)
        return await client.call_tool(tool_name, arguments)

    async def call_tool_all(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, str]:
        """Call a tool on all connected warehouses."""
        results: dict[str, str] = {}
        for warehouse_id, client in self._clients.items():
            try:
                results[warehouse_id] = await client.call_tool(tool_name, arguments)
            except Exception as exc:
                results[warehouse_id] = json.dumps({"error": str(exc)})
        return results

    async def disconnect_all(self) -> None:
        """Disconnect from all warehouses."""
        for client in self._clients.values():
            await client.disconnect()
        self._clients.clear()
        logger.info("all_warehouses_disconnected")

    def get_status(self) -> dict[str, Any]:
        """Get connection status for all warehouses."""
        return {
            wid: {
                "label": client.label,
                "connected": client.is_connected,
            }
            for wid, client in self._clients.items()
        }
