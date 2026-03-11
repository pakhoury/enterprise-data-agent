"""LangGraph agent nodes — each node is a step in the agent flow.

Node 1: RAG Search — find relevant tables
Node 2: Query Planning — LLM generates SQL plans
Node 3: Cache Check — look up Redis before MCP
Node 4: MCP Query — execute SQL via MCP servers
Node 5: Reflection — LLM analyzes raw results
Node 6: Response — LLM generates final answer
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.agent.prompts import (
    QUERY_PLANNING_PROMPT,
    REFLECTION_PROMPT,
    RESPONSE_PROMPT,
    SYSTEM_PROMPT,
)
from src.agent.state import AgentPhase, AgentState
from src.cache.redis_cache import RedisCache
from src.config import LlmConfig
from src.mcp_client.client import McpClientManager
from src.rag.store import MetadataStore

logger = structlog.get_logger(__name__)


def _create_llm(config: LlmConfig) -> ChatOpenAI:
    """Create LLM instance from config."""
    return ChatOpenAI(
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        api_key=config.api_key,
    )


class AgentNodes:
    """Container for all LangGraph agent nodes with shared dependencies."""

    def __init__(
        self,
        llm_config: LlmConfig,
        metadata_store: MetadataStore,
        redis_cache: RedisCache,
        mcp_manager: McpClientManager,
    ) -> None:
        self._llm = _create_llm(llm_config)
        self._store = metadata_store
        self._cache = redis_cache
        self._mcp = mcp_manager

    async def rag_search(self, state: AgentState) -> dict[str, Any]:
        """Node 1: Search RAG for relevant table metadata."""
        user_query = state["user_query"]
        logger.info("node_rag_search", query=user_query[:100])

        try:
            matches = await self._store.search(user_query)
            return {
                "rag_matches": matches,
                "phase": AgentPhase.RAG_SEARCH,
            }
        except Exception as exc:
            logger.error("rag_search_failed", error=str(exc))
            return {
                "rag_matches": [],
                "phase": AgentPhase.RAG_SEARCH,
                "error": f"RAG search failed: {exc}",
            }

    async def plan_queries(self, state: AgentState) -> dict[str, Any]:
        """Node 2: LLM generates SQL query plans based on RAG results."""
        user_query = state["user_query"]
        rag_matches = state.get("rag_matches", [])
        conversation_history = state.get("conversation_history", [])
        available_warehouses = state.get("available_warehouses", [])

        logger.info("node_plan_queries", query=user_query[:100], rag_matches=len(rag_matches))

        # Format RAG results for the prompt
        rag_text = json.dumps(rag_matches, indent=2, default=str) if rag_matches else "No tables found in metadata."
        history_text = json.dumps(conversation_history[-10:], default=str) if conversation_history else "None"
        warehouses_text = json.dumps(available_warehouses, default=str) if available_warehouses else "None configured"

        system_msg = SystemMessage(content=SYSTEM_PROMPT.format(warehouses=warehouses_text))
        planning_msg = HumanMessage(
            content=QUERY_PLANNING_PROMPT.format(
                user_query=user_query,
                rag_results=rag_text,
                conversation_history=history_text,
            )
        )

        try:
            response = await self._llm.ainvoke([system_msg, planning_msg])
            content = response.content

            # Parse JSON from LLM response
            plan = self._parse_json_response(content)

            if plan.get("needs_clarification"):
                return {
                    "needs_clarification": True,
                    "clarification_question": plan.get("clarification_question", "Could you clarify your question?"),
                    "phase": AgentPhase.CLARIFICATION,
                }

            return {
                "query_plans": plan.get("query_plans", []),
                "needs_clarification": False,
                "phase": AgentPhase.CACHE_CHECK,
            }
        except Exception as exc:
            logger.error("query_planning_failed", error=str(exc))
            return {
                "query_plans": [],
                "error": f"Query planning failed: {exc}",
                "phase": AgentPhase.ERROR,
            }

    async def check_cache(self, state: AgentState) -> dict[str, Any]:
        """Node 3: Check Redis cache for each planned query."""
        query_plans = state.get("query_plans", [])
        logger.info("node_check_cache", plans=len(query_plans))

        cache_hits: list[dict[str, Any]] = []
        cache_misses: list[dict[str, Any]] = []

        for plan in query_plans:
            warehouse_id = plan.get("warehouse_id", "")
            table_name = plan.get("table_name", "")
            sql = plan.get("sql", "")

            cached = await self._cache.get(warehouse_id, table_name, sql)
            if cached:
                cache_hits.append({
                    **plan,
                    "data": cached.get("data", []),
                    "row_count": cached.get("row_count", 0),
                    "cached": True,
                })
                logger.debug("cache_hit", warehouse=warehouse_id, table=table_name)
            else:
                cache_misses.append(plan)
                logger.debug("cache_miss", warehouse=warehouse_id, table=table_name)

        logger.info("cache_check_complete", hits=len(cache_hits), misses=len(cache_misses))

        return {
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "phase": AgentPhase.MCP_QUERY if cache_misses else AgentPhase.REFLECTION,
        }

    async def execute_mcp_queries(self, state: AgentState) -> dict[str, Any]:
        """Node 4: Execute cache-missed queries via MCP servers."""
        cache_misses = state.get("cache_misses", [])
        cache_hits = state.get("cache_hits", [])

        logger.info("node_mcp_queries", queries=len(cache_misses))

        query_results: list[dict[str, Any]] = list(cache_hits)  # Start with cache hits

        for plan in cache_misses:
            warehouse_id = plan.get("warehouse_id", "")
            table_name = plan.get("table_name", "")
            sql = plan.get("sql", "")
            purpose = plan.get("purpose", "")

            try:
                result_text = await self._mcp.call_tool(
                    warehouse_id,
                    "run_sql",
                    {"query": sql, "max_rows": 1000},
                )

                data = json.loads(result_text) if isinstance(result_text, str) else result_text

                result_entry = {
                    "warehouse_id": warehouse_id,
                    "table_name": table_name,
                    "sql": sql,
                    "purpose": purpose,
                    "data": data,
                    "row_count": len(data) if isinstance(data, list) else 0,
                    "cached": False,
                    "error": "",
                }
                query_results.append(result_entry)

                # Cache the result
                await self._cache.put(
                    warehouse_id,
                    table_name,
                    sql,
                    {"data": data, "row_count": len(data) if isinstance(data, list) else 0},
                )

            except Exception as exc:
                logger.error("mcp_query_failed", warehouse=warehouse_id, sql=sql[:200], error=str(exc))
                query_results.append({
                    "warehouse_id": warehouse_id,
                    "table_name": table_name,
                    "sql": sql,
                    "purpose": purpose,
                    "data": [],
                    "row_count": 0,
                    "cached": False,
                    "error": str(exc),
                })

        return {
            "query_results": query_results,
            "phase": AgentPhase.REFLECTION,
        }

    async def reflect(self, state: AgentState) -> dict[str, Any]:
        """Node 5: LLM analyzes query results — trends, comparisons, flags."""
        user_query = state["user_query"]
        query_results = state.get("query_results", [])
        conversation_history = state.get("conversation_history", [])

        logger.info("node_reflect", results=len(query_results))

        results_text = json.dumps(query_results, indent=2, default=str)
        history_text = json.dumps(conversation_history[-10:], default=str) if conversation_history else "None"

        msg = HumanMessage(
            content=REFLECTION_PROMPT.format(
                user_query=user_query,
                query_results=results_text,
                conversation_history=history_text,
            )
        )

        try:
            response = await self._llm.ainvoke([msg])
            return {
                "analysis": response.content,
                "phase": AgentPhase.RESPONSE,
            }
        except Exception as exc:
            logger.error("reflection_failed", error=str(exc))
            return {
                "analysis": f"Analysis failed: {exc}. Raw data available: {len(query_results)} results.",
                "phase": AgentPhase.RESPONSE,
            }

    async def generate_response(self, state: AgentState) -> dict[str, Any]:
        """Node 6: Generate the final user-facing response."""
        user_query = state["user_query"]
        analysis = state.get("analysis", "")
        query_results = state.get("query_results", [])

        logger.info("node_generate_response")

        # Build data summary
        data_summary_parts = []
        for r in query_results:
            data_summary_parts.append(
                f"[{r.get('warehouse_id', '?')}/{r.get('table_name', '?')}] "
                f"{'CACHED' if r.get('cached') else 'LIVE'} — "
                f"{r.get('row_count', 0)} rows"
                f"{' — ERROR: ' + r.get('error', '') if r.get('error') else ''}"
            )
        data_summary = "\n".join(data_summary_parts) if data_summary_parts else "No data retrieved."

        msg = HumanMessage(
            content=RESPONSE_PROMPT.format(
                user_query=user_query,
                analysis=analysis,
                data_summary=data_summary,
            )
        )

        try:
            response = await self._llm.ainvoke([msg])
            return {
                "response": response.content,
                "phase": AgentPhase.RESPONSE,
            }
        except Exception as exc:
            logger.error("response_generation_failed", error=str(exc))
            return {
                "response": f"I retrieved data but couldn't generate a summary. Here's what I found:\n\n{analysis}",
                "phase": AgentPhase.ERROR,
            }

    @staticmethod
    def _parse_json_response(content: str) -> dict[str, Any]:
        """Extract JSON from LLM response, handling markdown code blocks."""
        text = content.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [line for line in lines if not line.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass

            logger.warning("json_parse_failed", content=text[:200])
            return {"needs_clarification": False, "query_plans": []}
