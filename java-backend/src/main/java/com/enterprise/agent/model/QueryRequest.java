package com.enterprise.agent.model;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * Request payload for submitting a natural language query.
 */
public class QueryRequest {

    @NotBlank(message = "Query must not be blank")
    @Size(max = 2000, message = "Query must not exceed 2000 characters")
    private String query;

    private List<Map<String, String>> conversationHistory = new ArrayList<>();

    private String warehouseFilter;

    public QueryRequest() {
    }

    public QueryRequest(String query) {
        this.query = query;
    }

    public String getQuery() {
        return query;
    }

    public void setQuery(String query) {
        this.query = query;
    }

    public List<Map<String, String>> getConversationHistory() {
        return conversationHistory;
    }

    public void setConversationHistory(List<Map<String, String>> conversationHistory) {
        this.conversationHistory = conversationHistory;
    }

    public String getWarehouseFilter() {
        return warehouseFilter;
    }

    public void setWarehouseFilter(String warehouseFilter) {
        this.warehouseFilter = warehouseFilter;
    }
}
