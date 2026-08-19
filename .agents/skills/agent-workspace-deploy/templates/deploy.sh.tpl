#!/bin/bash
# deploy.sh - 通用部署脚本
# 用法：./deploy.sh <environment> <app-name>

set -euo pipefail

ENV=${1:-staging}
APP=${2:-}

if [ -z "$APP" ]; then
  echo "用法: ./deploy.sh <environment> <app-name>"
  exit 1
fi

HELM_DIR="apps/$APP/helm"
ENV_FILE="$HELM_DIR/environments/.env.$ENV"

if [ ! -f "$ENV_FILE" ]; then
  echo "错误: 环境文件 $ENV_FILE 不存在"
  exit 1
fi

# 读取环境变量
source "$ENV_FILE"

# 部署
echo "部署 $APP 到 $ENV 环境..."
helm upgrade --install "$APP" "$HELM_DIR" \
  -f "$HELM_DIR/values.yaml" \
  --set image.tag="$IMAGE_TAG" \
  --namespace "$NAMESPACE" \
  --create-namespace

echo "部署完成"