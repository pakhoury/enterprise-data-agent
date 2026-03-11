package com.enterprise.agent.model;

import java.util.Map;

/**
 * Health check response aggregating all service statuses.
 */
public class HealthResponse {

    private String status;
    private Map<String, Object> redis;
    private Map<String, Object> rag;
    private Map<String, Object> warehouses;
    private Map<String, Object> agentService;

    public HealthResponse() {
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Map<String, Object> getRedis() {
        return redis;
    }

    public void setRedis(Map<String, Object> redis) {
        this.redis = redis;
    }

    public Map<String, Object> getRag() {
        return rag;
    }

    public void setRag(Map<String, Object> rag) {
        this.rag = rag;
    }

    public Map<String, Object> getWarehouses() {
        return warehouses;
    }

    public void setWarehouses(Map<String, Object> warehouses) {
        this.warehouses = warehouses;
    }

    public Map<String, Object> getAgentService() {
        return agentService;
    }

    public void setAgentService(Map<String, Object> agentService) {
        this.agentService = agentService;
    }
}
