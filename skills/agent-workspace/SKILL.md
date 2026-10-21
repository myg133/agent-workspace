---
name: agent-workspace
description: 基于 Git worktree 的多 Agent 协作工作区规范。用于初始化或迁移项目为 workspace 布局（workspace 根容器 + code/BA/Deploy 平铺 worktree）、按 BA/Dev/QA/Deploy/Explore 角色分工开发、管理需求状态机与 REQ 编号、巡检与回收 worktree、发布与回滚。当用户要建立项目工作区、搭多 agent 开发流水线、规范分支/worktree/提交、迁移已有仓库到 worktree 结构、或排查 worktree 拓扑与 workspace 分支污染时使用。
metadata:
  short-description: Git worktree 多 Agent 协作工作区
  version: 1.2.0
---

# Agent Workspace

一套"用 Git 当状态层"的多 Agent 开发工作流：**一个需求 = 一个 worktree = 一个容器**，BA 写需求、Dev 写代码、QA 只验证、Deploy 只管部署，所有状态落在 Git 里。

## 30 秒上手

```bash
# 新项目
python <skill-path>/scripts/aw.py init my-project --name "My Project" --remote <url>

# 已有仓库迁移（先读 references/init/migrate-project.md 的前置条件）
python <skill-path>/scripts/aw.py migrate --main develop

# 任何 workspace 仓库里自检
python <skill-path>/scripts/aw.py verify
python <skill-path>/scripts/aw.py audit
```

## 目录布局

```text
<repo-root>/              workspace 分支：只跟踪 README.md + .gitignore
├── code/                 develop   业务源码、CI 源
├── BA/                   demand    需求、迭代、调度表
├── Deploy/               deploy    部署配置（不做构建）
├── feature-REQ-001/      feature/REQ-001   按需，合并即回收
└── hotfix-xxx/           hotfix/xxx        按需，合并即回收
```

所有 worktree **直接位于仓库根下一层**，无中间层、无嵌套。

## 分支

| 分支 | 类型 | worktree | 写入者 | 基分支 |
|------|------|----------|--------|--------|
| `workspace` | orphan | `<repo-root>/` | BA（极少） | — |
| `main` | orphan | — | 发布管理员 | — |
| `develop` | 普通 | `code/` | 仅 PR 合并 | `main` |
| `demand` | orphan | `BA/` | BA | — |
| `deploy` | orphan | `Deploy/` | Deploy / CD | — |
| `feature/REQ-xxx` | 普通 | `feature-REQ-xxx/` | Dev | `develop` |
| `release/vX.Y.Z` | 普通 | — | 发布管理员 | `develop` |
| `hotfix/xxx` | 普通 | `hotfix-xxx/` | Dev | `main` |

`workspace` / `main` / `demand` / `deploy` 互无父节点，各自管理自己的 `.gitignore`。

## 硬约束

1. `workspace` 分支的 `git ls-files` **必须恰好** `.gitignore` + `README.md`。
2. 根 `.gitignore` 用双层防御：`*` → `!*/` → `!.gitignore` `!README.md` → `/*/`。
3. 禁止中间层（`workspaces/code/`）与二级嵌套（`feature-x/code/`）。
4. `status.md` 只有 BA 能改；QA 不 commit；Dev 不改状态。
5. 跨 worktree 引用一律写 `<repo-root>/...` 绝对路径。
6. 一个 worktree 只服务一个需求，合并即回收。
7. `develop` 只通过 PR 合并；`main` 只从 `release` 合并。
8. 命令铁律：`git checkout --orphan` 之后用 `git reset`，**绝不用 `git rm -rf .`**（会删工作区文件）。

## 我该读什么

| 你是 | 先读 | 再读 |
|------|------|------|
| **BA** | `references/roles/ba.md` | `global/concurrency.md`、`global/state-machine.md` |
| **Dev** | `references/roles/dev.md` | `global/paths.md` |
| **QA** | `references/roles/qa.md` | `global/state-machine.md`（写入权） |
| **Deploy** | `references/roles/deploy.md` | `lifecycle/release.md` |
| **Explore** | `references/roles/explore.md` | `global/paths.md` |
| 初始化项目 | `references/init/new-project.md` | `global/layout.md` |
| 迁移仓库 | `references/init/migrate-project.md` | — |
| 巡检 / 回收 | `references/lifecycle/audit.md` | `lifecycle/cleanup.md` |
| 发布 | `references/lifecycle/release.md` | `roles/deploy.md` |

子 Agent 的 prompt 里应当**直接给出角色文件路径**，不要让它自己猜该读哪一节。

## 路径基准

`<repo-root>` 是 workspace 主 worktree 的绝对路径，任意 worktree 里这样取：

```bash
ROOT="$(git rev-parse --path-format=absolute --git-common-dir | xargs dirname)"
```

- 自己的文件：相对路径即可。
- 别人的文件：`<repo-root>/BA/demands/REQ-xxx/...`（**不是** `BA/...`）。
- 兄弟 worktree 物理可见，但**只可读、不可写**。

## 脚本

| 命令 | 作用 | 退出码 |
|------|------|--------|
| `aw.py init <dir>` | 建 workspace 项目（幂等） | 0 / 非 0 |
| `aw.py migrate --main <branch>` | 原地迁移已有仓库 | 0 / 非 0 |
| `aw.py verify` | 校验硬约束（可挂 CI / pre-commit） | 0 通过，1 违规 |
| `aw.py audit` | 只读巡检，输出四段报告 | 0 干净，1 有问题 |
| `aw.py next-req` | 计算下一个可用 REQ 编号 | 0 |

依赖：Python 3.8+，git 2.20+。脚本只调用 git 命令，不写 .git 内部结构。

## 提交格式

```text
[{区域}] {描述} (关联: {REQ}) [session: {id}]
```

只有 `demand` 分支强制带 `[session: ...]`，用于多 BA 追溯。

## 常见错误

| 症状 | 原因 | 修复 |
|------|------|------|
| `git ls-files` 出现 `code/` 或业务文件 | workspace 分支被污染 | `git rm -r --cached <path>` + `[Workspace] cleanup` |
| `git add .` 在根加进东西 | `/*/` 被删或 `.gitignore` 被改 | 恢复模板，跑 `aw.py verify` |
| 子 Agent 找不到需求文档 | 用了 `BA/...` 相对路径 | 改用 `<repo-root>/BA/...` |
| `worktree add` 报 `already exists` | 目标目录非空 | 先腾空目录（见 migrate 第 4 步） |
| `git rm -rf .` 后文件全没了 | 该命令会删工作区 | `git checkout <branch> -- .` 找回；以后用 `git reset` |
| QA 和 BA 同时改状态 | 写入权没守住 | 只允许 BA 写 `status.md` |

## 文件索引

| 路径 | 内容 |
|------|------|
| `references/global/layout.md` | 目录、分支、命名、worktree 生命周期 |
| `references/global/paths.md` | 路径基准与兄弟目录可见性 |
| `references/global/gitignore.md` | 双层防御原理与验证 |
| `references/global/state-machine.md` | 状态机、单一写入者、门禁 |
| `references/global/concurrency.md` | 多 BA：session、懒注册、认领、冲突 |
| `references/roles/*.md` | 五个角色的完整工作流 |
| `references/init/*.md` | 新建 / 迁移 |
| `references/lifecycle/*.md` | 巡检 / 回收 / 发布 |
| `assets/templates/*.tpl` | 根容器、需求、验收、状态、registry、feature 产物 |
| `scripts/aw.py` | init / migrate / verify / audit / next-req |
