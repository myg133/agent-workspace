# worktree 回收

原则：**一个 worktree 的寿命 = 一个需求的寿命**，结束即回收。

## 1. 时机

| 触发 | 执行者 | 方式 |
|------|--------|------|
| PR 合并 + Post-merge 通过 | Dev（自清理）或 BA | 正常回收 |
| 需求取消 | BA | 强制回收 |
| 巡检发现已合并残留 | BA | 正常回收 |
| 用户要求 | BA | 按状态选择 |

## 2. 正常回收

```bash
cd <repo-root>

# 安全检查（四项全过才删）
git -C feature-REQ-001 status --porcelain          # 必须为空
git -C feature-REQ-001 log --oneline origin/develop..HEAD   # 必须为空
git branch --merged develop | grep -F feature/REQ-001       # 必须命中
grep -q '已完成\|已取消' BA/demands/REQ-001-*/status.md      # 需求已终结

git worktree remove feature-REQ-001
git branch -d feature/REQ-001
git push origin --delete feature/REQ-001
```

`git branch -d`（小写 d）在未合并时会拒绝 —— 这是最后一道保险，别随手换成 `-D`。

## 3. 强制回收（需求取消 / 分支已丢）

```bash
git worktree remove feature-REQ-001 --force
git branch -D feature/REQ-001 2>/dev/null || true
git push origin --delete feature/REQ-001 2>/dev/null || true
git worktree prune
```

强制前必须：

- 需求状态 = `已取消`；
- 有未提交改动时，先把有价值的内容导出到 `BA/demands/REQ-xxx/archive/`；
- 在 `cleanup-log.md` 记录强制原因。

## 4. 安全检查清单

- [ ] 分支已合并到目标分支（或需求已取消）
- [ ] `git status --porcelain` 为空
- [ ] `git log origin/develop..HEAD` 为空
- [ ] 需求状态不是 `进行中` / `待验证`
- [ ] 已通知相关 Dev/QA

任何一项不满足 → 标"待处理"，不自动删。

## 5. 日志

```text
{日期} | {REQ} | {原因} | {方式} | {执行者}
2026-10-21 | REQ-001 | 已合并 | 正常回收 | dev-a1b2
2026-10-21 | REQ-002 | 已取消 | 强制回收（改动导出到 archive/） | ba-c3d4
```

日志写在 `BA/dispatch/cleanup-log.md`，随下次 BA commit 一起提交。
