# external-payment-simulator

External payment-provider simulator for EventFlow.

It models provider webhook behavior by:

- exposing `/authorize` for triggering payment authorization events
- generating `payment.authorized.v1` webhook payloads
- signing webhooks with HMAC-SHA256 headers
- retrying webhook delivery with backoff
- occasionally sending duplicate webhooks
- corrupting payloads at a configurable rate to exercise failure paths
- optionally auto-streaming events without external curl loops

## Run locally

```bash
cd services/external-payment-simulator
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8003
```

## Endpoints

- `POST /authorize`
- `GET /health`
- `GET /metrics`

## Optional: Auto-Stream Mode

To make the simulator emit continuous events from its own process, enable auto-stream:

```bash
export SIMULATOR_AUTO_STREAM_ENABLED=true
export SIMULATOR_AUTO_STREAM_RPS=5
uvicorn app.main:app --reload --port 8003
```

With this enabled, the simulator continuously calls its internal authorization workflow
and sends signed webhooks to EventFlow. You can still call `POST /authorize` manually.

## Example authorize request

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

To force fault paths for demos:

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

## Environment variables

- `EVENTFLOW_WEBHOOK_URL` (default: `http://localhost:8000/api/webhooks/payment-authorized`)
- `EVENTFLOW_WEBHOOK_SIGNING_SECRET` (default: `eventflow-local-secret`)
- `SIMULATOR_WEBHOOK_TIMEOUT_SECONDS` (default: `3`)
- `SIMULATOR_MAX_ATTEMPTS` (default: `4`)
- `SIMULATOR_BACKOFF_BASE_SECONDS` (default: `0.5`)
- `SIMULATOR_BACKOFF_MAX_SECONDS` (default: `5`)
- `SIMULATOR_BACKOFF_JITTER_SECONDS` (default: `0.25`)
- `SIMULATOR_DUPLICATE_RATE` (default: `0.05`)
- `SIMULATOR_CORRUPTION_RATE` (default: `0.01`)
- `SIMULATOR_AUTO_STREAM_ENABLED` (default: `false`)
- `SIMULATOR_AUTO_STREAM_RPS` (default: `5`)
- `SIMULATOR_AUTO_STREAM_AMOUNT` (default: `49.90`)
- `SIMULATOR_AUTO_STREAM_CURRENCY` (default: `USD`)
- `SIMULATOR_AUTO_STREAM_PAYMENT_PREFIX` (default: `pay_stream`)
- `SIMULATOR_AUTO_STREAM_ORDER_PREFIX` (default: `ord_stream`)
