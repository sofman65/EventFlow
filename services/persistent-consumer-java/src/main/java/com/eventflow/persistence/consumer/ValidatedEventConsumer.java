package com.eventflow.persistence.consumer;

import com.eventflow.persistence.dto.DeadLetterEventDto;
import com.eventflow.persistence.dto.PaymentAuthorizedEventDto;
import com.eventflow.persistence.service.EventPersistenceService;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import org.apache.kafka.clients.producer.RecordMetadata;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.Acknowledgment;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutionException;

@Component
public class ValidatedEventConsumer {

    private static final Logger log = LoggerFactory.getLogger(ValidatedEventConsumer.class);
    private static final String EXPECTED_EVENT_TYPE = "payment.authorized.v1";

    private final ObjectMapper objectMapper;
    private final Validator validator;
    private final EventPersistenceService eventPersistenceService;
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final MeterRegistry meterRegistry;
    private final Counter consumedCounter;
    private final Counter storedCounter;
    private final Counter duplicateCounter;
    private final Counter dlqPublishedCounter;
    private final Counter processingErrorCounter;
    private final Timer processingTimer;
    private final DistributionSummary eventAgeMsSummary;

    @Value("${eventflow.kafka.dlq-topic}")
    private String dlqTopic;

    @Value("${eventflow.service-name}")
    private String serviceName;

    public ValidatedEventConsumer(
            ObjectMapper objectMapper,
            Validator validator,
            EventPersistenceService eventPersistenceService,
            KafkaTemplate<String, String> kafkaTemplate,
            MeterRegistry meterRegistry
    ) {
        this.objectMapper = objectMapper;
        this.validator = validator;
        this.eventPersistenceService = eventPersistenceService;
        this.kafkaTemplate = kafkaTemplate;
        this.meterRegistry = meterRegistry;
        this.consumedCounter = meterRegistry.counter("eventflow.persistence.consumed.total");
        this.storedCounter = meterRegistry.counter("eventflow.persistence.stored.total");
        this.duplicateCounter = meterRegistry.counter("eventflow.persistence.duplicates.total");
        this.dlqPublishedCounter = meterRegistry.counter("eventflow.persistence.dlq.published.total");
        this.processingErrorCounter = meterRegistry.counter("eventflow.persistence.processing.errors.total");
        this.processingTimer = Timer
                .builder("eventflow.persistence.processing.latency")
                .description("End-to-end persistence consumer message processing latency.")
                .publishPercentileHistogram()
                .register(meterRegistry);
        this.eventAgeMsSummary = DistributionSummary
                .builder("eventflow.persistence.event.age.ms")
                .description("Age of validated events when processed by persistence consumer.")
                .baseUnit("milliseconds")
                .publishPercentileHistogram()
                .register(meterRegistry);
    }

    @KafkaListener(topics = "${eventflow.kafka.validated-topic}")
    public void onMessage(
            String message,
            @Header(KafkaHeaders.RECEIVED_TOPIC) String sourceTopic,
            @Header(KafkaHeaders.RECEIVED_PARTITION) int sourcePartition,
            @Header(KafkaHeaders.OFFSET) long sourceOffset,
            Acknowledgment acknowledgment
    ) {
        Timer.Sample sample = Timer.start(meterRegistry);
        consumedCounter.increment();
        meterRegistry
                .counter("eventflow.persistence.by.partition.total", "partition", String.valueOf(sourcePartition))
                .increment();

        try {
            PaymentAuthorizedEventDto event = objectMapper.readValue(message, PaymentAuthorizedEventDto.class);
            validateEvent(event);
            meterRegistry
                    .counter(
                            "eventflow.persistence.by.event.type.total",
                            "event_type",
                            safeTagValue(event.eventType())
                    )
                    .increment();
            observeEventAge(event.timestamp());

            boolean stored = eventPersistenceService.store(event);
            acknowledgment.acknowledge();

            if (stored) {
                storedCounter.increment();
                log.info(
                        "Stored event {} from partition {} offset {}",
                        event.eventId(),
                        sourcePartition,
                        sourceOffset
                );
            } else {
                duplicateCounter.increment();
                log.info(
                        "Skipped duplicate event {} from partition {} offset {}",
                        event.eventId(),
                        sourcePartition,
                        sourceOffset
                );
            }
        } catch (Exception processingError) {
            processingErrorCounter.increment();
            boolean publishedToDlq = publishToDlq(
                    sourceTopic,
                    sourcePartition,
                    sourceOffset,
                    message,
                    processingError
            );

            if (publishedToDlq) {
                dlqPublishedCounter.increment();
                acknowledgment.acknowledge();
                log.warn(
                        "Sent failed message from partition {} offset {} to {}: {}",
                        sourcePartition,
                        sourceOffset,
                        dlqTopic,
                        processingError.getMessage()
                );
            } else {
                log.error(
                        "Unable to publish failed message from partition {} offset {} to {}. "
                                + "Offset left uncommitted for retry.",
                        sourcePartition,
                        sourceOffset,
                        dlqTopic
                );
            }
        } finally {
            sample.stop(processingTimer);
        }
    }

