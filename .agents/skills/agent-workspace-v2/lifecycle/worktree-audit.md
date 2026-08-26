# Worktree 巡检流程

## 触发时机

- BA Agent 每次启动时
- 手动触发

## 流程

### Step 1: 扫描所有 worktree

```bash
cd <repo-root>          # 切到 workspace/ 主 worktree
git worktree list
# 输出样例：
# <repo-root>      workspace  [<repo-root>]
# <repo-root>/code       develop    [<repo-root>/code]
# <repo-root>/BA         demand     [<repo-root>/BA]
# <repo-root>/Deploy     deploy     [<repo-root>/Deploy]
# <repo-root>/feature-REQ-001  feature/REQ-001  [<repo-root>/feature-REQ-001]
```

### Step 2: 过滤系统 worktree

排除 `code/`、`BA/`、`Deploy/`、`<repo-root>`（workspace 主 worktree），
只检查 `feature-*` 和 `hotfix-*`。

### Step 3: 检查分支状态

```bash
cd feature-REQ-xxx
git status --porcelain            # 是否有未提交变更
git log origin/develop..HEAD      # 是否有未推送的 commit
git branch --merged develop | grep feature/REQ-xxx  # 是否已合并
```

### Step 4: 分类处理

| 状态 | 处理 |
|------|------|
| 已合并，无未提交变更 | 清理（见 `worktree-cleanup.md` 正常合并后流程） |
| 已合并，有未提交变更 | 标记异常，不清理 |
| 未合并 | 跳过 |
| 目录存在但分支已不存在 | 强制删除目录 |

### Step 5: 记录结果

记录到 `BA/dispatch/cleanup-log.md`。

---

## workspace 分支巡检（BA Agent 启动必做）

**目的**：保证 `workspace` 分支始终只跟踪 `README.md`，不被业务代码污染。

### Step W1: 切到仓库根

```bash
cd <repo-root>
git rev-parse --abbrev-ref HEAD
# 应输出：workspace
# 如果不是，巡检失败：workspace 主 worktree 丢失，立即告警
```

### Step W2: 检查跟踪文件清单（核心检查）

```bash
git ls-files
# 应只输出两个文件：
# .gitignore
# README.md
# 任何其他文件都是违规
```

**违规判定清单**：

| 输出 | 判定 | 处理 |
|------|------|------|
| 空 | 异常（应有 README.md + .gitignore） | 检查是否漏 commit |
| 只有 `.gitignore` 和 `README.md` | OK | 继续 W3 |
| 含 worktree 目录（`code/` `BA/` `Deploy/` 等） | **严重违规** | 立即 `git rm -r --cached <dir>`，commit `[Workspace] cleanup` |
| 含其他业务文件（src/、tests/、package.json 等） | 违规 | 评估后 `git rm` 或移到对应 worktree |

**.gitignore 防御性测试**（推荐每次巡检跑一次）：

```bash
# 模拟误操作：把所有文件 add
git add .
git status --short
# 应为空（因为 .gitignore 白名单机制已经过滤）
# 如果有任何文件出现 → 违规，说明 .gitignore 白名单被破坏，立即修复
```

### Step W3: 检查仓库根目录结构

```bash
ls <repo-root>
# 应看到：README.md  .gitignore  .git/  code/  BA/  Deploy/  feature-*  hotfix-*
# 不应有：workspaces/  src/  tests/  package.json 等
```

**违规判定**：

- `workspaces/` 等中间目录层 → 不应存在，**违反"无中间层"硬约束**
- 仓库根出现 `src/` `tests/` `package.json` → 业务文件泄漏
- 仓库根出现 `docs/` 等非 README/.gitignore 文件/目录 → 评估：要在 workspace 分支吗？

### Step W4: 检查 worktree 完整性

```bash
git worktree list
# 应对照预期清单：
# - <repo-root> (workspace)
# - <repo-root>/code (develop)
# - <repo-root>/BA (demand)
# - <repo-root>/Deploy (deploy)
# - <repo-root>/feature-* (按需)
# - <repo-root>/hotfix-* (按需)

# 任何 <repo-root>/workspaces/xxx 形式的 worktree → 违规（有中间层）
# 任何 <repo-root>/xxx/code/ 形式的二级嵌套 → 违规
```

### Step W5: 分类处理 + 记录

| 状态 | 处理 |
|------|------|
| 所有检查通过 | 正常 |
| 跟踪文件违规 | `git rm` + commit + 记录 |
| 仓库根出现中间目录层 | 删除目录（如果空）或合并内容到现有 worktree + 记录 |
| worktree 路径违规（有中间层） | `git worktree repair` 或强制清理后重建 |
| workspace 主 worktree 丢失 | **最严重**，立即告警并停止其他工作 |

记录到 `BA/dispatch/cleanup-log.md`：

```
{日期} | workspace-audit | {状态：clean/violation-fixed} | {详情} | {执行者}
2026-08-20 | workspace-audit | clean | 无违规 | ba-agent-01
2026-08-20 | workspace-audit | violation-fixed | 移除误加 src/ + commit | ba-agent-01
2026-08-20 | workspace-audit | violation-fixed | 清理 workspaces/ 中间层 | ba-agent-01
```

---

## 巡检兜底

- BA Agent 启动时如发现 `git worktree list` 输出与预期不符（缺少 code/、BA/、Deploy/ 或 workspace 主 worktree），
  立即告警并停止其他工作，先恢复 workspace 拓扑。
- workspace 主 worktree 丢失是最严重情况，**任何业务 worktree 都依赖它**。
