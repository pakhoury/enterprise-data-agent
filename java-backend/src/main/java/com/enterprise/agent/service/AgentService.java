package com.enterprise.agent.service;

import java.util.List;
import java.util.Map;

import com.enterprise.agent.model.CacheStats;
import com.enterprise.agent.model.MetadataSearchRequest;
import com.enterprise.agent.model.QueryRequest;
import com.enterprise.agent.model.QueryResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

/**
 * Service layer for communicating with the Python LangGraph agent.
 *
 * <p>All agent operations (query, metadata sync/search, cache stats)
 * are delegated to the Python agent service via REST calls.
 */
@Service
public class AgentService {

    private static final Logger log = LoggerFactory.getLogger(AgentService.class);

    private final WebClient agentWebClient;

    public AgentService(WebClient agentWebClient) {
        this.agentWebClient = agentWebClient;
    }

    /**
     * Submit a natural language query to the LangGraph agent.
     */
    public QueryResponse query(QueryRequest request) {
        log.info("Submitting query to agent: {}", truncate(request.getQuery(), 100));

        try {
            QueryResponse response = agentWebClient.post()
                    .uri("/query")
                    .bodyValue(Map.of(
                            "query", request.getQuery(),
                            "conversation_history", request.getConversationHistory(),
                            "warehouse_filter", request.getWarehouseFilter() != null ? request.getWarehouseFilter() : ""
                    ))
                    .retrieve()
                    .bodyToMono(QueryResponse.class)
                    .block();

            if (response == null) {
                throw new RuntimeException("Agent returned null response");
            }

            log.info("Agent query complete: tables={}, cache_hits={}, cache_misses={}",
                    response.getTablesQueried().size(),
                    response.getCacheHits(),
                    response.getCacheMisses());

            return response;

        } catch (WebClientResponseException e) {
            log.error("Agent service error: status={}, body={}", e.getStatusCode(), e.getResponseBodyAsString());
            QueryResponse errorResponse = new QueryResponse();
            errorResponse.setResponse("Agent service error: " + e.getMessage());
            errorResponse.setError(e.getResponseBodyAsString());
            return errorResponse;
        } catch (Exception e) {
            log.error("Failed to reach agent service", e);
            QueryResponse errorResponse = new QueryResponse();
            errorResponse.setResponse("Unable to reach the agent service. Please try again.");
            errorResponse.setError(e.getMessage());
            return errorResponse;
        }
    }

    /**
     * Trigger metadata sync across all warehouses.
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> syncMetadata() {
        log.info("Triggering metadata sync");

        return agentWebClient.post()
                .uri("/metadata/sync")
                .retrieve()
                .bodyToMono(Map.class)
                .block();
    }

    /**
     * Search the RAG metadata store.
     */
    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> searchMetadata(MetadataSearchRequest request) {
        log.info("Searching metadata: query={}", truncate(request.getQuery(), 100));

        return agentWebClient.post()
                .uri("/metadata/search")
                .bodyValue(Map.of(
                        "query", request.getQuery(),
                        "top_k", request.getTopK(),
                        "warehouse_filter", request.getWarehouseFilter() != null ? request.getWarehouseFilter() : ""
                ))
                .retrieve()
                .bodyToMono(new ParameterizedTypeReference<List<Map<String, Object>>>() {})
                .block();
    }

    /**
     * Get cache statistics from the agent service.
     */
    public CacheStats getCacheStats() {
        return agentWebClient.get()
                .uri("/cache/stats")
                .retrieve()
                .bodyToMono(CacheStats.class)
                .block();
    }

    /**
     * Invalidate cache for a specific warehouse/table.
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> invalidateCache(String warehouseId, String tableName) {
        log.info("Invalidating cache: warehouse={}, table={}", warehouseId, tableName);

        return agentWebClient.delete()
                .uri("/cache/{warehouseId}/{tableName}", warehouseId, tableName)
                .retrieve()
                .bodyToMono(Map.class)
                .block();
    }

    /**
     * Get warehouse connection statuses.
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getWarehouses() {
        return agentWebClient.get()
                .uri("/warehouses")
                .retrieve()
                .bodyToMono(Map.class)
                .block();
    }

    /**
     * Get agent service health status.
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getAgentHealth() {
        try {
            return agentWebClient.get()
                    .uri("/health")
                    .retrieve()
                    .bodyToMono(Map.class)
                    .block();
        } catch (Exception e) {
            return Map.of("status", "unreachable", "error", e.getMessage());
        }
    }

    private static String truncate(String s, int maxLen) {
        if (s == null) return "";
        return s.length() <= maxLen ? s : s.substring(0, maxLen) + "...";
    }
}