    private void validateEvent(PaymentAuthorizedEventDto event) {
        Set<ConstraintViolation<PaymentAuthorizedEventDto>> violations = validator.validate(event);
        if (!violations.isEmpty()) {
            ConstraintViolation<PaymentAuthorizedEventDto> violation = violations.iterator().next();
            throw new IllegalArgumentException(
                    "invalid event payload at " + violation.getPropertyPath() + ": " + violation.getMessage()
            );
        }

        if (!EXPECTED_EVENT_TYPE.equals(event.eventType())) {
            throw new IllegalArgumentException("event_type must be " + EXPECTED_EVENT_TYPE);
        }
    }

    private boolean publishToDlq(
            String sourceTopic,
            int sourcePartition,
            long sourceOffset,
            String rawMessage,
            Exception processingError
    ) {
        try {
            Object originalEvent = readLenientJson(rawMessage);
            DeadLetterEventDto deadLetterEvent = new DeadLetterEventDto(
                    serviceName,
                    processingError.getMessage(),
                    sourceTopic,
                    sourcePartition,
                    sourceOffset,
                    Instant.now(),
                    originalEvent
            );

            String key = extractEventId(originalEvent);
            String payload = objectMapper.writeValueAsString(deadLetterEvent);

            RecordMetadata metadata = kafkaTemplate
                    .send(dlqTopic, key, payload)
                    .get()
                    .getRecordMetadata();

            log.info(
                    "Published DLQ record to {} partition {} offset {}",
                    metadata.topic(),
                    metadata.partition(),
                    metadata.offset()
            );
            return true;
        } catch (InterruptedException interruptedException) {
            Thread.currentThread().interrupt();
            log.error("Interrupted while publishing DLQ record", interruptedException);
            return false;
        } catch (ExecutionException | JsonProcessingException publishError) {
            log.error("Failed to publish DLQ record", publishError);
            return false;
        }
    }

    private Object readLenientJson(String rawMessage) {
        try {
            return objectMapper.readValue(rawMessage, Object.class);
        } catch (JsonProcessingException parseError) {
            return rawMessage;
        }
    }

    private String extractEventId(Object eventObject) {
        if (eventObject instanceof Map<?, ?> map) {
            Object eventId = map.get("event_id");
            if (eventId instanceof String eventIdString && !eventIdString.isBlank()) {
                return eventIdString;
            }
        }
        return "unknown-event-id";
    }

    private String safeTagValue(String raw) {
        if (raw == null || raw.isBlank()) {
            return "unknown";
        }
        return raw;
    }

    private void observeEventAge(Instant eventTimestamp) {
        if (eventTimestamp == null) {
            return;
        }
        long ageMs = Instant.now().toEpochMilli() - eventTimestamp.toEpochMilli();
        if (ageMs >= 0) {
            eventAgeMsSummary.record(ageMs);
        }
    }
}
