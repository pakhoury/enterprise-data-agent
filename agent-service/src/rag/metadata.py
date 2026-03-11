"""Metadata management — syncs warehouse schemas into the RAG vector store.

On startup or refresh, connects to each MCP server, pulls table schemas,
and pushes metadata into the vector store for agent discovery.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from src.mcp_client.client import McpClientManager
from src.rag.store import MetadataStore

logger = structlog.get_logger(__name__)


class MetadataSyncer:
    """Syncs warehouse table metadata from MCP servers into the RAG store."""

    def __init__(self, mcp_manager: McpClientManager, store: MetadataStore) -> None:
        self._mcp = mcp_manager
        self._store = store

    async def sync_warehouse(self, warehouse_id: str) -> int:
        """Sync all table metadata from a single warehouse into the vector store."""
        logger.info("sync_warehouse_start", warehouse=warehouse_id)

        try:
            # Step 1: Get all tables via MCP
            schema_result = await self._mcp.call_tool(warehouse_id, "get_schema", {})
            if not schema_result:
                logger.warning("sync_no_schema", warehouse=warehouse_id)
                return 0

            tables_raw = json.loads(schema_result) if isinstance(schema_result, str) else schema_result

            # Step 2: For each table, get detailed schema
            enriched_tables: list[dict[str, Any]] = []
            for table in tables_raw:
                table_name = table.get("TABLE_NAME", table.get("table_name", ""))
                owner = table.get("OWNER", table.get("owner", ""))

                try:
                    detail_result = await self._mcp.call_tool(
                        warehouse_id,
                        "describe_table",
                        {"table_name": table_name, "owner": owner},
                    )
                    detail = json.loads(detail_result) if isinstance(detail_result, str) else detail_result

                    # Try to get comments
                    comments_result = await self._mcp.call_tool(
                        warehouse_id,
                        "get_table_comments",
                        {"table_name": table_name, "owner": owner},
                    )
                    comments = json.loads(comments_result) if isinstance(comments_result, str) else comments_result

                    enriched_tables.append({
                        "table_name": table_name,
                        "owner": owner,
                        "columns": detail.get("columns", []),
                        "description": comments.get("table_comment", ""),
                        "sample_rows": detail.get("sample_rows", []),
                        "row_count": table.get("NUM_ROWS", table.get("num_rows")),
                    })
                except Exception as exc:
                    logger.warning(
                        "sync_table_detail_failed",
                        warehouse=warehouse_id,
                        table=table_name,
                        error=str(exc),
                    )
                    # Still add basic info
                    enriched_tables.append({
                        "table_name": table_name,
                        "owner": owner,
                        "columns": [],
                        "description": "",
                        "row_count": table.get("NUM_ROWS", table.get("num_rows")),
                    })

            # Step 3: Bulk upsert into vector store
            count = await self._store.bulk_upsert(warehouse_id, enriched_tables)
            logger.info("sync_warehouse_complete", warehouse=warehouse_id, tables_synced=count)
            return count

        except Exception as exc:
            logger.error("sync_warehouse_failed", warehouse=warehouse_id, error=str(exc))
            return 0

    async def sync_all(self) -> dict[str, int]:
        """Sync metadata from all connected warehouses."""
        results: dict[str, int] = {}
        for warehouse_id in self._mcp.warehouse_ids:
            results[warehouse_id] = await self.sync_warehouse(warehouse_id)
        return results
