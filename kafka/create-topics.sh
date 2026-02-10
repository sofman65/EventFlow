#!/usr/bin/env bash
set -e

KAFKA_CONTAINER=kafka
BOOTSTRAP_SERVER=localhost:9092

echo "Creating Kafka topics..."

docker exec -i $KAFKA_CONTAINER kafka-topics \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --create \
  --if-not-exists \
  --topic events.raw.v1 \
  --partitions 3 \
  --replication-factor 1

docker exec -i $KAFKA_CONTAINER kafka-topics \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --create \
  --if-not-exists \
  --topic events.validated.v1 \
  --partitions 3 \
  --replication-factor 1

docker exec -i $KAFKA_CONTAINER kafka-topics \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --create \
  --if-not-exists \
  --topic events.enriched.v1 \
  --partitions 3 \
  --replication-factor 1

docker exec -i $KAFKA_CONTAINER kafka-topics \
  --bootstrap-server $BOOTSTRAP_SERVER \
  --create \
  --if-not-exists \
  --topic events.dlq.v1 \
  --partitions 1 \
  --replication-factor 1

echo "Kafka topics created."
