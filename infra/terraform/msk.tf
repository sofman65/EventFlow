resource "aws_cloudwatch_log_group" "msk" {
  name              = "/aws/msk/${local.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

resource "aws_msk_cluster" "eventflow" {
  cluster_name           = "${local.name_prefix}-msk"
  kafka_version          = var.msk_kafka_version
  number_of_broker_nodes = 2

  broker_node_group_info {
    instance_type   = var.msk_broker_instance_type
    client_subnets  = aws_subnet.private[*].id
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = var.msk_broker_ebs_volume_size
      }
    }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "PLAINTEXT"
      in_cluster    = true
    }
  }

  client_authentication {
    unauthenticated = true
  }

  logging_info {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = aws_cloudwatch_log_group.msk.name
      }
    }
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-msk"
  })
}
