# Preview 环境配置
# 用于 CI 为 feature 分支部署临时预览环境

replicaCount: 1

image:
  tag: preview-${GIT_SHA}

ingress:
  host: preview-${PR_NUMBER}.${DOMAIN}

resources:
  requests:
    memory: "128Mi"
    cpu: "100m"
  limits:
    memory: "256Mi"
    cpu: "200m"

# 预览环境自动清理
cleanup:
  enabled: true
  ttl: 3600  # 1小时后自动清理