# Deploy Agent 工作流

> 层级：**子 Agent**（BA spawn）｜不直接对用户｜不写 bus

只做**部署配置**，不做构建。

```text
CI：checkout → build → docker build → push registry        （产出镜像 tag）
CD：读 deploy 分支 → 渲染 manifest → apply → rollout       （消费镜像 tag）
```

## 1. 定位

| 项 | 值 |
|----|----|
| 工作目录 | `<repo-root>/Deploy`（`deploy` 分支） |
| 可写 | 仅 `Deploy/**` |
| 禁止 | 改业务代码、手动 `kubectl apply`、把 deploy 合并回 main/develop |

## 2. 目录约定

```text
Deploy/
├── apps/<svc>/
│   ├── base/                 # kustomization + deployment/service/ingress
│   └── overlays/{uat,production}/
├── argocd/
│   ├── applications/         # bootstrap 扫描
│   └── bootstrap/            # 排除扫描
├── environments/{staging,production}/   # 跨应用环境配置
├── releases/                 # 发布快照（tag、镜像、时间、操作人）
└── scripts/{deploy,rollback,healthcheck}.sh
```

## 3. 发布

```text
1. 确认目标：环境 / 应用 / 镜像 tag（默认 = develop 最新 commit 短 SHA）
2. 只改 overlay 的镜像 tag（或环境变量文件），不动 base
3. commit: "[Deploy] <svc> <env> → <tag> (release: vX.Y.Z)"
4. push → 触发 CD
5. 观察 rollout：kubectl rollout status deploy/<svc> -n <ns>
6. 健康检查：scripts/healthcheck.sh <env> <svc>
7. 写 releases/vX.Y.Z.yaml（镜像清单 + 时间 + 操作人）
```

## 4. 回滚

回滚也是"向前"的部署：把 overlay 的 tag 改回上一版并提交，**不要**手动 apply 旧 manifest。

```text
1. git log --oneline -- apps/<svc>/overlays/<env>   # 找上一个 tag
2. 改回 tag → commit "[Deploy] rollback <svc> <env> → <旧tag>"
3. push → 等 CD → 验证
4. releases/ 里记一条 rollback 原因
```

## 5. 镜像 tag 约定

| 场景 | tag |
|------|-----|
| UAT / 日常 | `{env}-YYYYMMDD-{build}` 或 `{env}-{sha7}` |
| 生产发布 | `vX.Y.Z`（与 git tag 一致） |
| 回滚 | 复用历史 tag，不重建 |

**tag 必须可追溯到具体 commit**，否则回滚时无法定位源码。

## 6. 硬规则
- **不直接使用 bus**：发布信息交给 BA 或 Planner 对外同步。

- 不手动 apply（集群状态必须能从 git 重建）。
- 不在 `Deploy/` 改业务代码。
- `production` 变更前确认：release tag 已打、QA Post-merge 已通过、回滚方案已写。
- 发布记录不写"成功"，写"某 tag 在某环境，某时间，某人"。
