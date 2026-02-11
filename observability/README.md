# Observability

EventFlow local observability stack:

- Prometheus (`http://localhost:9090`)
- Grafana (`http://localhost:3000`, default credentials: `admin` / `admin`)

## Start stack

```bash
cd infra
docker compose up -d prometheus grafana
```

## Scraped targets

- Validator consumer: `http://host.docker.internal:8001/metrics`
- Analytics consumer: `http://host.docker.internal:8002/metrics`
- Java persistence consumer: `http://host.docker.internal:8080/actuator/prometheus`
- External payment simulator: `http://host.docker.internal:8003/metrics`

## Dashboard

Grafana auto-provisions:

- `EventFlow / EventFlow Streaming Overview`
