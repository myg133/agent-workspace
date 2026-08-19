# Worktree 巡检流程

## 触发时机

- BA Agent 每次启动时
- 每日定时巡检（如每小时）
- 手动触发

## 巡检流程

### Step 1: 扫描所有 worktree

```bash
git worktree list
```

输出示例：
```
D:\project\code                  develop
D:\project\BA                    demand
D:\project\Deploy                deploy
D:\project\feature-REQ-001       feature/REQ-001
D:\project\feature-REQ-002       feature/REQ-002
D:\project\feature-REQ-003       feature/REQ-003
```

### Step 2: 过滤非系统 worktree

排除 `code/`、`BA/`、`Deploy/` 这三个系统 worktree，只检查 `feature-*` 和 `hotfix-*` worktree。

### Step 3: 对每个 worktree 检查分支状态

对每个 feature/hotfix worktree，执行以下检查：

```bash
# 进入 worktree 目录
cd feature-REQ-xxx

# 检查是否有未提交变更
git status --porcelain

# 检查是否有未推送的 commit
git log origin/develop..HEAD --oneline

# 检查分支是否已合并到 develop
git branch --merged develop | grep feature/REQ-xxx
```

### Step 4: 分类处理

| 状态 | 处理方式 |
|------|---------|
| 已合并到 develop，无未提交变更 | 执行清理（删除 worktree 和分支） |
| 已合并到 develop，有未提交变更 | 标记为"异常"，不清理，通知人工介入 |
| 未合并，无未提交变更 | 跳过，继续观察 |
| 未合并，有未提交变更 | 跳过，标记为"活跃中" |
| worktree 目录存在但分支已不存在 | 强制删除 worktree 目录 |

### Step 5: 记录巡检结果

记录到 `BA/dispatch/cleanup-log.md`：

```
## 巡检记录
### 2026-08-19 10:00:00
- REQ-001: 已合并 → 清理完成
- REQ-003: 已合并，有未提交变更 → 异常，待人工处理
- REQ-005: 未合并，活跃中 → 跳过
```

## 巡检配置

在 `BA/dispatch/rules.md` 中配置巡检策略：

```yaml
# 巡检策略
audit:
  enabled: true
  interval_minutes: 60
  auto_clean_merged: true
  skip_directories:
    - code
    - BA
    - Deploy
  notify_on_abnormal: true
```

## 异常处理

发现异常情况时：
1. 记录异常信息到巡检日志
2. 更新 `BA/demands/REQ-xxx/status.md` → "异常"
3. 通知用户或相关 Agent 人工介入