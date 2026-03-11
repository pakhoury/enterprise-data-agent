package com.enterprise.agent.model;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * Request payload for searching the RAG metadata store.
 */
public class MetadataSearchRequest {

    @NotBlank(message = "Query must not be blank")
    @Size(max = 500, message = "Query must not exceed 500 characters")
    private String query;

    @Min(1)
    @Max(20)
    @JsonProperty("top_k")
    private int topK = 5;

    @JsonProperty("warehouse_filter")
    private String warehouseFilter;

    public MetadataSearchRequest() {
    }

    public String getQuery() {
        return query;
    }

    public void setQuery(String query) {
        this.query = query;
    }

    public int getTopK() {
        return topK;
    }

    public void setTopK(int topK) {
        this.topK = topK;
    }

    public String getWarehouseFilter() {
        return warehouseFilter;
    }

    public void setWarehouseFilter(String warehouseFilter) {
        this.warehouseFilter = warehouseFilter;
    }
}
