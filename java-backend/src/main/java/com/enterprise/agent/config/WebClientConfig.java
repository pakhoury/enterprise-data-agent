package com.enterprise.agent.config;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

/**
 * WebClient configuration for calling the Python agent service.
 */
@Configuration
public class WebClientConfig {

    @Bean
    public WebClient agentWebClient(AgentConfig agentConfig) {
        HttpClient httpClient = HttpClient.create()
                .responseTimeout(Duration.ofSeconds(agentConfig.getTimeoutSeconds()));

        return WebClient.builder()
                .baseUrl(agentConfig.getServiceUrl())
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .codecs(configurer -> configurer.defaultCodecs().maxInMemorySize(10 * 1024 * 1024))
                .build();
    }
}
