package com.enterprise.agent;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Enterprise Data Agent — Java Spring Boot backend.
 *
 * <p>Main entry point. Provides REST API endpoints for:
 * <ul>
 *   <li>Natural language queries routed to the Python LangGraph agent</li>
 *   <li>Warehouse management (list, status)</li>
 *   <li>Cache management (stats, invalidation)</li>
 *   <li>Metadata operations (sync, search)</li>
 *   <li>Health checks</li>
 * </ul>
 */
@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
