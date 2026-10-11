package br.pucminas.ti6.waste.client;

import br.pucminas.ti6.waste.dto.Prediction;
import br.pucminas.ti6.waste.dto.WorkerBatchResponse;
import br.pucminas.ti6.waste.grpc.BatchInferenceRequest;
import br.pucminas.ti6.waste.grpc.BatchInferenceResponse;
import br.pucminas.ti6.waste.grpc.HealthRequest;
import br.pucminas.ti6.waste.grpc.HealthResponse;
import br.pucminas.ti6.waste.grpc.ImagePayload;
import br.pucminas.ti6.waste.grpc.WasteInferenceServiceGrpc;
import com.google.protobuf.ByteString;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

@Component
public class WorkerGrpcClient {
    private static final int MAX_MESSAGE_SIZE = 100 * 1024 * 1024; // 100 MB
    private final ConcurrentHashMap<String, ManagedChannel> channels = new ConcurrentHashMap<>();

    public WorkerBatchResponse classify(String grpcTarget, List<MultipartFile> files) {
        ManagedChannel channel = getChannel(grpcTarget);
        WasteInferenceServiceGrpc.WasteInferenceServiceBlockingStub stub =
                WasteInferenceServiceGrpc.newBlockingStub(channel)
                        .withMaxInboundMessageSize(MAX_MESSAGE_SIZE)
                        .withMaxOutboundMessageSize(MAX_MESSAGE_SIZE);

        BatchInferenceRequest.Builder requestBuilder = BatchInferenceRequest.newBuilder();

        for (MultipartFile file : files) {
            try {
                String filename = file.getOriginalFilename() == null ? "image.jpg" : file.getOriginalFilename();
                requestBuilder.addImages(
                        ImagePayload.newBuilder()
                                .setFilename(filename)
                                .setImageData(ByteString.copyFrom(file.getBytes()))
                                .build()
                );
            } catch (IOException e) {
                throw new IllegalArgumentException("Não foi possível ler o arquivo " + file.getOriginalFilename(), e);
            }
        }

        BatchInferenceResponse response = stub.predictBatch(requestBuilder.build());

        List<Prediction> predictions = response.getPredictionsList().stream()
                .map(item -> new Prediction(
                        item.getFilename(),
                        item.getStatus(),
                        item.getLabel().isBlank() ? null : item.getLabel(),
                        "OK".equals(item.getStatus()) ? (double) item.getConfidence() : null
                ))
                .toList();

        return new WorkerBatchResponse(
                response.getWorkerId(),
                response.getModelLoaded(),
                response.getElapsedMs(),
                predictions
        );
    }

    public String health(String grpcTarget) {
        try {
            ManagedChannel channel = getChannel(grpcTarget);
            WasteInferenceServiceGrpc.WasteInferenceServiceBlockingStub stub =
                    WasteInferenceServiceGrpc.newBlockingStub(channel)
                            .withDeadlineAfter(3, TimeUnit.SECONDS);

            HealthResponse response = stub.checkHealth(HealthRequest.getDefaultInstance());
            return response.getStatus();
        } catch (Exception e) {
            return "UNAVAILABLE";
        }
    }

    private ManagedChannel getChannel(String target) {
        return channels.computeIfAbsent(target, t -> ManagedChannelBuilder.forTarget(t)
                .usePlaintext()
                .maxInboundMessageSize(MAX_MESSAGE_SIZE)
                .build());
    }

    @PreDestroy
    public void shutdown() {
        for (ManagedChannel channel : channels.values()) {
            try {
                channel.shutdown().awaitTermination(2, TimeUnit.SECONDS);
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            }
        }
    }
}

