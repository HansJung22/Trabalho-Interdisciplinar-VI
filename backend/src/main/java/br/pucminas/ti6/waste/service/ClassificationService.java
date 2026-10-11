package br.pucminas.ti6.waste.service;

import br.pucminas.ti6.waste.client.WorkerClient;
import br.pucminas.ti6.waste.client.WorkerGrpcClient;
import br.pucminas.ti6.waste.config.WorkerProperties;
import br.pucminas.ti6.waste.dto.ClassificationResponse;
import br.pucminas.ti6.waste.dto.ExperimentResponse;
import br.pucminas.ti6.waste.dto.ProtocolComparisonResponse;
import br.pucminas.ti6.waste.dto.WorkerBatchResponse;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

@Service
public class ClassificationService {
    private final WorkerClient workerClient;
    private final WorkerGrpcClient workerGrpcClient;
    private final WorkerProperties workerProperties;

    public ClassificationService(
            WorkerClient workerClient,
            WorkerGrpcClient workerGrpcClient,
            WorkerProperties workerProperties
    ) {
        this.workerClient = workerClient;
        this.workerGrpcClient = workerGrpcClient;
        this.workerProperties = workerProperties;
    }

    public ClassificationResponse singleWorker(List<MultipartFile> files) {
        return singleWorker(files, "rest");
    }

    public ClassificationResponse singleWorker(List<MultipartFile> files, String protocol) {
        long start = System.nanoTime();
        WorkerBatchResponse result;

        if ("grpc".equalsIgnoreCase(protocol)) {
            if (workerProperties.grpcUrls().isEmpty()) {
                throw new IllegalStateException("Nenhum worker gRPC configurado");
            }
            result = workerGrpcClient.classify(workerProperties.grpcUrls().get(0), files);
            return buildResponse("single-worker-grpc", files.size(), List.of(result), start);
        } else {
            if (workerProperties.urls().isEmpty()) {
                throw new IllegalStateException("Nenhum worker REST configurado");
            }
            result = workerClient.classify(workerProperties.urls().get(0), files);
            return buildResponse("single-worker-rest", files.size(), List.of(result), start);
        }
    }

    public ClassificationResponse distributed(List<MultipartFile> files) {
        return distributed(files, "rest");
    }

    public ClassificationResponse distributed(List<MultipartFile> files, String protocol) {
        long start = System.nanoTime();

        if ("grpc".equalsIgnoreCase(protocol)) {
            if (workerProperties.grpcUrls().isEmpty()) {
                throw new IllegalStateException("Nenhum worker gRPC configurado");
            }
            List<String> endpoints = workerProperties.grpcUrls();
            List<List<MultipartFile>> partitions = partition(files, endpoints.size());
            List<CompletableFuture<WorkerBatchResponse>> futures = new ArrayList<>();

            for (int i = 0; i < partitions.size(); i++) {
                if (partitions.get(i).isEmpty()) {
                    continue;
                }
                String target = endpoints.get(i);
                List<MultipartFile> batch = partitions.get(i);
                futures.add(CompletableFuture.supplyAsync(() -> workerGrpcClient.classify(target, batch)));
            }

            List<WorkerBatchResponse> results = futures.stream().map(CompletableFuture::join).toList();
            return buildResponse("distributed-grpc", files.size(), results, start);
        } else {
            if (workerProperties.urls().isEmpty()) {
                throw new IllegalStateException("Nenhum worker REST configurado");
            }
            List<String> endpoints = workerProperties.urls();
            List<List<MultipartFile>> partitions = partition(files, endpoints.size());
            List<CompletableFuture<WorkerBatchResponse>> futures = new ArrayList<>();

            for (int i = 0; i < partitions.size(); i++) {
                if (partitions.get(i).isEmpty()) {
                    continue;
                }
                String workerUrl = endpoints.get(i);
                List<MultipartFile> batch = partitions.get(i);
                futures.add(CompletableFuture.supplyAsync(() -> workerClient.classify(workerUrl, batch)));
            }

            List<WorkerBatchResponse> results = futures.stream().map(CompletableFuture::join).toList();
            return buildResponse("distributed-rest", files.size(), results, start);
        }
    }

    public ExperimentResponse compare(List<MultipartFile> files) {
        return compare(files, "rest");
    }

    public ExperimentResponse compare(List<MultipartFile> files, String protocol) {
        ClassificationResponse baseline = singleWorker(files, protocol);
        ClassificationResponse distributed = distributed(files, protocol);
        double speedup = distributed.elapsedMs() == 0 ? 0 : baseline.elapsedMs() / distributed.elapsedMs();
        return new ExperimentResponse(baseline, distributed, speedup);
    }

    public ProtocolComparisonResponse compareProtocols(List<MultipartFile> files) {
        ClassificationResponse restResult = distributed(files, "rest");
        ClassificationResponse grpcResult = distributed(files, "grpc");
        double speedup = grpcResult.elapsedMs() == 0 ? 0 : restResult.elapsedMs() / grpcResult.elapsedMs();
        return new ProtocolComparisonResponse(restResult, grpcResult, speedup);
    }

    private ClassificationResponse buildResponse(
            String strategy,
            int imageCount,
            List<WorkerBatchResponse> results,
            long start
    ) {
        double elapsedMs = (System.nanoTime() - start) / 1_000_000.0;
        double throughput = elapsedMs == 0 ? 0 : imageCount / (elapsedMs / 1000.0);
        return new ClassificationResponse(strategy, imageCount, results.size(), elapsedMs, throughput, results);
    }

    private List<List<MultipartFile>> partition(List<MultipartFile> files, int workers) {
        List<List<MultipartFile>> partitions = new ArrayList<>();
        for (int i = 0; i < workers; i++) {
            partitions.add(new ArrayList<>());
        }
        for (int i = 0; i < files.size(); i++) {
            partitions.get(i % workers).add(files.get(i));
        }
        return partitions;
    }
}
