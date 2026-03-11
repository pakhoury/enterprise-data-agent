package com.enterprise.agent.service;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

/**
 * Direct Redis cache operations from the Java side.
 *
 * <p>Provides cache stats, key inspection, and bulk operations
 * complementing the agent service's own Redis usage.
 */
@Service
public class CacheService {

    private static final Logger log = LoggerFactory.getLogger(CacheService.class);

    private final RedisTemplate<String, Object> redisTemplate;

    public CacheService(RedisTemplate<String, Object> redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    /**
     * Get local Redis connection stats.
     */
    public Map<String, Object> getLocalStats() {
        Map<String, Object> stats = new HashMap<>();
        try {
            RedisConnectionFactory factory = redisTemplate.getConnectionFactory();
            if (factory != null) {
                stats.put("status", "connected");
                // Get key count via scan with mcp:* pattern
                Set<String> mcpKeys = redisTemplate.keys("mcp:*");
                stats.put("mcp_cache_keys", mcpKeys != null ? mcpKeys.size() : 0);
            } else {
                stats.put("status", "disconnected");
            }
        } catch (Exception e) {
            stats.put("status", "error");
            stats.put("error", e.getMessage());
        }
        return stats;
    }

    /**
     * List all cached MCP query keys.
     */
    public Set<String> listCacheKeys(String pattern) {
        String searchPattern = pattern != null ? pattern : "mcp:*";
        return redisTemplate.keys(searchPattern);
    }

    /**
     * Invalidate all cache entries for a warehouse.
     */
    public long invalidateWarehouse(String warehouseId) {
        Set<String> keys = redisTemplate.keys("mcp:" + warehouseId + ":*");
        if (keys != null && !keys.isEmpty()) {
            Long deleted = redisTemplate.delete(keys);
            log.info("Invalidated {} keys for warehouse {}", deleted, warehouseId);
            return deleted != null ? deleted : 0;
        }
        return 0;
    }

    /**
     * Invalidate all MCP cache entries.
     */
    public long invalidateAll() {
        Set<String> keys = redisTemplate.keys("mcp:*");
        if (keys != null && !keys.isEmpty()) {
            Long deleted = redisTemplate.delete(keys);
            log.info("Invalidated all {} MCP cache keys", deleted);
            return deleted != null ? deleted : 0;
        }
        return 0;
    }
}
