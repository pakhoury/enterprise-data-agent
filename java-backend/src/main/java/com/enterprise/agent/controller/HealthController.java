package com.enterprise.agent.controller;

import java.util.Map;

import com.enterprise.agent.model.HealthResponse;
import com.enterprise.agent.service.AgentService;
import com.enterprise.agent.service.CacheService;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Health check controller aggregating statuses from all services.
 */
@RestController
@RequestMapping("/api/health")
public class HealthController {

    private final AgentService agentService;
    private final CacheService cacheService;

    public HealthController(AgentService agentService, CacheService cacheService) {
        this.agentService = agentService;
        this.cacheService = cacheService;
    }

    /**
     * Comprehensive health check across all services.
     *
     * <p>Checks:
     * <ul>
     *   <li>Redis connectivity (direct from Java)</li>
     *   <li>Agent service health (Python LangGraph service)</li>
     *   <li>Warehouse MCP connections (via agent service)</li>
     * </ul>
     */
    @GetMapping
    public ResponseEntity<HealthResponse> healthCheck() {
        Map<String, Object> agentHealth = agentService.getAgentHealth();
        Map<String, Object> localRedis = cacheService.getLocalStats();

        HealthResponse response = new HealthResponse();

        // Determine overall status
        boolean agentOk = "healthy".equals(agentHealth.get("status"));
        boolean redisOk = "connected".equals(localRedis.get("status"));

        if (agentOk && redisOk) {
            response.setStatus("healthy");
        } else if (agentOk || redisOk) {
            response.setStatus("degraded");
        } else {
            response.setStatus("unhealthy");
        }

        response.setAgentService(agentHealth);
        response.setRedis(localRedis);

        // Pull sub-statuses from agent health if available
        if (agentHealth.containsKey("rag")) {
            @SuppressWarnings("unchecked")
            Map<String, Object> rag = (Map<String, Object>) agentHealth.get("rag");
            response.setRag(rag);
        }
        if (agentHealth.containsKey("warehouses")) {
            @SuppressWarnings("unchecked")
            Map<String, Object> warehouses = (Map<String, Object>) agentHealth.get("warehouses");
            response.setWarehouses(warehouses);
        }

        return ResponseEntity.ok(response);
    }
}
