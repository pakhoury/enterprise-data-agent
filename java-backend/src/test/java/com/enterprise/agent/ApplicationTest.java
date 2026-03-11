package com.enterprise.agent;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(properties = {
    "spring.data.redis.host=localhost",
    "spring.data.redis.port=6379",
    "agent.service-url=http://localhost:8001"
})
class ApplicationTest {

    @Test
    void contextLoads() {
        // Verifies Spring context starts successfully
    }
}
