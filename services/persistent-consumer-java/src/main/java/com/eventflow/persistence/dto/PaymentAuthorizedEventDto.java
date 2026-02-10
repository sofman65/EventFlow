package com.eventflow.persistence.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.time.Instant;

@JsonIgnoreProperties(ignoreUnknown = true)
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record PaymentAuthorizedEventDto(
        @NotBlank String eventId,
        @NotBlank String eventType,
        @NotBlank String source,
        @NotNull Instant timestamp,
        @NotNull @Valid PaymentAuthorizedPayloadDto payload
) {
}
