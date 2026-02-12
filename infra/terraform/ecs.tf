resource "aws_ecs_cluster" "eventflow" {
  name = "${local.name_prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-cluster"
  })
}

resource "aws_cloudwatch_log_group" "service" {
  for_each = local.service_definitions

  name              = "/ecs/${local.name_prefix}/${each.value.service_name}"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

resource "aws_lb" "eventflow" {
  name               = "${local.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-alb"
  })
}

resource "aws_lb_target_group" "api" {
  name        = "${local.name_prefix}-api-tg"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.eventflow.id

  health_check {
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 20
    timeout             = 5
    path                = "/health"
    matcher             = "200-399"
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-api-tg"
  })
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.eventflow.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_ecs_task_definition" "service" {
  for_each = local.service_definitions

  family                   = "${local.name_prefix}-${each.value.service_name}"
  cpu                      = tostring(each.value.cpu)
  memory                   = tostring(each.value.memory)
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    merge(
      {
        name      = each.value.service_name
        image     = "${aws_ecr_repository.service[each.value.repository_key].repository_url}:${lookup(var.image_tags, each.key, "latest")}"
        essential = true
        environment = [
          for env_name, env_value in each.value.environment : {
            name  = env_name
            value = tostring(env_value)
          }
        ]
        logConfiguration = {
          logDriver = "awslogs"
          options = {
            awslogs-group         = aws_cloudwatch_log_group.service[each.key].name
            awslogs-region        = var.aws_region
            awslogs-stream-prefix = each.value.service_name
          }
        }
      },
      each.value.port == null ? {} : {
        portMappings = [
          {
            containerPort = each.value.port
            hostPort      = each.value.port
            protocol      = "tcp"
          }
        ]
      }
    )
  ])

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-${each.value.service_name}-task"
  })
}

resource "aws_ecs_service" "service" {
  for_each = local.service_definitions

  name            = "${local.name_prefix}-${each.value.service_name}"
  cluster         = aws_ecs_cluster.eventflow.id
  task_definition = aws_ecs_task_definition.service[each.key].arn
  desired_count   = each.value.desired_count
  launch_type     = "FARGATE"

  deployment_maximum_percent         = 200
  deployment_minimum_healthy_percent = 50
  enable_execute_command             = true
  force_new_deployment               = true

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = true
  }

  dynamic "load_balancer" {
    for_each = each.value.attach_to_alb ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.api.arn
      container_name   = each.value.service_name
      container_port   = each.value.port
    }
  }

  depends_on = [aws_lb_listener.http]

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-${each.value.service_name}"
  })
}
