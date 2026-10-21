# 巡检（只读）

BA 每次启动跑一次。原则：**先看拓扑，再看队列，最后看僵尸**。

## 1. 一条命令

```bash
cd <repo-root>/BA
git pull --rebase origin demand
python <skill-path>/scripts/aw.py audit
```

输出四段：workspace 卫生 / worktree 拓扑 / 待回收 / session 状态。退出码非 0 表示有需要修的问题（配合 `verify` 使用）。

## 2. workspace 卫生

```bash
cd <repo-root>
git rev-parse --abbrev-ref HEAD      # 必须是 workspace
git ls-files                         # 必须恰好 .gitignore + README.md
git add -A --dry-run                 # 必须无输出
```

| 现象 | 判定 | 处理 |
|------|------|------|
| `git ls-files` 为空 | 异常（丢文件） | 检查是否漏 commit |
| 出现业务文件 / `code/` 等 | **严重违规** | `git rm -r --cached <path>` + `[Workspace] cleanup` |
| `git add -A --dry-run` 有输出 | ignore 规则失效 | 检查 `/*/` 是否被删 |

## 3. worktree 拓扑

```bash
git worktree list
```

期望：

```text
<repo-root>              workspace
<repo-root>/code         develop
<repo-root>/BA           demand
<repo-root>/Deploy       deploy
<repo-root>/feature-*    feature/REQ-*
```

| 现象 | 判定 | 处理 |
|------|------|------|
| 路径带中间层（`/workspaces/x`） | 违规 | 重建 |
| `code/` 不在 develop | 违规 | `git -C code checkout develop` |
| 主 worktree 不是 workspace | **最严重** | 停止业务，先恢复 |
| 目录在但分支已删 | 僵尸 | `git worktree prune` + 删目录 |

## 4. 待回收

```bash
for d in feature-*; do
  echo "== $d"
  git -C "$d" status --porcelain
  git -C "$d" log --oneline origin/develop..HEAD
  git branch --merged develop --format='%(refname:short)' | grep -F "$(git -C "$d" branch --show-current)" && echo MERGED
done
```

| 状态 | 处理 |
|------|------|
| 已合并 + 干净 + 无未推送 | 回收（`cleanup.md`） |
| 已合并 + 有改动 | 标记待处理，不删 |
| 未合并 | 跳过 |
| 需求已取消 | 强制回收 |

## 5. session / registry

```bash
grep -E '\| *(online|stale) *\|' BA/dispatch/agent-registry.md
# 对每个 session 取最后活动时间：
git log --format=%ct --grep="\[session: <id>\]" -1
```

超过阈值（默认 120 分钟）无 commit → 标 `stale`。**接管必须人工确认。**

## 6. 记录

追加到 `BA/dispatch/cleanup-log.md`：

```text
2026-10-21 | workspace-audit | clean            | 无违规                  | ba-...-a1b2
2026-10-21 | REQ-001        | merged-cleanup   | worktree+branch removed | ba-...-a1b2
2026-10-21 | REQ-002        | cancelled        | forced cleanup          | ba-...-a1b2
```

> 巡检只**发现**和**修跟踪文件**；删 worktree / 删分支见 `cleanup.md`。
