# persistent-consumer-java

Spring Boot Kafka consumer that reads validated payment events from `events.validated.v1`, persists them, and publishes failures to `events.dlq.v1`.

## What this service does

- Consumes `payment.authorized.v1` events from `events.validated.v1`.
- Validates envelope and payload DTO constraints.
- Persists events idempotently by `event_id` into the `events` table.
- Publishes processing failures to `events.dlq.v1`.

## Run locally

Prerequisites:

- Java 17+
- Maven 3.9+
- Docker (for Kafka and PostgreSQL)

Run:

```bash
cd infra
docker compose up -d kafka postgres prometheus grafana

cd ../services/persistent-consumer-java
mvn spring-boot:run
```

## Useful environment variables

- `KAFKA_BOOTSTRAP_SERVERS` (default: `localhost:9092`)
- `KAFKA_GROUP_ID` (default: `persistence-writer-java`)
- `EVENTFLOW_VALIDATED_TOPIC` (default: `events.validated.v1`)
- `EVENTFLOW_DLQ_TOPIC` (default: `events.dlq.v1`)
- `EVENTFLOW_DB_URL` (default: `jdbc:postgresql://localhost:5433/eventflow`)
- `EVENTFLOW_DB_DRIVER` (default: `org.postgresql.Driver`)
- `EVENTFLOW_DB_USERNAME` (default: `eventflow`)
- `EVENTFLOW_DB_PASSWORD` (default: `eventflow`)

## Metrics

- Actuator health: `http://localhost:8080/actuator/health`
- Prometheus endpoint: `http://localhost:8080/actuator/prometheus`
