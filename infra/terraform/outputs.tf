output "alb_dns_name" {
  description = "Public ALB DNS name."
  value       = aws_lb.eventflow.dns_name
}

output "api_base_url" {
  description = "Public API base URL."
  value       = local.api_base_url
}

output "api_webhook_url" {
  description = "Webhook endpoint used by external providers."
  value       = local.api_webhook_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name."
  value       = aws_ecs_cluster.eventflow.name
}

output "msk_bootstrap_brokers" {
  description = "MSK plaintext bootstrap brokers."
  value       = aws_msk_cluster.eventflow.bootstrap_brokers
}

output "rds_endpoint" {
  description = "RDS endpoint hostname."
  value       = aws_db_instance.eventflow.address
}

output "rds_jdbc_url" {
  description = "JDBC URL for persistence service."
  value       = local.database_jdbc_url
}

output "rds_password" {
  description = "Database password used by EventFlow services."
  value       = local.database_password
  sensitive   = true
}

output "ecr_repository_urls" {
  description = "ECR repositories by service."
  value = {
    api_producer               = aws_ecr_repository.service["api-producer"].repository_url
    validator_consumer         = aws_ecr_repository.service["validator-consumer"].repository_url
    analytics_consumer         = aws_ecr_repository.service["analytics-consumer"].repository_url
    persistence_consumer_java  = aws_ecr_repository.service["persistent-consumer-java"].repository_url
    external_payment_simulator = aws_ecr_repository.service["external-payment-simulator"].repository_url
  }
}
