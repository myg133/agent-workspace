# {项目名称}

> {一句话说明项目做什么、给谁用}

本仓库采用 **Agent Workspace 工作流**（参见 `.agents/skills/agent-workspace-v2/`），
使用 `workspace` 分支作为根容器，**所有 worktree 在仓库根平铺**（无中间目录层）。

## 目录 ↔ 分支对应表

| 路径 | 分支 | 角色 | 说明 |
|------|------|------|------|
| `./` | `workspace` | **根容器** | **只跟踪 README.md**（`.gitignore` 不进 git） |
| `code/` | `develop` | CI 主工作区 | 主开发分支，CI 构建源 |
| `BA/` | `demand` | BA Agent | 需求管理、迭代计划、Agent 注册 |
| `Deploy/` | `deploy` | Deploy Agent | helm/k8s/部署配置，不做构建 |
| `feature-REQ-xxx/` | `feature/REQ-xxx` | Dev Agent | 需求开发，按需创建，合并后清理 |
| `hotfix-xxx/` | `hotfix/xxx` | Dev Agent | 紧急修复，按需创建 |

**所有 worktree 跟 `README.md` 同级**，在仓库根平铺，没有中间目录层（如 `workspaces/`）。

## 快速上手

### 1. 克隆仓库

```bash
git clone <url> my-project
cd my-project
# 默认在 workspace/ 主 worktree，看到这份 README
```

### 2. 注册主 worktree（如已部署过可跳过）

```bash
git worktree add code develop
git worktree add BA demand
git worktree add Deploy deploy
```

### 3. 接到需求后

在仓库根跑：

```bash
git worktree add feature-REQ-001 -b feature/REQ-001 develop
```

或在 `BA/` 里跑（用 `../` 回到仓库根，再平铺）：

```bash
cd BA
git worktree add ../feature-REQ-001 -b feature/REQ-001 develop
```

新 worktree 跟 `code/` `BA/` 在仓库根平铺，**没有中间目录层**。

### 4. 提交 PR

在 `feature-REQ-xxx/` 里编码、测试、提交：

```bash
git commit -m "[Dev] {描述} (关联: REQ-xxx)"
git push -u origin feature/REQ-xxx
# 在 GitHub/GitLab 创建 PR → develop
```

PR 合并后 Dev Agent 自动清理 worktree（详见 `.agents/skills/agent-workspace-v2/lifecycle/worktree-cleanup.md`）。

## 各角色 Agent 入口

- **BA Agent**（主 agent）→ 进入 `BA/` 目录
- **Dev Agent**（子 agent）→ 进入 `feature-REQ-xxx/` 目录
- **QA Agent**（子 agent）→ Pre-merge 进 `feature-REQ-xxx/`，Post-merge 进 `code/` + staging
- **Deploy Agent**（子 agent）→ 进入 `Deploy/` 目录

新 agent 启动时必须加载 `.agents/skills/agent-workspace-v2/SKILL.md`。

## 硬规则

- ❌ `workspace` 分支**只跟踪 `README.md`**（`git ls-files` 必须只有这一个）
- ❌ 不向 `workspace` 分支提交 PR
- ❌ 不在仓库根加中间目录层（禁止 `workspaces/` `agents/` 等中间层放 worktree）
- ❌ 不做 worktree 二级嵌套（禁止 `feature-xxx/code/`）
- ✅ 各 worktree 自己的 `.gitignore` 由对应 agent 维护（**不进 workspace 分支**）
- ✅ BA Agent 每次启动时执行 workspace 巡检

## 详细文档

- 工作流规范：`.agents/skills/agent-workspace-v2/SKILL.md`
- 初始化：`.agents/skills/agent-workspace-v2/init/`
- 生命周期：`.agents/skills/agent-workspace-v2/lifecycle/`
- 模板：`.agents/skills/agent-workspace-v2/templates/`
- 各角色 README：见对应 worktree 根目录（如 `BA/README.md`）

## 平台运行目录

如果你在云开发平台（Claude.ai Projects、Cursor Cloud、Codespaces 等）使用本仓库：

- 平台的"运行目录"通常绑定到仓库根（`my-project/` = `workspace/` 主 worktree）
- 所有 worktree 都在仓库根平铺，**没有中间目录层、没有 worktree 嵌套**
- 平台无关：git worktree add 用相对路径 `xxx` 即可
- 不需要任何特殊适配
