#!/usr/bin/env bash
set -euo pipefail

AWS_REGION=""
PROJECT_NAME="eventflow"
ENVIRONMENT="dev"
IMAGE_TAG="latest"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --aws-region)
      AWS_REGION="$2"
      shift 2
      ;;
    --project-name)
      PROJECT_NAME="$2"
      shift 2
      ;;
    --environment)
      ENVIRONMENT="$2"
      shift 2
      ;;
    --image-tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [[ -z "${AWS_REGION}" ]]; then
  echo "Missing required argument: --aws-region"
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "aws CLI is required."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required."
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "Logging in to ECR: ${ECR_REGISTRY}"
aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${ECR_REGISTRY}"

build_and_push() {
  local repo_suffix="$1"
  local service_dir="$2"
  local image_uri="${ECR_REGISTRY}/${PROJECT_NAME}-${ENVIRONMENT}-${repo_suffix}:${IMAGE_TAG}"

  echo "Building ${service_dir} -> ${image_uri}"
  docker build -t "${image_uri}" "${ROOT_DIR}/${service_dir}"
  docker push "${image_uri}"
}

build_and_push "api-producer" "services/api-producer"
build_and_push "validator-consumer" "services/validator-consumer"
build_and_push "analytics-consumer" "services/analytics-consumer"
build_and_push "persistent-consumer-java" "services/persistent-consumer-java"
build_and_push "external-payment-simulator" "services/external-payment-simulator"

echo "All images pushed successfully."
