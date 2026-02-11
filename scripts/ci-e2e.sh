#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/.ci-logs"
mkdir -p "${LOG_DIR}"

declare -a SERVICE_PIDS=()

dump_logs() {
  shopt -s nullglob
  for log_file in "${LOG_DIR}"/*.log; do
    echo "===== ${log_file} ====="
    tail -n 200 "${log_file}" || true
  done
  shopt -u nullglob
}

cleanup() {
  set +e
  for pid in "${SERVICE_PIDS[@]:-}"; do
    kill "${pid}" >/dev/null 2>&1 || true
  done
  sleep 1
  (
    cd "${ROOT_DIR}/infra" &&
      docker compose down -v --remove-orphans
  ) >/dev/null 2>&1 || true
}

on_exit() {
  exit_code=$?
  if [[ "${exit_code}" -ne 0 ]]; then
    echo "E2E check failed. Dumping service logs."
    dump_logs
  fi
  cleanup
  exit "${exit_code}"
}

trap on_exit EXIT

wait_for_http() {
  local name="$1"
  local url="$2"
  local attempts="${3:-120}"

  echo "Waiting for ${name} (${url})"
  for _ in $(seq 1 "${attempts}"); do
    if curl -fsS "${url}" >/dev/null; then
      echo "${name} is ready"
      return 0
    fi
    sleep 1
  done

  echo "Timed out waiting for ${name}"
  return 1
}

start_service() {
  local name="$1"
  local command="$2"
  local log_file="${LOG_DIR}/${name}.log"

  bash -lc "${command}" >"${log_file}" 2>&1 &
  local pid=$!
  SERVICE_PIDS+=("${pid}")
  echo "Started ${name} (pid=${pid})"
}

cd "${ROOT_DIR}/infra"
docker compose up -d kafka postgres prometheus grafana
docker compose ps

cd "${ROOT_DIR}"
chmod +x kafka/create-topics.sh
./kafka/create-topics.sh

python3 -m pip install --upgrade pip
python3 -m pip install -r services/api-producer/requirements.txt
python3 -m pip install -r services/validator-consumer/requirements.txt
python3 -m pip install -r services/external-payment-simulator/requirements.txt

start_service \
  "validator-consumer" \
  "cd '${ROOT_DIR}/services/validator-consumer' && python3 app/consumer.py"

start_service \
  "api-producer" \
  "cd '${ROOT_DIR}/services/api-producer' && PAYMENT_PROVIDER_WEBHOOK_SECRET=eventflow-local-secret uvicorn app.main:app --host 127.0.0.1 --port 8000"

start_service \
  "persistence-consumer-java" \
  "cd '${ROOT_DIR}/services/persistent-consumer-java' && mvn -B -ntp spring-boot:run"

start_service \
  "external-payment-simulator" \
  "cd '${ROOT_DIR}/services/external-payment-simulator' && EVENTFLOW_WEBHOOK_SIGNING_SECRET=eventflow-local-secret SIMULATOR_DUPLICATE_RATE=0 SIMULATOR_CORRUPTION_RATE=0 uvicorn app.main:app --host 127.0.0.1 --port 8003"

wait_for_http "API producer" "http://127.0.0.1:8000/health"
wait_for_http "Validator metrics" "http://127.0.0.1:8001/metrics"
wait_for_http "Persistence consumer" "http://127.0.0.1:8080/actuator/health" 180
wait_for_http "External simulator" "http://127.0.0.1:8003/health"

suffix="$(date +%s%N)"
authorize_response="$(
  curl -fsS -X POST "http://127.0.0.1:8003/authorize" \
    -H "Content-Type: application/json" \
    -d "{\"payment_id\":\"pay_ci_${suffix}\",\"order_id\":\"ord_ci_${suffix}\",\"amount\":49.90,\"currency\":\"USD\"}"
)"

event_id="$(
  printf "%s" "${authorize_response}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["event_id"])'
)"

if [[ -z "${event_id}" ]]; then
  echo "Could not parse event_id from simulator response: ${authorize_response}"
  exit 1
fi

echo "Waiting for persisted event_id=${event_id}"
found=0
for _ in $(seq 1 60); do
  raw_count="$(
    docker exec eventflow-postgres psql -U eventflow -d eventflow -tAc \
      "SELECT count(*) FROM events WHERE event_id='${event_id}';" 2>/dev/null || true
  )"
  count="$(echo "${raw_count}" | tr -d '[:space:]')"
  if [[ "${count}" =~ ^[1-9][0-9]*$ ]]; then
    found=1
    break
  fi
  sleep 1
done

if [[ "${found}" -ne 1 ]]; then
  echo "Event was not persisted to PostgreSQL within timeout."
  exit 1
fi

echo "E2E flow succeeded."
