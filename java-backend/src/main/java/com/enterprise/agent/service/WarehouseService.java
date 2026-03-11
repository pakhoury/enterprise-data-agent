package com.enterprise.agent.service;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * Service for warehouse management operations.
 *
 * <p>Delegates to the Python agent service for actual MCP server
 * connections. Provides warehouse listing and status checking.
 */
@Service
public class WarehouseService {

    private static final Logger log = LoggerFactory.getLogger(WarehouseService.class);

    private final AgentService agentService;

    public WarehouseService(AgentService agentService) {
        this.agentService = agentService;
    }

    /**
     * Get status of all connected warehouses.
     */
    public Map<String, Object> getAllStatuses() {
        return agentService.getWarehouses();
    }

    /**
     * Trigger metadata sync and return results.
     */
    public Map<String, Object> syncAllMetadata() {
        log.info("Triggering full metadata sync across all warehouses");
        return agentService.syncMetadata();
    }
}
