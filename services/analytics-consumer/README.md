# analytics-consumer

Real-time metrics consumer for EventFlow.

It consumes `events.validated.v1` and publishes Prometheus metrics that prove fan-out and extensibility without changing upstream services.

## Exposed metrics

- `eventflow_analytics_total_processed_total`
- `eventflow_analytics_by_event_type_total{event_type=...}`
- `eventflow_analytics_by_partition_total{partition=...}`
- `eventflow_analytics_processing_errors_total`
- `eventflow_analytics_event_age_ms`
- `eventflow_analytics_processing_latency_seconds`

## Run locally

```bash
cd services/analytics-consumer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app/consumer.py
```

Metrics endpoint:

- `http://localhost:8002/metrics`
