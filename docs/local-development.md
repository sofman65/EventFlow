# Local Development Guide - EventFlow

This document describes how to run EventFlow locally with a real Kafka broker (KRaft mode), a FastAPI ingestion service, and Kafka consumers.

The goal is to mirror production semantics as closely as possible while keeping local setup simple and deterministic.

## Prerequisites

You need the following installed locally:

- Docker (with Docker Compose v2)
- Python 3.9+
- `curl` (or any HTTP client)
- Java 17+ (only if running Java consumers)

No local Kafka installation is required.

## Repository Structure (Relevant Parts)

```text
EventFlow/
├── infra/
│   └── docker-compose.yml
├── kafka/
│   └── create-topics.sh
├── services/
│   ├── api-producer/
│   └── validator-consumer/
```

Infrastructure, services, and tooling are intentionally separated.

## 1. Start Kafka (KRaft Mode)

Kafka runs only in Docker.

From the `infra/` directory:

```bash
docker compose up -d kafka
```

Verify Kafka is running:

```bash
docker ps
```

Expected output includes a running `kafka` container.

## 2. Verify Kafka Health

Run Kafka CLI tools inside the container:

```bash
docker exec -it kafka kafka-topics \
  --bootstrap-server localhost:9092 \
  --list
```

If this command runs without error, Kafka is healthy.

## 3. Create Kafka Topics

Kafka topics are created via a helper script that executes commands inside the Kafka container.

From the repository root:

```bash
chmod +x kafka/create-topics.sh
./kafka/create-topics.sh
```

Verify topics exist:

```bash
docker exec -it kafka kafka-topics \
  --bootstrap-server localhost:9092 \
  --list
```

Expected topics:

- `events.raw.v1`
- `events.validated.v1`
- `events.enriched.v1`
- `events.dlq.v1`

## 4. Start the Validator Consumer

Each service has its own isolated Python environment.

Create and activate the virtual environment:

```bash
cd services/validator-consumer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the consumer:

```bash
python app/consumer.py
```

Expected output:

```text
Validator consumer started...
```

The consumer will now block and wait for Kafka events.

## 5. Start the API Producer (FastAPI)

Open a new terminal window.

Create and activate the virtual environment:

```bash
cd services/api-producer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run FastAPI:

```bash
uvicorn app.main:app --reload
```

Expected output:

```text
Uvicorn running on http://127.0.0.1:8000
Application startup complete.
```

## 6. Send a Test Event

From any terminal:

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

Expected API response:

```json
{
  "status": "accepted",
  "event_id": "..."
}
```

Expected consumer output:

```text
Validated event <event_id> from partition <n> offset <n> -> events.validated.v1
```

## 7. End-to-End Flow (What Just Happened)

```text
HTTP request
   |
FastAPI Ingestion API
   |
Kafka Producer
   |
events.raw.v1 topic
   |
Validator Consumer Group
   |
Partition assignment
   |
Offset commit
```

This confirms the core event pipeline is operational.

## Design Notes

- Kafka is the only integration mechanism between services.
- Services do not call each other via HTTP.
- HTTP exists only at the system boundary (ingestion).
- Consumers are reactive workers, not servers.
- Local dev mirrors production semantics (partitions, consumer groups, offsets).

## Common Pitfalls

- Running `kafka-topics` on the host machine.
  Kafka CLI tools run inside the container.
- Forgetting to start FastAPI.
  Kafka and consumers do not expose HTTP ports.
- Using a single virtual environment for all services.
  Each service is isolated by design.
