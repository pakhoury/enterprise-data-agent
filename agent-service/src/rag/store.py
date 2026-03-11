"""RAG vector store for warehouse metadata discovery.

Stores table names, column names, descriptions, and sample data.
The agent searches this first to find relevant tables before querying MCP servers.
"""

from __future__ import annotations

from typing import Any

import chromadb
import structlog

from src.config import RagConfig

logger = structlog.get_logger(__name__)


class MetadataStore:
    """ChromaDB-backed vector store for warehouse table metadata."""

    def __init__(self, config: RagConfig) -> None:
        self._config = config
        self._client: chromadb.ClientAPI | None = None
        self._collection: chromadb.Collection | None = None

    async def initialize(self) -> None:
        """Initialize ChromaDB client and collection."""
        try:
            self._client = chromadb.PersistentClient(path=self._config.persist_directory)
            self._collection = self._client.get_or_create_collection(
                name=self._config.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                "rag_store_initialized",
                collection=self._config.collection_name,
                persist_dir=self._config.persist_directory,
                count=self._collection.count(),
            )
        except Exception as exc:
            logger.error("rag_store_init_failed", error=str(exc))
            raise

    async def upsert_table_metadata(
        self,
        warehouse_id: str,
        table_name: str,
        owner: str,
        columns: list[dict[str, Any]],
        description: str = "",
        sample_rows: list[dict[str, Any]] | None = None,
        row_count: int | None = None,
    ) -> None:
        """Insert or update metadata for a single table."""
        if not self._collection:
            raise RuntimeError("MetadataStore not initialized")

        column_names = [col.get("COLUMN_NAME", col.get("column_name", "")) for col in columns]
        column_types = [
            f"{col.get('COLUMN_NAME', col.get('column_name', ''))}:{col.get('DATA_TYPE', col.get('data_type', ''))}"
            for col in columns
        ]

        # Build rich text document for embedding
        doc_parts = [
            f"Table: {owner}.{table_name}",
            f"Warehouse: {warehouse_id}",
            f"Description: {description}" if description else "",
            f"Columns: {', '.join(column_names)}",
            f"Column types: {', '.join(column_types)}",
            f"Row count: {row_count}" if row_count else "",
        ]

        if sample_rows:
            sample_str = str(sample_rows[:3])
            if len(sample_str) > 500:
                sample_str = sample_str[:500] + "..."
            doc_parts.append(f"Sample data: {sample_str}")

        document = "\n".join(part for part in doc_parts if part)

        metadata = {
            "warehouse_id": warehouse_id,
            "table_name": table_name,
            "owner": owner,
            "columns": ",".join(column_names),
            "column_count": len(column_names),
            "row_count": row_count or 0,
            "description": description,
        }

        doc_id = f"{warehouse_id}:{owner}:{table_name}"

        self._collection.upsert(
            ids=[doc_id],
            documents=[document],
            metadatas=[metadata],
        )
        logger.debug("metadata_upserted", doc_id=doc_id)

    async def search(
        self, query: str, top_k: int | None = None, warehouse_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for relevant tables based on a natural language query.

        Returns list of matches with table metadata and relevance scores.
        """
        if not self._collection:
            raise RuntimeError("MetadataStore not initialized")

        k = top_k or self._config.search_top_k

        where_filter = None
        if warehouse_filter:
            where_filter = {"warehouse_id": warehouse_filter}

        results = self._collection.query(
            query_texts=[query],
            n_results=k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        matches = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 1.0
                document = results["documents"][0][i] if results["documents"] else ""

                matches.append({
                    "id": doc_id,
                    "score": 1.0 - distance,  # Convert distance to similarity
                    "table_name": metadata.get("table_name", ""),
                    "warehouse_id": metadata.get("warehouse_id", ""),
                    "owner": metadata.get("owner", ""),
                    "columns": metadata.get("columns", "").split(",") if metadata.get("columns") else [],
                    "description": metadata.get("description", ""),
                    "row_count": metadata.get("row_count", 0),
                    "document": document,
                })

        logger.info("rag_search", query=query[:100], matches=len(matches))
        return matches

    async def bulk_upsert(self, warehouse_id: str, tables: list[dict[str, Any]]) -> int:
        """Bulk upsert metadata for multiple tables from a warehouse."""
        count = 0
        for table in tables:
            try:
                await self.upsert_table_metadata(
                    warehouse_id=warehouse_id,
                    table_name=table.get("table_name", ""),
                    owner=table.get("owner", ""),
                    columns=table.get("columns", []),
                    description=table.get("description", ""),
                    sample_rows=table.get("sample_rows"),
                    row_count=table.get("row_count"),
                )
                count += 1
            except Exception as exc:
                logger.warning("bulk_upsert_failed", table=table.get("table_name"), error=str(exc))
        logger.info("bulk_upsert_complete", warehouse=warehouse_id, count=count)
        return count

    async def delete_warehouse(self, warehouse_id: str) -> None:
        """Remove all metadata for a specific warehouse."""
        if not self._collection:
            return

        # ChromaDB doesn't support delete by metadata filter directly in all versions,
        # so we query first then delete by IDs
        results = self._collection.get(
            where={"warehouse_id": warehouse_id},
            include=[],
        )
        if results and results["ids"]:
            self._collection.delete(ids=results["ids"])
            logger.info("warehouse_metadata_deleted", warehouse=warehouse_id, count=len(results["ids"]))

    async def get_stats(self) -> dict[str, Any]:
        """Get store statistics."""
        if not self._collection:
            return {"status": "not_initialized"}

        return {
            "status": "ready",
            "collection": self._config.collection_name,
            "total_documents": self._collection.count(),
        }
