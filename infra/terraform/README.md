# EventFlow AWS Deployment (Terraform)

This Terraform stack deploys a practical single-environment EventFlow setup on AWS:

- VPC with public and private subnets
- ECS Fargate cluster with 5 services
  - `api-producer`
  - `validator-consumer`
  - `analytics-consumer`
  - `persistent-consumer-java`
  - `external-payment-simulator` (auto-stream enabled)
- Public ALB for API ingress
- Amazon MSK (Kafka, PLAINTEXT, unauthenticated for demo use)
- Amazon RDS PostgreSQL
- ECR repositories for all service images
- CloudWatch log groups for each service

## Important

This is a deployment baseline for interview/demo value, not a hardened production template.
Before production use, tighten network boundaries, secrets handling, encryption/auth for Kafka,
HA, backup/restore, and cost controls.

## Prerequisites

- Terraform `>= 1.5`
- AWS CLI configured (`aws configure`)
- Docker
- Permissions to create VPC/ECS/MSK/RDS/ECR/IAM/CloudWatch resources

## Release CD Workflow

Repository includes a release CD pipeline at:

- `.github/workflows/cd-release.yml`

It triggers on Git tags:

- `v*` (for example `v1.0.0`)
- `release-*` (for example `release-2026-02-11`)

The workflow sequence is:

1. Resolve image tag from the pushed Git tag.
2. Initialize Terraform with an S3 backend.
3. Bootstrap ECR repositories only.
4. Build and push all service images to ECR with the release tag.
5. Run full `terraform apply`.

Configure these GitHub repository **Variables**:

- `AWS_REGION` (optional, default `us-east-1`)
- `PROJECT_NAME` (optional, default `eventflow`)
- `DEPLOY_ENVIRONMENT` (optional, default `dev`)
- `TF_STATE_BUCKET` (required, S3 bucket for Terraform state)
- `TF_STATE_KEY` (optional, default `<project>/<environment>/terraform.tfstate`)
- `TF_STATE_DYNAMODB_TABLE` (optional, for Terraform state locking)

State backend resources must already exist before the workflow runs (S3 bucket and optional DynamoDB lock table).

Configure these GitHub repository **Secrets**:

- `PAYMENT_PROVIDER_WEBHOOK_SECRET` (required)
- `AWS_ROLE_TO_ASSUME` (recommended, OIDC role ARN)
- Or fallback:
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_SESSION_TOKEN` (optional)

## 1. Configure Variables

Copy and edit:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
```

Set at minimum:

- `aws_region`
- `environment`
- `payment_provider_webhook_secret`
- `image_tags` (if not using `latest`)

## 2. Provision Infrastructure

```bash
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

Useful outputs:

```bash
terraform output alb_dns_name
terraform output api_webhook_url
terraform output msk_bootstrap_brokers
terraform output rds_jdbc_url
terraform output -json ecr_repository_urls
```

## 3. Build and Push Service Images

From repository root:

```bash
./scripts/build-and-push-images.sh \
  --aws-region us-east-1 \
  --project-name eventflow \
  --environment dev \
  --image-tag latest
```

This script tags and pushes images to the ECR repositories created by Terraform.

## 4. Roll ECS Tasks to New Image Tags

Update `image_tags` in `terraform.tfvars` if needed, then:

```bash
terraform plan -out=tfplan
terraform apply tfplan
```

## 5. Smoke Checks

API health:

```bash
curl "http://$(terraform output -raw alb_dns_name)/health"
```

Send one event through simulator endpoint (if you expose it externally later) or rely on auto-stream.

Verify persistence (requires AWS access to RDS endpoint):

- Check ECS logs for:
  - validator validated events
  - persistence stored events
  - analytics processed events

## 6. Tear Down

```bash
terraform destroy
```
