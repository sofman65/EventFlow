# Local Development Guide - EventFlow

This guide is the reproducible local runbook for this public repository.

It takes you from a clean state to a verified end-to-end flow:

1. External simulator receives an `/authorize` request.
2. Simulator sends a signed webhook to EventFlow.
3. Validator consumes and validates.
4. Analytics consumes and exposes metrics.
5. Java persistence consumer writes to PostgreSQL.
6. Prometheus and Grafana scrape and visualize metrics.

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
    ├── persistent-consumer-java/
    └── external-payment-simulator/
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
export PAYMENT_PROVIDER_WEBHOOK_SECRET=eventflow-local-secret
uvicorn app.main:app --reload
```

API endpoints:

- `http://localhost:8000/health`
- `http://localhost:8000/docs`
- `http://localhost:8000/api/webhooks/payment-authorized`

### Terminal D: Java Persistence Consumer

```bash
cd services/persistent-consumer-java
mvn test
mvn spring-boot:run
```

Metrics endpoint: `http://localhost:8080/actuator/prometheus`

### Terminal E: External Payment Simulator

```bash
cd services/external-payment-simulator
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
export EVENTFLOW_WEBHOOK_SIGNING_SECRET=eventflow-local-secret
export SIMULATOR_AUTO_STREAM_ENABLED=true
export SIMULATOR_AUTO_STREAM_RPS=5
uvicorn app.main:app --reload --port 8003
```

Simulator endpoints:

- `http://localhost:8003/health`
- `http://localhost:8003/docs`
- `http://localhost:8003/metrics`

## 4. Send Test Events Through the Simulator

From a new terminal:

```bash
curl -X POST http://localhost:8003/authorize \
  -H "Content-Type: application/json" \
  -d '{
    "payment_id": "pay_123",
    "order_id": "ord_123",
    "amount": 49.90,
    "currency": "USD"
  }'
```

Expected response shape:

```json
{
  "status": "accepted",
  "event_id": "...",
  "primary_delivery": {
    "ok": true
  }
}
```

Expected runtime logs:

- API producer terminal: `Produced event to events.raw.v1 ...`
- Validator terminal: `Validated event ... -> events.validated.v1`
- Analytics terminal: `Analytics processed event ...`
- Persistence terminal: `Stored event ...`

Force duplicate and corrupted-event behavior:

```bash
curl -X POST http://localhost:8003/authorize \
  -H "Content-Type: application/json" \
  -d '{
    "payment_id": "pay_fault",
    "order_id": "ord_fault",
    "amount": 49.90,
    "currency": "USD",
    "force_corruption": true,
    "force_duplicate": true
  }'
```

If auto-stream mode is enabled in Terminal E, this manual curl step is optional.
You should see continuous traffic in Grafana without running a separate shell loop.

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
curl -s http://localhost:8003/metrics | grep eventflow_simulator_webhook_attempts_total
```

### Verify observability UIs

- Prometheus: `http://localhost:9090/targets`
- Grafana: `http://localhost:3000` (default: `admin` / `admin`)
- Dashboard: `EventFlow / EventFlow Streaming Overview`

On the Prometheus Targets page, all of these should be `UP`:

- `validator-consumer`
- `analytics-consumer`
- `persistence-consumer-java`
- `external-payment-simulator`

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

- If `prometheus` shows targets as `DOWN`, confirm the corresponding service process is running on host ports `8001`, `8002`, `8003`, and `8080`.
- If Kafka topic creation fails, confirm the `kafka` container is running: `cd infra && docker compose ps`.
- If Grafana panels look empty, send at least one event first, then refresh the dashboard.
- If a port is already in use, stop the conflicting process before starting EventFlow services.
- If you are on Linux and Prometheus cannot reach `host.docker.internal`, confirm Docker supports `host-gateway` and keep the `extra_hosts` entries in `infra/docker-compose.yml`.
- If simulator calls fail with `401` from EventFlow, ensure `PAYMENT_PROVIDER_WEBHOOK_SECRET` and `EVENTFLOW_WEBHOOK_SIGNING_SECRET` match.
