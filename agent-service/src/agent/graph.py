"""LangGraph agent graph — orchestrates the full query flow.

Flow:
  rag_search → plan_queries → [clarification?] → check_cache → [mcp_query?] → reflect → respond

Conditional edges:
  - After plan_queries: if needs_clarification → END (return question)
  - After check_cache: if all cached → skip mcp_query → reflect
  - After mcp_query → reflect → respond → END
"""

from __future__ import annotations

from typing import Any

import structlog
from langgraph.graph import END, StateGraph

from src.agent.nodes import AgentNodes
from src.agent.state import AgentPhase, AgentState
from src.cache.redis_cache import RedisCache
from src.config import LlmConfig
from src.mcp_client.client import McpClientManager
from src.rag.store import MetadataStore

logger = structlog.get_logger(__name__)


def _route_after_planning(state: AgentState) -> str:
    """Route after query planning: clarification or cache check."""
    if state.get("needs_clarification"):
        return "end_clarification"
    if not state.get("query_plans"):
        return "generate_response"  # No plans = can't query, go straight to response
    return "check_cache"


def _route_after_cache(state: AgentState) -> str:
    """Route after cache check: MCP query or skip to reflection."""
    cache_misses = state.get("cache_misses", [])
    if cache_misses:
        return "execute_mcp_queries"
    # All hits — combine cache hits into query_results and go to reflection
    return "promote_cache_hits"


def _promote_cache_hits(state: AgentState) -> dict[str, Any]:
    """When all queries are cache hits, promote them to query_results."""
    return {
        "query_results": state.get("cache_hits", []),
        "phase": AgentPhase.REFLECTION,
    }


def build_agent_graph(
    llm_config: LlmConfig,
    metadata_store: MetadataStore,
    redis_cache: RedisCache,
    mcp_manager: McpClientManager,
) -> StateGraph:
    """Build and compile the LangGraph agent workflow.

    Returns a compiled graph ready for invocation.
    """
    nodes = AgentNodes(
        llm_config=llm_config,
        metadata_store=metadata_store,
        redis_cache=redis_cache,
        mcp_manager=mcp_manager,
    )

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("rag_search", nodes.rag_search)
    graph.add_node("plan_queries", nodes.plan_queries)
    graph.add_node("check_cache", nodes.check_cache)
    graph.add_node("promote_cache_hits", _promote_cache_hits)
    graph.add_node("execute_mcp_queries", nodes.execute_mcp_queries)
    graph.add_node("reflect", nodes.reflect)
    graph.add_node("generate_response", nodes.generate_response)

    # Set entry point
    graph.set_entry_point("rag_search")

    # Add edges
    graph.add_edge("rag_search", "plan_queries")

    # Conditional: after planning, clarification or cache check
    graph.add_conditional_edges(
        "plan_queries",
        _route_after_planning,
        {
            "end_clarification": END,
            "check_cache": "check_cache",
            "generate_response": "generate_response",
        },
    )

    # Conditional: after cache, MCP or straight to reflection
    graph.add_conditional_edges(
        "check_cache",
        _route_after_cache,
        {
            "execute_mcp_queries": "execute_mcp_queries",
            "promote_cache_hits": "promote_cache_hits",
        },
    )

    # After promote_cache_hits → reflect
    graph.add_edge("promote_cache_hits", "reflect")

    # After MCP queries → reflect
    graph.add_edge("execute_mcp_queries", "reflect")

    # After reflect → generate response
    graph.add_edge("reflect", "generate_response")

    # After response → END
    graph.add_edge("generate_response", END)

    compiled = graph.compile()
    logger.info("agent_graph_compiled")
    return compiled
