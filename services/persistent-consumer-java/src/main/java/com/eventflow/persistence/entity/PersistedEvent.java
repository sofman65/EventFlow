package com.eventflow.persistence.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.Table;

import java.time.Instant;

@Entity
@Table(name = "events")
public class PersistedEvent {

    @Id
    @Column(name = "event_id", nullable = false, updatable = false, length = 128)
    private String eventId;

    @Column(name = "event_type", nullable = false, length = 128)
    private String eventType;

    @Column(name = "source", nullable = false, length = 128)
    private String source;

    @Column(name = "event_timestamp", nullable = false)
    private Instant eventTimestamp;

    @Lob
    @Column(name = "payload", nullable = false)
    private String payload;

    @Column(name = "stored_at", nullable = false)
    private Instant storedAt;

    protected PersistedEvent() {
    }

    public PersistedEvent(
            String eventId,
            String eventType,
            String source,
            Instant eventTimestamp,
            String payload,
            Instant storedAt
    ) {
        this.eventId = eventId;
        this.eventType = eventType;
        this.source = source;
        this.eventTimestamp = eventTimestamp;
        this.payload = payload;
        this.storedAt = storedAt;
    }

    public String getEventId() {
        return eventId;
    }

    public String getEventType() {
        return eventType;
    }

    public String getSource() {
        return source;
    }

    public Instant getEventTimestamp() {
        return eventTimestamp;
    }

    public String getPayload() {
        return payload;
    }

    public Instant getStoredAt() {
        return storedAt;
    }
}
