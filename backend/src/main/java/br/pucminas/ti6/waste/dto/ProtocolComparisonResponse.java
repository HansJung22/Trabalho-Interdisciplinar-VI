package br.pucminas.ti6.waste.dto;

public record ProtocolComparisonResponse(
        ClassificationResponse restExecution,
        ClassificationResponse grpcExecution,
        double speedup
) {}

