# Worktree 回收机制

## 原则

每个 worktree 都有明确的结束时间点，结束即清理。不做回收的 worktree 会堆积在目录平面中，降低管理效率。

## 回收时机

| 触发条件 | 优先级 | 执行者 | 说明 |
|---------|--------|--------|------|
| 正常合并后 | 最常见 | Dev Agent 自清理 | feature 分支 PR 合并到 develop 后自动清理 |
| 需求取消 | 高 | BA Agent 强制清理 | 需求取消，立即回收 worktree 和分支 |
| 工作区巡检 | 兜底 | BA Agent 定期巡检 | 发现已合并但未清理的 worktree，兜底清理 |
| 手动触发 | 用户 | 用户指定 | 手动清理指定 worktree |

## 回收流程

### 场景 1：正常合并后自动回收（Dev Agent 执行）

```
1. 确认 PR 已合并到 develop 分支
2. 确认 develop 分支已包含本次变更
   → git log --oneline develop | grep "REQ-xxx"
3. 删除本地 worktree 目录
   → git worktree remove feature-REQ-xxx
4. 删除本地 feature 分支
   → git branch -d feature/REQ-xxx
5. 删除远程 feature 分支
   → git push origin --delete feature/REQ-xxx
6. 清理 .feature/ 目录（如果存在）
7. 通知 BA Agent：REQ-xxx 已完成，worktree 已清理
```

### 场景 2：需求取消时强制回收（BA Agent 执行）

```
1. 更新 BA/demands/REQ-xxx/status.md → cancelled
2. 检查 worktree 是否存在
   → git worktree list | grep feature-REQ-xxx
3. 如果存在，强制删除
   → git worktree remove feature-REQ-xxx --force
4. 删除本地和远程分支
   → git branch -D feature/REQ-xxx
   → git push origin --delete feature/REQ-xxx
5. 更新 sprint/current.md
6. 记录到 BA/dispatch/cleanup-log.md
```

### 场景 3：定期巡检兜底回收（BA Agent 执行）

详见 `worktree-audit.md`。

## 安全检查

**删除 worktree 前，必须检查以下所有项：**

- [ ] worktree 目录是否存在
- [ ] 分支是否已合并到目标分支（develop 或 main）
- [ ] 有无未提交的变更（`git status --porcelain` 输出为空）
- [ ] 有无未推送的 commit（`git log origin/develop..HEAD` 输出为空）
- [ ] 需求的最终状态不是"进行中"

**异常处理：**
- 以上任何一项未通过 → 标记为"待处理"，不自动删除
- 有未提交变更 → 报告异常，人工介入
- 需求状态为"进行中"但已合并 → 可能是误合并，需要人工确认

## Hotfix Worktree 回收

hotfix 的回收流程与 feature 一致，只是目标分支为 `main`：

```
1. hotfix 修复完成，PR 合并到 develop + main
2. 清理 hotfix worktree
3. 删除 hotfix/xxx 分支
```

## 回收日志格式

回收操作必须记录到 `BA/dispatch/cleanup-log.md`，格式如下：

```
{日期} | {需求ID} | {原因} | {方式} | {执行者}
2026-08-18 | REQ-001 | 已合并 | 自动清理 | dev-agent-01
2026-08-18 | REQ-002 | 已取消 | 强制清理 | ba-agent
2026-08-19 | REQ-005 | 已合并 | 巡检清理 | ba-agent
```

## 特殊场景：需求重新打开

如果某个已关闭的需求需要重新打开：

```
1. 检查清理记录，确认原 worktree 已删除
2. 重新创建 worktree，使用原目录名
3. 从原分支重新派生（如果分支还在），或从 develop 创建新分支
4. 清理记录中补充标记为"重新打开"
```