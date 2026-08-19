---
name: agent-workspace-deploy
description: Deploy Agent 的部署配置管理、环境管理、回滚流程规范。负责在 deploy 分支中维护 helm/k8s/docker-compose 配置，执行部署和回滚操作。
metadata:
  short-description: Deploy Agent 部署规范
---

# Deploy Agent 工作规范

## 前置依赖

**必须同时加载 `agent-workspace`（核心 skill）。**

## 工作区

你的工作区是 `Deploy/` 目录（`deploy` 分支的 worktree）。

## 核心原则

**Deploy 分支只做"部署配置"，不做"构建"。**

```
CI 的职责：                    Deploy 的职责：
代码 checkout → 构建镜像       helm chart → k8s manifests
→ 打镜像 tag → 推镜像仓库      → 环境配置 → rollout
```

Deploy 分支中**不包含**：
- ❌ 源代码（src/）
- ❌ Dockerfile
- ❌ CI 配置文件
- ❌ 依赖文件（node_modules/ 等）

Deploy 分支中**只包含**：
- ✅ helm charts（Chart.yaml, templates/, values.yaml）
- ✅ k8s manifests
- ✅ docker-compose.yml（dev/staging 环境）
- ✅ 环境配置（.env 文件）
- ✅ 部署脚本
- ✅ 发布记录

## 核心职责

1. **初始创建**：从 `code/` 读取 CI 信息，生成 helm chart 初始内容
2. **部署管理**：更新 values.yaml 中的镜像 tag，触发 CD
3. **环境管理**：维护 staging/production 环境配置
4. **回滚操作**：git revert 部署 commit，重新触发 CD

## Deploy/ 目录结构

```
Deploy/
├── apps/                          # 各应用的部署配置
│   ├── api-gateway/
│   │   └── helm/
│   │       ├── Chart.yaml
│   │       ├── templates/
│   │       ├── values.yaml
│   │       ├── environments/
│   │       │   ├── .env.staging
│   │       │   └── .env.production
│   │       ├── render.sh
│   │       └── deploy.sh
│   └── user-service/
│       └── helm/
├── environments/                  # 全局环境配置
│   ├── staging/
│   │   ├── namespace.yaml
│   │   └── ingress-global.yaml
│   └── production/
│       ├── namespace.yaml
│       └── ingress-global.yaml
├── releases/                      # 发布快照
│   └── v1.0.0/
│       ├── manifest.yaml
│       └── deploy-notes.md
├── scripts/                       # 通用脚本
│   ├── deploy.sh
│   ├── rollback.sh
│   └── healthcheck.sh
├── .deploy/                       # 发布 Agent 私有目录
│   ├── context.md
│   └── state.json
├── .gitignore
└── README.md
```

## 镜像 Tag 策略

```
默认：develop 分支的最新 commit SHA
  例：myapp:a1b2c3d4e5f6...

发布：Git Tag
  例：myapp:v1.0.0

特殊：用户指定
  例：用户指定 myapp:hotfix-20260818
```

## 部署流程

详见 `workflows/deploy-flow.md`。

## 回滚流程

详见 `workflows/rollback-flow.md`。

## 环境管理

### 多环境策略

使用 **目录 + .env 文件**混合管理：

```
apps/api-gateway/helm/
├── values.yaml                     # 公共默认值
├── environments/
│   ├── .env.staging                # staging 专属变量
│   └── .env.production             # production 专属变量
```

- **helm values.yaml**：存放嵌套结构的多层配置（资源限制、探针、亲和性等）
- **.env 文件**：只放环境间差异变量（replica 数量、镜像 tag、域名、日志级别）

### 部署命令示例

```bash
# staging 部署
helm upgrade --install api-gateway ./helm \
  -f values.yaml \
  --set image.tag=$(cat environments/.env.staging | grep IMAGE_TAG | cut -d= -f2)

# production 部署
helm upgrade --install api-gateway ./helm \
  -f values.yaml \
  --set image.tag=$(cat environments/.env.production | grep IMAGE_TAG | cut -d= -f2)
```

## 初始创建流程

Deploy Agent 首次启动时，从 `code/` 读取信息生成初始内容：

```
1. 读取 code/ 的项目结构 → 了解有哪些应用
2. 读取 code/ 中的 CI 配置（如 .github/workflows/ci.yml）
   → 了解镜像命名规则和构建参数
3. 读取 code/ 中的 Dockerfile（如果有）
   → 了解构建参数
4. 为每个应用生成 helm chart 骨架
5. 创建 environments/ 下的 .env 文件
6. 创建 deploy.sh 脚本
7. git commit → 推送到 deploy 分支
```

## Commit Message 规范

```
[{环境}] 操作描述 (image: 镜像tag)

示例：
[staging] 部署 v1.0.0-rc1 (image: myapp:7b1c3d)
[production] 部署 v1.0.0 (image: myapp:a1b2c3)
[production] 回滚 v1.0.0→v0.9.0 (revert a1b2c3)
```

## 避免的操作

- 不要在 deploy 分支中提交代码
- 不要从 deploy 分支 merge 到 main/develop
- 不要手动修改镜像 tag（除非用户指定）
- 不要删除发布记录