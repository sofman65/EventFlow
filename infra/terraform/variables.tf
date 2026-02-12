variable "aws_region" {
  description = "AWS region for deployment."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name prefix used in resource naming."
  type        = string
  default     = "eventflow"
}

variable "environment" {
  description = "Environment name (for example: dev, stage, prod)."
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Two public subnet CIDRs."
  type        = list(string)
  default     = ["10.42.0.0/24", "10.42.1.0/24"]
}

variable "private_subnet_cidrs" {
  description = "Two private subnet CIDRs for data services."
  type        = list(string)
  default     = ["10.42.10.0/24", "10.42.11.0/24"]
}

variable "image_tags" {
  description = "Image tags for each service."
  type        = map(string)
  default = {
    api_producer               = "latest"
    validator_consumer         = "latest"
    analytics_consumer         = "latest"
    persistence_consumer_java  = "latest"
    external_payment_simulator = "latest"
  }
}

variable "service_desired_counts" {
  description = "Desired ECS task counts for each service."
  type        = map(number)
  default = {
    api_producer               = 1
    validator_consumer         = 1
    analytics_consumer         = 1
    persistence_consumer_java  = 1
    external_payment_simulator = 1
  }
}

variable "topic_raw" {
  description = "Kafka raw topic name."
  type        = string
  default     = "events.raw.v1"
}

variable "topic_validated" {
  description = "Kafka validated topic name."
  type        = string
  default     = "events.validated.v1"
}

variable "topic_dlq" {
  description = "Kafka dead-letter topic name."
  type        = string
  default     = "events.dlq.v1"
}

variable "expected_event_type" {
  description = "Validator expected event type."
  type        = string
  default     = "payment.authorized.v1"
}

variable "webhook_max_age_seconds" {
  description = "Max accepted webhook timestamp skew."
  type        = number
  default     = 300
}

variable "payment_provider_webhook_secret" {
  description = "Shared HMAC secret between simulator and api-producer."
  type        = string
  default     = "eventflow-cloud-secret-change-me"
  sensitive   = true
}

variable "db_name" {
  description = "PostgreSQL database name."
  type        = string
  default     = "eventflow"
}

variable "db_username" {
  description = "PostgreSQL username."
  type        = string
  default     = "eventflow"
}

variable "db_password" {
  description = "Optional PostgreSQL password override. If null, Terraform generates one."
  type        = string
  default     = null
  sensitive   = true
}

variable "db_allocated_storage" {
  description = "RDS allocated storage (GiB)."
  type        = number
  default     = 20
}

variable "db_instance_class" {
  description = "RDS instance class."
  type        = string
  default     = "db.t4g.micro"
}

variable "msk_broker_instance_type" {
  description = "MSK broker instance type."
  type        = string
  default     = "kafka.t3.small"
}

variable "msk_broker_ebs_volume_size" {
  description = "MSK broker EBS volume size (GiB)."
  type        = number
  default     = 100
}

variable "msk_kafka_version" {
  description = "Apache Kafka version for MSK."
  type        = string
  default     = "3.6.0"
}

variable "log_retention_days" {
  description = "CloudWatch log retention period."
  type        = number
  default     = 14
}

variable "simulator_auto_stream_enabled" {
  description = "Enable simulator continuous auto-stream mode."
  type        = bool
  default     = true
}

variable "simulator_auto_stream_rps" {
  description = "Simulator events-per-second when auto-stream is enabled."
  type        = number
  default     = 3
}

variable "simulator_duplicate_rate" {
  description = "Simulator duplicate injection rate."
  type        = number
  default     = 0.05
}

variable "simulator_corruption_rate" {
  description = "Simulator payload corruption rate."
  type        = number
  default     = 0.01
}
