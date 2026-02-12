resource "random_password" "db_password" {
  length  = 20
  special = true
}

resource "aws_db_subnet_group" "eventflow" {
  name       = "${local.name_prefix}-db-subnet-group"
  subnet_ids = aws_subnet.private[*].id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-db-subnet-group"
  })
}

resource "aws_db_instance" "eventflow" {
  identifier              = "${local.name_prefix}-postgres"
  engine                  = "postgres"
  engine_version          = "16.3"
  instance_class          = var.db_instance_class
  allocated_storage       = var.db_allocated_storage
  storage_type            = "gp3"
  db_name                 = var.db_name
  username                = var.db_username
  password                = local.database_password
  db_subnet_group_name    = aws_db_subnet_group.eventflow.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  publicly_accessible     = false
  multi_az                = false
  backup_retention_period = 0
  deletion_protection     = false
  skip_final_snapshot     = true
  apply_immediately       = true

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-postgres"
  })
}
