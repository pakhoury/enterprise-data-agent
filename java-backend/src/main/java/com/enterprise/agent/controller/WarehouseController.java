package com.enterprise.agent.controller;

import java.util.List;
import java.util.Map;

import com.enterprise.agent.model.MetadataSearchRequest;
import com.enterprise.agent.service.AgentService;
import com.enterprise.agent.service.WarehouseService;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * REST controller for warehouse and metadata operations.
 */
@RestController
@RequestMapping("/api/warehouses")
public class WarehouseController {

    private final WarehouseService warehouseService;
    private final AgentService agentService;

    public WarehouseController(WarehouseService warehouseService, AgentService agentService) {
        this.warehouseService = warehouseService;
        this.agentService = agentService;
    }

    /**
     * List all connected warehouses and their statuses.
     */
    @GetMapping
    public ResponseEntity<Map<String, Object>> listWarehouses() {
        return ResponseEntity.ok(warehouseService.getAllStatuses());
    }

    /**
     * Trigger metadata sync from all warehouses into the RAG store.
     */
    @PostMapping("/sync")
    public ResponseEntity<Map<String, Object>> syncMetadata() {
        return ResponseEntity.ok(warehouseService.syncAllMetadata());
    }

    /**
     * Search the RAG metadata store for relevant tables.
     */
    @PostMapping("/search")
    public ResponseEntity<List<Map<String, Object>>> searchMetadata(
            @Valid @RequestBody MetadataSearchRequest request) {
        return ResponseEntity.ok(agentService.searchMetadata(request));
    }
}
