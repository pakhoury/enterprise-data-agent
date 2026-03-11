package com.enterprise.agent.controller;

import java.util.Map;
import java.util.Set;

import com.enterprise.agent.model.CacheStats;
import com.enterprise.agent.service.AgentService;
import com.enterprise.agent.service.CacheService;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller for Redis cache management.
 */
@RestController
@RequestMapping("/api/cache")
public class CacheController {

    private final AgentService agentService;
    private final CacheService cacheService;

    public CacheController(AgentService agentService, CacheService cacheService) {
        this.agentService = agentService;
        this.cacheService = cacheService;
    }

    /**
     * Get cache statistics from the agent service.
     */
    @GetMapping("/stats")
    public ResponseEntity<CacheStats> getStats() {
        return ResponseEntity.ok(agentService.getCacheStats());
    }

    /**
     * Get local Redis connection stats.
     */
    @GetMapping("/local-stats")
    public ResponseEntity<Map<String, Object>> getLocalStats() {
        return ResponseEntity.ok(cacheService.getLocalStats());
    }

    /**
     * List cached keys matching a pattern.
     */
    @GetMapping("/keys")
    public ResponseEntity<Set<String>> listKeys(
            @RequestParam(defaultValue = "mcp:*") String pattern) {
        return ResponseEntity.ok(cacheService.listCacheKeys(pattern));
    }

    /**
     * Invalidate cache for a specific warehouse/table.
     */
    @DeleteMapping("/{warehouseId}/{tableName}")
    public ResponseEntity<Map<String, Object>> invalidateTableCache(
            @PathVariable String warehouseId,
            @PathVariable String tableName) {
        return ResponseEntity.ok(agentService.invalidateCache(warehouseId, tableName));
    }

    /**
     * Invalidate all cache for a warehouse.
     */
    @DeleteMapping("/{warehouseId}")
    public ResponseEntity<Map<String, Object>> invalidateWarehouseCache(
            @PathVariable String warehouseId) {
        long deleted = cacheService.invalidateWarehouse(warehouseId);
        return ResponseEntity.ok(Map.of("deleted", deleted, "warehouse", warehouseId));
    }

    /**
     * Invalidate all MCP cache entries.
     */
    @DeleteMapping
    public ResponseEntity<Map<String, Object>> invalidateAllCache() {
        long deleted = cacheService.invalidateAll();
        return ResponseEntity.ok(Map.of("deleted", deleted));
    }
}
