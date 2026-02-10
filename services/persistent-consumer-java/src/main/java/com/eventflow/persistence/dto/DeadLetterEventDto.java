package com.eventflow.persistence.dto;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

import java.time.Instant;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record DeadLetterEventDto(
        String failedService,
        String errorMessage,
        String sourceTopic,
        int sourcePartition,
        long sourceOffset,
        Instant timestamp,
        Object event
) {
}
