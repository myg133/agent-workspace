# 发布流程（develop → 生产）

目标：让"上生产"这件事**可追溯、可回滚、不靠记忆**。

## 1. 分支与产物

```text
develop ──► release/vX.Y.Z ──► tag vX.Y.Z ──► main ──► 部署
                │                               ▲
                └── 修复只进 release ───────────┘
hotfix/xxx ─────┴── 合 main 后必须回合 develop
```

| 对象 | 规则 |
|------|------|
| `release/vX.Y.Z` | 从 `develop` 切出，只接受 bugfix，不接受新功能 |
| tag `vX.Y.Z` | 打在 `main` 的发布 commit 上；**部署唯一依据** |
| `main` | 只从 `release` 合并；不直接提交 |
| `hotfix/xxx` | 从 `main` 切出，合回 `main` 后**必须**回合 `develop` |

## 2. 发布步骤

```text
1. 冻结：develop 上相关需求全部 已完成；CI 绿
2. 切分支： git checkout -b release/v1.3.0 develop
3. 改版本号 + CHANGELOG（写"用户可见的变化"）
4. 回归：QA 在 release 分支跑全量回归，出 Post-merge 报告
5. 合并： PR → main（squash 或 merge 由仓库约定），打 tag v1.3.0
6. 部署： Deploy Agent 把 production overlay 的 tag 改为 v1.3.0
7. 验证： 健康检查 + 冒烟；观察 30 分钟
8. 回合： release 上的修复（若有）cherry-pick 回 develop
9. 收尾： 删除 release 分支；releases/ 记录本次清单
```

## 3. 版本号

| 位 | 触发 |
|----|------|
| MAJOR | 不兼容变更 / 大版本重构 |
| MINOR | 新功能，向下兼容 |
| PATCH | 修 bug、配置调整 |

需求号与版本号**没有**换算关系，别用"每个需求一个版本"。

## 4. 回滚

```text
1. 确认坏版本 tag（v1.3.0）与回滚目标（v1.2.4）
2. Deploy Agent 改 production overlay → v1.2.4，commit + push
3. 等 CD rollout 完成，验证
4. 在 main 上打 revert tag 说明（或直接记 releases/）
5. 建 hotfix 分支修根因，合 main + 回合 develop
```

**不要**用 `kubectl rollout undo` 了事 —— 集群状态必须能从 git 重建，否则下次 sync 会把坏版本带回来。

## 5. 发布记录

`Deploy/releases/vX.Y.Z.yaml`：

```yaml
version: v1.3.0
date: 2026-10-21
commit: <main 上的发布 commit>
tag: v1.3.0
images:
  api-gateway: aigccontainer.azurecr.cn/api-gateway:v1.3.0
  user-service: aigccontainer.azurecr.cn/user-service:v1.3.0
verified_by: qa-agent
rollback_to: v1.2.4
```

## 6. 门禁

| 门禁 | 条件 |
|------|------|
| 可以切 release | develop 上目标需求全部 `已完成`，CI 绿 |
| 可以打 tag | release 分支回归通过，无 P0/P1 缺陷 |
| 可以部署 production | tag 存在、QA Post-merge 通过、回滚目标明确 |
| 可以删 release 分支 | 已合 main 且已回合 develop |
