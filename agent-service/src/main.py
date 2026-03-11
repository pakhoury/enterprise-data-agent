"""FastAPI application for the Enterprise Data Agent Service.

Exposes REST endpoints for:
- /query — submit a natural language query to the agent
- /metadata/sync — trigger RAG metadata sync from warehouses
- /metadata/search — search the RAG store directly
- /cache/stats — view Redis cache statistics
- /warehouses — list connected warehouse statuses
- /health — service health check
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Any

import structlog
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.agent.graph import build_agent_graph
from src.cache.redis_cache import RedisCache
from src.config import (
    AgentServiceConfig,
    LlmConfig,
    RagConfig,
    RedisConfig,
    WarehouseConfig,
)
from src.mcp_client.client import McpClientManager
from src.rag.metadata import MetadataSyncer
from src.rag.store import MetadataStore

load_dotenv()

logger = structlog.get_logger(__name__)

# Global service instances
service_config = AgentServiceConfig()
redis_config = RedisConfig()
rag_config = RagConfig()
llm_config = LlmConfig()

redis_cache = RedisCache(redis_config)
metadata_store = MetadataStore(rag_config)
mcp_manager = McpClientManager()
agent_graph = None
metadata_syncer = None


def _load_warehouse_configs() -> list[WarehouseConfig]:
    """Load warehouse configurations from JSON file or environment."""
    config_path = service_config.warehouses_config_path

    if os.path.exists(config_path):
        with open(config_path) as f:
            warehouses = json.load(f)
        return [WarehouseConfig(**w) for w in warehouses]

    # Fallback: single warehouse from environment
    return [
        WarehouseConfig(
            warehouse_id=os.getenv("MCP_WAREHOUSE_ID", "hq"),
            label=os.getenv("MCP_WAREHOUSE_LABEL", "HQ Warehouse"),
            mcp_url=os.getenv("MCP_URL", "http://localhost:8080/mcp"),
        )
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle — initialize and teardown services."""
    global agent_graph, metadata_syncer

    logger.info("agent_service_starting")

    # Initialize Redis
    await redis_cache.initialize()

    # Initialize RAG store
    await metadata_store.initialize()

    # Connect to warehouse MCP servers
    warehouse_configs = _load_warehouse_configs()
    for wc in warehouse_configs:
        try:
            await mcp_manager.register_warehouse(wc)
        except Exception as exc:
            logger.warning("warehouse_connect_failed", warehouse=wc.warehouse_id, error=str(exc))

    # Build LangGraph agent
    agent_graph = build_agent_graph(
        llm_config=llm_config,
        metadata_store=metadata_store,
        redis_cache=redis_cache,
        mcp_manager=mcp_manager,
    )

    # Create metadata syncer
    metadata_syncer = MetadataSyncer(mcp_manager, metadata_store)

    logger.info("agent_service_ready", warehouses=mcp_manager.warehouse_ids)

    yield

    # Shutdown
    await mcp_manager.disconnect_all()
    await redis_cache.close()
    logger.info("agent_service_stopped")


app = FastAPI(
    title="Enterprise Data Agent",
    description="LangGraph-based AI agent for multi-warehouse Oracle data querying",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """User query request."""

    query: str = Field(..., min_length=1, max_length=2000, description="Natural language query")
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list, description="Previous conversation turns"
    )
    warehouse_filter: str | None = Field(None, description="Optional: limit to a specific warehouse")


class QueryResponse(BaseModel):
    """Agent query response."""

    response: str
    needs_clarification: bool = False
    clarification_question: str = ""
    tables_queried: list[str] = Field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    error: str = ""


class MetadataSyncResponse(BaseModel):
    """Metadata sync result."""

    warehouses_synced: dict[str, int]


class MetadataSearchRequest(BaseModel):
    """RAG search request."""

    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(5, ge=1, le=20)
    warehouse_filter: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    redis: dict[str, Any]
    rag: dict[str, Any]
    warehouses: dict[str, Any]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/query", response_model=QueryResponse)
async def query_agent(request: QueryRequest) -> QueryResponse:
    """Submit a natural language query to the agent."""
    if agent_graph is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    logger.info("query_received", query=request.query[:100])

    # Build initial state
    initial_state = {
        "user_query": request.query,
        "conversation_history": request.conversation_history,
        "available_warehouses": [
            {"warehouse_id": wid, "label": mcp_manager.get_client(wid).label}
            for wid in mcp_manager.warehouse_ids
        ],
        "phase": "init",
        "iteration": 0,
    }

    try:
        # Run the agent graph
        final_state = await agent_graph.ainvoke(initial_state)

        # Extract results
        needs_clarification = final_state.get("needs_clarification", False)
        clarification_question = final_state.get("clarification_question", "")
        response_text = final_state.get("response", "")
        query_results = final_state.get("query_results", [])
        cache_hits_list = final_state.get("cache_hits", [])
        cache_misses_list = final_state.get("cache_misses", [])
        error = final_state.get("error", "")

        if needs_clarification:
            response_text = clarification_question

        tables_queried = list({
            f"{r.get('warehouse_id', '?')}.{r.get('table_name', '?')}"
            for r in query_results
        })

        return QueryResponse(
            response=response_text or "No response generated.",
            needs_clarification=needs_clarification,
            clarification_question=clarification_question,
            tables_queried=tables_queried,
            cache_hits=len(cache_hits_list),
            cache_misses=len(cache_misses_list),
            error=error,
        )

    except Exception as exc:
        logger.error("query_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Agent query failed: {exc}") from exc


@app.post("/metadata/sync", response_model=MetadataSyncResponse)
async def sync_metadata() -> MetadataSyncResponse:
    """Trigger metadata sync from all connected warehouses into RAG store."""
    if metadata_syncer is None:
        raise HTTPException(status_code=503, detail="Metadata syncer not initialized")

    results = await metadata_syncer.sync_all()
    return MetadataSyncResponse(warehouses_synced=results)


@app.post("/metadata/search")
async def search_metadata(request: MetadataSearchRequest) -> list[dict[str, Any]]:
    """Search the RAG metadata store directly."""
    return await metadata_store.search(
        query=request.query,
        top_k=request.top_k,
        warehouse_filter=request.warehouse_filter,
    )


@app.get("/cache/stats")
async def cache_stats() -> dict[str, Any]:
    """Get Redis cache statistics."""
    return await redis_cache.get_stats()


@app.delete("/cache/{warehouse_id}/{table_name}")
async def invalidate_cache(warehouse_id: str, table_name: str) -> dict[str, Any]:
    """Invalidate cache for a specific warehouse/table."""
    deleted = await redis_cache.invalidate_table(warehouse_id, table_name)
    return {"deleted": deleted}


@app.get("/warehouses")
async def list_warehouses() -> dict[str, Any]:
    """List all connected warehouse MCP servers."""
    return mcp_manager.get_status()


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Service health check."""
    redis_stats = await redis_cache.get_stats()
    rag_stats = await metadata_store.get_stats()
    warehouse_status = mcp_manager.get_status()

    overall = "healthy"
    if redis_stats.get("status") != "connected":
        overall = "degraded"
    if not warehouse_status:
        overall = "degraded"

    return HealthResponse(
        status=overall,
        redis=redis_stats,
        rag=rag_stats,
        warehouses=warehouse_status,
    )


def main() -> None:
    """Entry point for the agent service."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.get_level_from_name(service_config.log_level)
        ),
    )
    uvicorn.run(
        "src.main:app",
        host=service_config.host,
        port=service_config.port,
        reload=False,
        log_level=service_config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
