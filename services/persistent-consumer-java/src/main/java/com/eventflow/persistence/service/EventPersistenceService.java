package com.eventflow.persistence.service;

import com.eventflow.persistence.dto.PaymentAuthorizedEventDto;
import com.eventflow.persistence.entity.PersistedEvent;
import com.eventflow.persistence.repository.PersistedEventRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;

@Service
public class EventPersistenceService {

    private final PersistedEventRepository repository;
    private final ObjectMapper objectMapper;

    public EventPersistenceService(PersistedEventRepository repository, ObjectMapper objectMapper) {
        this.repository = repository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public boolean store(PaymentAuthorizedEventDto event) {
        if (repository.existsById(event.eventId())) {
            return false;
        }

        final String payloadJson;
        try {
            payloadJson = objectMapper.writeValueAsString(event.payload());
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("unable to serialize event payload", ex);
        }

        PersistedEvent persistedEvent = new PersistedEvent(
                event.eventId(),
                event.eventType(),
                event.source(),
                event.timestamp(),
                payloadJson,
                Instant.now()
        );

        try {
            repository.saveAndFlush(persistedEvent);
            return true;
        } catch (DataIntegrityViolationException duplicate) {
            return false;
        }
    }
}
