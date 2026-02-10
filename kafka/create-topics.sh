#!/usr/bin/env bash

kafka-topics \
  --bootstrap-server localhost:9092 \
  --create --topic events.raw.v1 \
  --partitions 3 \
  --replication-factor 1

kafka-topics --bootstrap-server localhost:9092 --create --topic events.validated.v1 --partitions 3 --replication-factor 1
kafka-topics --bootstrap-server localhost:9092 --create --topic events.enriched.v1 --partitions 3 --replication-factor 1
kafka-topics --bootstrap-server localhost:9092 --create --topic events.dlq.v1 --partitions 3 --replication-factor 1
