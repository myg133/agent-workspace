# Worktree 回收机制

## 原则

每个 worktree 有明确的结束时间点，结束即清理。**所有 worktree 在仓库根平铺**，
回收路径使用相对路径（从仓库根出发）。

## 回收时机

| 触发条件 | 执行者 | 说明 |
|---------|--------|------|
| 正常合并后 | Dev Agent 自清理 | PR 合并后自动清理 |
| 需求取消 | BA Agent 强制清理 | 立即回收 |
| 定期巡检 | BA Agent 兜底清理 | 发现已合并但未清理的 |
| 手动触发 | 用户 | 手动指定 |
| **workspace 巡检** | **BA Agent** | **发现违规 → 见 `worktree-audit.md` 末节** |

## 正常合并后回收（Dev Agent）

**当前工作目录**：`feature-REQ-xxx/`（feature 分支的 worktree）

```bash
# 1. 确认 PR 已合并到 develop
git fetch origin
git log origin/develop..HEAD   # 应为空

# 2. 切到仓库根（workspace/ 主 worktree）执行回收
cd <repo-root>                 # 切到 workspace/ 主 worktree
git worktree remove feature-REQ-xxx
git branch -d feature/REQ-xxx
git push origin --delete feature/REQ-xxx

# 3. 通知 BA Agent
```

> **路径基准**：`git worktree remove` 的参数是 worktree 目录相对 git 仓库根的路径，
> 等价于 `<repo-root>/feature-REQ-xxx`。

## 需求取消时回收（BA Agent）

```bash
# 1. 更新 status.md → "cancelled"
# 2. 强制清理
cd <repo-root>
git worktree remove feature-REQ-xxx --force
git branch -D feature/REQ-xxx
git push origin --delete feature/REQ-xxx
# 3. 记录到 BA/dispatch/cleanup-log.md
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

> **workspace 分支巡检**：发现 `git ls-files` 违规属于巡检范畴，详见 `worktree-audit.md` 末节。
> 清理日志格式见 `worktree-audit.md` 中的记录规范。
