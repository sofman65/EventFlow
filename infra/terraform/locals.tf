locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
    Repo        = "sofman65/EventFlow"
  }

  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  ecr_repository_names = toset([
    "api-producer",
    "validator-consumer",
    "analytics-consumer",
    "persistent-consumer-java",
    "external-payment-simulator",
  ])

  database_password = var.db_password != null ? var.db_password : random_password.db_password.result
  database_jdbc_url = "jdbc:postgresql://${aws_db_instance.eventflow.address}:5432/${var.db_name}"
  api_base_url      = "http://${aws_lb.eventflow.dns_name}"
  api_webhook_url   = "${local.api_base_url}/api/webhooks/payment-authorized"

  service_definitions = {
    api_producer = {
      service_name   = "api-producer"
      repository_key = "api-producer"
      cpu            = 512
      memory         = 1024
      port           = 8000
      attach_to_alb  = true
      desired_count  = lookup(var.service_desired_counts, "api_producer", 1)
      environment = {
        KAFKA_BOOTSTRAP_SERVERS                  = aws_msk_cluster.eventflow.bootstrap_brokers
        EVENTFLOW_RAW_TOPIC                      = var.topic_raw
        PAYMENT_PROVIDER_WEBHOOK_SECRET          = var.payment_provider_webhook_secret
        PAYMENT_PROVIDER_WEBHOOK_MAX_AGE_SECONDS = tostring(var.webhook_max_age_seconds)
      }
    }

    validator_consumer = {
      service_name   = "validator-consumer"
      repository_key = "validator-consumer"
      cpu            = 256
      memory         = 512
      port           = 8001
      attach_to_alb  = false
      desired_count  = lookup(var.service_desired_counts, "validator_consumer", 1)
      environment = {
        KAFKA_BOOTSTRAP_SERVERS       = aws_msk_cluster.eventflow.bootstrap_brokers
        KAFKA_GROUP_ID                = "validator-service"
        EVENTFLOW_RAW_TOPIC           = var.topic_raw
        EVENTFLOW_VALIDATED_TOPIC     = var.topic_validated
        EVENTFLOW_DLQ_TOPIC           = var.topic_dlq
        EVENTFLOW_EXPECTED_EVENT_TYPE = var.expected_event_type
        VALIDATOR_METRICS_PORT        = "8001"
      }
    }

    analytics_consumer = {
      service_name   = "analytics-consumer"
      repository_key = "analytics-consumer"
      cpu            = 256
      memory         = 512
      port           = 8002
      attach_to_alb  = false
      desired_count  = lookup(var.service_desired_counts, "analytics_consumer", 1)
      environment = {
        KAFKA_BOOTSTRAP_SERVERS = aws_msk_cluster.eventflow.bootstrap_brokers
        ANALYTICS_GROUP_ID      = "analytics-service"
        ANALYTICS_TOPIC         = var.topic_validated
        ANALYTICS_METRICS_PORT  = "8002"
      }
    }

    persistence_consumer_java = {
      service_name   = "persistent-consumer-java"
      repository_key = "persistent-consumer-java"
      cpu            = 512
      memory         = 1024
      port           = 8080
      attach_to_alb  = false
      desired_count  = lookup(var.service_desired_counts, "persistence_consumer_java", 1)
      environment = {
        KAFKA_BOOTSTRAP_SERVERS   = aws_msk_cluster.eventflow.bootstrap_brokers
        KAFKA_GROUP_ID            = "persistence-writer-java"
        EVENTFLOW_VALIDATED_TOPIC = var.topic_validated
        EVENTFLOW_DLQ_TOPIC       = var.topic_dlq
        EVENTFLOW_DB_URL          = local.database_jdbc_url
        EVENTFLOW_DB_USERNAME     = var.db_username
        EVENTFLOW_DB_PASSWORD     = local.database_password
        PERSISTENCE_HTTP_PORT     = "8080"
      }
    }

    external_payment_simulator = {
      service_name   = "external-payment-simulator"
      repository_key = "external-payment-simulator"
      cpu            = 256
      memory         = 512
      port           = 8003
      attach_to_alb  = false
      desired_count  = lookup(var.service_desired_counts, "external_payment_simulator", 1)
      environment = {
        EVENTFLOW_WEBHOOK_URL            = local.api_webhook_url
        EVENTFLOW_WEBHOOK_SIGNING_SECRET = var.payment_provider_webhook_secret
        SIMULATOR_AUTO_STREAM_ENABLED    = tostring(var.simulator_auto_stream_enabled)
        SIMULATOR_AUTO_STREAM_RPS        = tostring(var.simulator_auto_stream_rps)
        SIMULATOR_DUPLICATE_RATE         = tostring(var.simulator_duplicate_rate)
        SIMULATOR_CORRUPTION_RATE        = tostring(var.simulator_corruption_rate)
      }
    }
  }
}
