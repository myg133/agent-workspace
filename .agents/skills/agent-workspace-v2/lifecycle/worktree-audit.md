# Worktree 巡检流程

## 触发时机

- BA Agent 每次启动时
- 手动触发

## 流程

### Step 1: 扫描所有 worktree

```bash
git worktree list
```

### Step 2: 过滤系统 worktree

排除 `code/`、`BA/`、`Deploy/`，只检查 `feature-*` 和 `hotfix-*`。

### Step 3: 检查分支状态

```bash
cd feature-REQ-xxx
git status --porcelain            # 是否有未提交变更
git log origin/develop..HEAD       # 是否有未推送的 commit
git branch --merged develop | grep feature/REQ-xxx  # 是否已合并
```

### Step 4: 分类处理

| 状态 | 处理 |
|------|------|
| 已合并，无未提交变更 | 清理 |
| 已合并，有未提交变更 | 标记异常，不清理 |
| 未合并 | 跳过 |
| 目录存在但分支已不存在 | 强制删除目录 |

### Step 5: 记录结果

记录到 `BA/dispatch/cleanup-log.md`。