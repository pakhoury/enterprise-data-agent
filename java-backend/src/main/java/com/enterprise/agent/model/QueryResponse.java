package com.enterprise.agent.model;

import java.util.ArrayList;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Response payload from the agent query.
 */
public class QueryResponse {

    private String response;

    @JsonProperty("needs_clarification")
    private boolean needsClarification;

    @JsonProperty("clarification_question")
    private String clarificationQuestion;

    @JsonProperty("tables_queried")
    private List<String> tablesQueried = new ArrayList<>();

    @JsonProperty("cache_hits")
    private int cacheHits;

    @JsonProperty("cache_misses")
    private int cacheMisses;

    private String error;

    public QueryResponse() {
    }

    public String getResponse() {
        return response;
    }

    public void setResponse(String response) {
        this.response = response;
    }

    public boolean isNeedsClarification() {
        return needsClarification;
    }

    public void setNeedsClarification(boolean needsClarification) {
        this.needsClarification = needsClarification;
    }

    public String getClarificationQuestion() {
        return clarificationQuestion;
    }

    public void setClarificationQuestion(String clarificationQuestion) {
        this.clarificationQuestion = clarificationQuestion;
    }

    public List<String> getTablesQueried() {
        return tablesQueried;
    }

    public void setTablesQueried(List<String> tablesQueried) {
        this.tablesQueried = tablesQueried;
    }

    public int getCacheHits() {
        return cacheHits;
    }

    public void setCacheHits(int cacheHits) {
        this.cacheHits = cacheHits;
    }

    public int getCacheMisses() {
        return cacheMisses;
    }

    public void setCacheMisses(int cacheMisses) {
        this.cacheMisses = cacheMisses;
    }

    public String getError() {
        return error;
    }

    public void setError(String error) {
        this.error = error;
    }
}
