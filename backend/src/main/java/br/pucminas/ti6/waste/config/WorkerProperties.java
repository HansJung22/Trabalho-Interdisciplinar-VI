package br.pucminas.ti6.waste.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;

import java.util.Arrays;
import java.util.List;

@Configuration
public class WorkerProperties {
    private final List<String> urls;
    private final List<String> grpcUrls;

    public WorkerProperties(
            @Value("${waste.workers:http://localhost:8001,http://localhost:8002}") String workers,
            @Value("${waste.grpc-workers:localhost:50051,localhost:50052}") String grpcWorkers
    ) {
        this.urls = parseList(workers);
        this.grpcUrls = parseList(grpcWorkers);
    }

    public List<String> urls() {
        return urls;
    }

    public List<String> grpcUrls() {
        return grpcUrls;
    }

    private static List<String> parseList(String raw) {
        if (raw == null || raw.isBlank()) {
            return List.of();
        }
        return Arrays.stream(raw.split(","))
                .map(String::trim)
                .filter(value -> !value.isBlank())
                .toList();
    }
}
