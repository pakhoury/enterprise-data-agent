package com.enterprise.agent.model;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Redis cache statistics model.
 */
public class CacheStats {

    private String status;

    @JsonProperty("total_keys")
    private long totalKeys;

    private long hits;
    private long misses;

    @JsonProperty("evicted_keys")
    private long evictedKeys;

    private String error;

    public CacheStats() {
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public long getTotalKeys() {
        return totalKeys;
    }

    public void setTotalKeys(long totalKeys) {
        this.totalKeys = totalKeys;
    }

    public long getHits() {
        return hits;
    }

    public void setHits(long hits) {
        this.hits = hits;
    }

    public long getMisses() {
        return misses;
    }

    public void setMisses(long misses) {
        this.misses = misses;
    }

    public long getEvictedKeys() {
        return evictedKeys;
    }

    public void setEvictedKeys(long evictedKeys) {
        this.evictedKeys = evictedKeys;
    }

    public String getError() {
        return error;
    }

    public void setError(String error) {
        this.error = error;
    }
}
