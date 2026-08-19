# Worktree 回收机制

## 原则

每个 worktree 有明确的结束时间点，结束即清理。

## 回收时机

| 触发条件 | 执行者 | 说明 |
|---------|--------|------|
| 正常合并后 | Dev Agent 自清理 | PR 合并后自动清理 |
| 需求取消 | BA Agent 强制清理 | 立即回收 |
| 定期巡检 | BA Agent 兜底清理 | 发现已合并但未清理的 |
| 手动触发 | 用户 | 手动指定 |

## 正常合并后回收（Dev Agent）

```
1. 确认 PR 已合并到 develop
2. git worktree remove feature-REQ-xxx
3. git branch -d feature/REQ-xxx
4. git push origin --delete feature/REQ-xxx
5. 通知 BA Agent
```

## 需求取消时回收（BA Agent）

```
1. 更新 status.md → "cancelled"
2. git worktree remove feature-REQ-xxx --force
3. git branch -D feature/REQ-xxx
4. git push origin --delete feature/REQ-xxx
5. 记录到 cleanup-log.md
```

## 安全检查

删除前必须检查：
- [ ] 分支已合并到目标分支
- [ ] 无未提交的变更（`git status --porcelain` 为空）
- [ ] 无未推送的 commit（`git log origin/develop..HEAD` 为空）
- [ ] 需求状态不是"进行中"

异常情况不自动删除，标记为"待处理"。

## 回收日志格式

```
{日期} | {需求ID} | {原因} | {方式} | {执行者}
2026-08-18 | REQ-001 | 已合并 | 自动清理 | dev-agent-01
```