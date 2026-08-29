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
| **workspace 巡检** | **BA Agent** | **发现 workspace 分支有多于 README.md 的文件 → 清理** |

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

## workspace 分支回收（BA Agent 巡检）

**触发**：workspace 巡检发现 `git ls-files` 不止 `README.md` + `.gitignore`。

```bash
# 1. 在仓库根（workspace/）执行
cd <repo-root>
git ls-files
# 应只输出两个文件：
# .gitignore
# README.md
# 如果有其他文件：违规

# 2. 分类处理
#    - 误加的 README/.gitignore → 保留（这两个是白名单内）
#    - 误加的业务文件 → git rm + commit [Workspace] cleanup
#    - 故意新增的导航文件（如 docs/）→ 评估：要不要保留？保留要 commit，但要更新 .gitignore 白名单

# 3. 记录到 BA/dispatch/cleanup-log.md
# 格式：
# {日期} | workspace-violation | {原因} | {方式} | {执行者}
```

**特别注意**：

- worktree 目录（`code/` `BA/` `Deploy/` 等）**不应**出现在 `git ls-files`（git 通过 `.git/worktrees/` 内部管理）
- 如果 `code/` 出现在 `git ls-files`，说明被错误跟踪了，立即 `git rm -r --cached code/`

## 回收日志格式

```
{日期} | {需求ID 或 workspace-violation} | {原因} | {方式} | {执行者}
2026-08-18 | REQ-001 | 已合并 | 自动清理 | dev-agent-01
2026-08-20 | workspace-violation | 误提交 src/ | git rm + commit | ba-agent-01
```
