package com.enterprise.agent.controller;

import com.enterprise.agent.model.QueryRequest;
import com.enterprise.agent.model.QueryResponse;
import com.enterprise.agent.service.AgentService;

import jakarta.validation.Valid;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller for natural language query operations.
 *
 * <p>The main entry point for users to interact with the data agent.
 * Accepts natural language queries, routes them through the LangGraph
 * agent, and returns structured responses.
 */
@RestController
@RequestMapping("/api/query")
public class QueryController {

    private static final Logger log = LoggerFactory.getLogger(QueryController.class);

    private final AgentService agentService;

    public QueryController(AgentService agentService) {
        this.agentService = agentService;
    }

    /**
     * Submit a natural language query to the data agent.
     *
     * <p>The agent will:
     * <ol>
     *   <li>Search RAG metadata for relevant tables</li>
     *   <li>Check Redis cache for recent results</li>
     *   <li>Query Oracle warehouses via MCP if needed</li>
     *   <li>Analyze and summarize the results</li>
     * </ol>
     *
     * @param request the query request containing the natural language question
     * @return structured response with the agent's answer and metadata
     */
    @PostMapping
    public ResponseEntity<QueryResponse> submitQuery(@Valid @RequestBody QueryRequest request) {
        log.info("Query received: {}", truncate(request.getQuery(), 100));

        QueryResponse response = agentService.query(request);

        if (response.getError() != null && !response.getError().isEmpty()) {
            log.warn("Query completed with error: {}", response.getError());
        }

        return ResponseEntity.ok(response);
    }

    private static String truncate(String s, int maxLen) {
        if (s == null) return "";
        return s.length() <= maxLen ? s : s.substring(0, maxLen) + "...";
    }
}
