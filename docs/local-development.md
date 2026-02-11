# Local Development Guide - EventFlow

This guide is the reproducible local runbook for this public repository.

It takes you from a clean state to a verified end-to-end flow:

1. API receives an event.
2. Validator consumes and validates.
3. Analytics consumes and exposes metrics.
4. Java persistence consumer writes to PostgreSQL.
5. Prometheus and Grafana scrape and visualize metrics.

## Prerequisites

Install these first:

- Docker with Compose v2 (`docker compose`)
- Python 3.9+
- Java 17+
- Maven 3.9+
- `curl`

No host Kafka installation is required.

Quick preflight checks:

```bash
docker --version
docker compose version
python3 --version
java --version
mvn -version
curl --version
```

## Repository Layout

```text
EventFlow/
├── infra/
│   └── docker-compose.yml
├── kafka/
│   └── create-topics.sh
├── observability/
│   ├── prometheus.yml
│   └── grafana/
└── services/
    ├── api-producer/
    ├── validator-consumer/
    ├── analytics-consumer/
    └── persistent-consumer-java/
```

## 0. Reset to a Clean Local State

Run from repository root:

```bash
cd infra
docker compose down -v --remove-orphans
cd ..
```

This ensures Kafka/PostgreSQL volumes are reset before reproducing the flow.

## 1. Start Infrastructure

From `infra/`:

```bash
cd infra
docker compose up -d kafka postgres prometheus grafana
docker compose ps
cd ..
```

Expected container names:

- `kafka`
- `eventflow-postgres`
- `eventflow-prometheus`
- `eventflow-grafana`

## 2. Create and Verify Topics

From repository root (`EventFlow/`):

```bash
chmod +x kafka/create-topics.sh
./kafka/create-topics.sh

docker exec kafka kafka-topics \
  --bootstrap-server localhost:9092 \
  --list | sort
```

Expected topics:

- `events.raw.v1`
- `events.validated.v1`
- `events.enriched.v1`
- `events.dlq.v1`

## 3. Start Services (One Terminal per Service)

Use separate terminals for each process.

### Terminal A: Validator Consumer

```bash
cd services/validator-consumer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app/consumer.py
```

Metrics endpoint: `http://localhost:8001/metrics`

### Terminal B: Analytics Consumer

```bash
cd services/analytics-consumer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app/consumer.py
```

Metrics endpoint: `http://localhost:8002/metrics`

### Terminal C: API Producer

```bash
cd services/api-producer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API endpoints:

- `http://localhost:8000/health`
- `http://localhost:8000/docs`

### Terminal D: Java Persistence Consumer

```bash
cd services/persistent-consumer-java
mvn test
mvn spring-boot:run
```

Metrics endpoint: `http://localhost:8080/actuator/prometheus`

## 4. Send Test Events

From a new terminal:

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "payment_id": "pay_123",
    "order_id": "ord_123",
    "amount": 49.90,
    "currency": "USD",
    "provider_auth_id": "auth_abc"
  }'
```

Expected response shape:

```json
{
  "status": "accepted",
  "event_id": "..."
}
```

Expected runtime logs:

- Validator terminal: `Validated event ... -> events.validated.v1`
- Analytics terminal: `Analytics processed event ...`
- Persistence terminal: `Stored event ...`

## 5. Verify End-to-End Output

### Verify persistence in PostgreSQL

```bash
docker exec eventflow-postgres psql -U eventflow -d eventflow -c \
"SELECT event_id, event_type, source, event_timestamp, stored_at FROM events ORDER BY stored_at DESC LIMIT 5;"
```

### Verify metrics endpoints

```bash
curl -s http://localhost:8001/metrics | grep eventflow_validator_events_validated_total
curl -s http://localhost:8002/metrics | grep eventflow_analytics_total_processed_total
curl -s http://localhost:8080/actuator/prometheus | grep eventflow_persistence_stored_total
```

### Verify observability UIs

- Prometheus: `http://localhost:9090/targets`
- Grafana: `http://localhost:3000` (default: `admin` / `admin`)
- Dashboard: `EventFlow / EventFlow Streaming Overview`

On the Prometheus Targets page, all of these should be `UP`:

- `validator-consumer`
- `analytics-consumer`
- `persistence-consumer-java`

## 6. Stop the Stack

Stop service terminals with `Ctrl+C`, then:

```bash
cd infra
docker compose down
```

For a full reset (including Kafka/PostgreSQL data):

```bash
docker compose down -v --remove-orphans
```

## Troubleshooting

- If `prometheus` shows targets as `DOWN`, confirm the corresponding service process is running on host ports `8001`, `8002`, and `8080`.
- If Kafka topic creation fails, confirm the `kafka` container is running: `cd infra && docker compose ps`.
- If Grafana panels look empty, send at least one event first, then refresh the dashboard.
- If a port is already in use, stop the conflicting process before starting EventFlow services.
- If you are on Linux and Prometheus cannot reach `host.docker.internal`, confirm Docker supports `host-gateway` and keep the `extra_hosts` entries in `infra/docker-compose.yml`.
