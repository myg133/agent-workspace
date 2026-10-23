---
name: agent-workspace
description: 基于 Git worktree 的多 Agent 协作工作区规范，面向中大型、多需求并行、需要可追溯交付的项目（小型脚本或一次性任务不适用）。用于初始化或迁移项目为 workspace 布局（workspace 根容器 + code/BA/Deploy 平铺 worktree）、按 Planner/BA/Dev/QA/Deploy/Explore 角色分工开发、管理需求状态机与 REQ 编号、巡检与回收 worktree、发布与回滚。当用户要建立项目工作区、搭多 agent 开发流水线、规范分支/worktree/提交、迁移已有仓库到 worktree 结构、或排查 worktree 拓扑与 workspace 分支污染时使用。
metadata:
  short-description: Git worktree 多 Agent 协作工作区
  version: 1.15.1
---

# Agent Workspace

一套"用 Git 当状态层"的多 Agent 开发工作流：**一个需求 = 一个 worktree = 一个容器**，
Planner 定方向、BA 写需求、Dev 写代码、QA 只验证、Deploy 只管部署，所有状态落在 Git 里。

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
| `demand` | orphan | `BA/` | BA（`demands/`）、Planner（`plan/` `decisions/`） | — |
| `deploy` | orphan | `Deploy/` | Deploy / CD | — |
| `feature/REQ-xxx` | 普通 | `feature-REQ-xxx/` | Dev | `develop` |
| `release/vX.Y.Z` | 普通 | — | 发布管理员 | `develop` |
| `hotfix/xxx` | 普通 | `hotfix-xxx/` | Dev | `main` |

`workspace` / `main` / `demand` / `deploy` 互无父节点，各自管理自己的 `.gitignore`。

## 适用范围

| 适合 | 不适合 |
|------|--------|
| 中大型项目（多个模块、多需求并行） | 单文件脚本、一次性工具 |
| 多人 / 多 Agent 协作 | 个人短周期验证性开发 |
| 需要"需求 → 开发 → 验证 → 发布"可追溯 | 只求快速出原型、不留审计 |
| 长期维护、有 CI/CD 与环境区分 | 无部署环节的纯库 |

判断标准：**维护 worktree 的成本 < 上下文隔离带来的收益** 时才用。小于这个阈值时，
普通分支 + PR 更划算——本规范会把三个空容器的维护成本强加给一个本不需要的项目。

> 本仓库（`agent-workspace` 插件源码）**自身不遵循**本规范：它是单仓库的文档 + 脚本项目，
> 用普通 `main` + PR 即可。因此在本仓库跑 `aw.py verify` 会报"不是 workspace 仓库"，这是预期行为。

## 硬约束

1. `workspace` 分支的 `git ls-files` **必须恰好** `.gitignore` + `README.md`。
2. 根 `.gitignore` 用双层防御：`*` → `!*/` → `!.gitignore` `!README.md` → `/*/`。
3. 禁止中间层（`workspaces/code/`）与二级嵌套（`feature-x/code/`）。
4. `status.md` 只有 BA 能改；QA 不 commit；Dev 不改状态。
5. 跨 worktree 引用一律写 `<repo-root>/...` 绝对路径。
6. 一个 worktree 只服务一个需求，合并即回收。
7. 多 BA 同机协作：每个会话必须带稳定的 `AW_AGENT_ID`；**一个 agent 同时只能持有 1 个认领**，
   由 `aw.py claim` 强制（先进 `ALREADY_HOLDING`，不是靠提醒）。
8. 认领是创建 worktree 的唯一入口：禁止手工 `git worktree add` 绕过认领。
9. BA 间消息只走 `bus` 分支的空 commit；**契约/决策才进 `demand`**，不要把对话提交到 demand。
   消息里的路径一律用**仓库相对路径**（`BA/contracts/...`），禁止本机绝对路径。
10. **Planner 不领 feature、不改状态、不派单**：只写 `BA/plan/` 与 `BA/decisions/`；
    决策必须落 ADR，优先级一次只改一个。
11. **身份必须由人指定**：`--agent <name>` 或 `AW_AGENT_ID`，都没有时工具 `exit 2`（`MISSING_AGENT_ID`），
    不自动生成、不猜。名称在同一仓库内唯一且跨会话稳定。
12. 未读消息存在时 `claim next` 拒绝（`UNREAD_MESSAGES`，exit 4）——先读消息（或让 Notifier 读）再认领。
13. 契约有版本：已 ratified 的 `vN.md` 不可改；消费方在 `.feature/manifest.json` 里 pin 版本；
    合并前 `aw.py contract check` 必须通过。
14. `develop` 只通过 PR 合并；`main` 只从 `release` 合并。
15. 命令铁律：`git checkout --orphan` 之后用 `git reset`，**绝不用 `git rm -rf .`**（会删工作区文件）。

## 我该读什么

| 你是 | 先读 | 再读 |
|------|------|------|
| **Planner** | `references/roles/planner.md` | `global/state-machine.md`、`global/messaging.md` |
| **BA** | `references/roles/ba.md` | `global/concurrency.md`、`global/state-machine.md` |
| **Dev** | `references/roles/dev.md` | `global/paths.md` |
| **QA** | `references/roles/qa.md` | `global/state-machine.md`（写入权） |
| **Deploy** | `references/roles/deploy.md` | `lifecycle/release.md` |
| **Explore** | `references/roles/explore.md` | `global/paths.md` |
| 初始化项目 | `references/init/new-project.md` | `global/layout.md` |
| 迁移仓库 | `references/init/migrate-project.md` | — |
| 巡检 / 回收 | `references/lifecycle/audit.md` | `lifecycle/cleanup.md` |
| 发布 | `references/lifecycle/release.md` | `roles/deploy.md` |
| 升级已运行的项目 | `references/lifecycle/upgrade.md` | `aw.py upgrade` |
| BA 之间沟通 | `references/global/messaging.md` | `aw.py msg` |
| 通过 MCP 调用 | `references/global/mcp.md` | 工具名见上表 |
| 接口/契约对齐 | `references/global/contracts.md` | `aw.py contract check` |
| 我是谁 / 没名字 | `references/global/identity.md` | `aw.py agent whoami` |
| 代读消息 | `references/roles/notifier.md` | 只读子 agent |

子 Agent 的 prompt 里应当**直接给出角色文件路径**，不要让它自己猜该读哪一节。

## 路径基准

`<repo-root>` 是 workspace 主 worktree 的绝对路径，任意 worktree 里这样取：

```bash
ROOT="$(git rev-parse --path-format=absolute --git-common-dir | xargs dirname)"
```

- 自己的文件：相对路径即可。
- 别人的文件：`<repo-root>/BA/demands/REQ-xxx/...`（**不是** `BA/...`）。
- 兄弟 worktree 物理可见，但**只可读、不可写**。

## 如果客户端支持 MCP

`scripts/aw_mcp.py` 是 stdio 适配层：**一个 agent 一个进程**，`AW_AGENT_ID` 由启动环境注入，
不需要 `--agent`，也不依赖 session_id。配置见 `references/global/mcp.md`。

> 不同客户端会给工具名加前缀：DSH 是 `mcp__aw__claim_next`，Claude/Cursor 是原名。
> 判断"MCP 是否可用"时按**后缀**匹配，不要精确等于。

| 组 | 工具 |
|----|------|
| 身份 / 名册 | `agent_whoami` `agent_roster` `agent_register` `agent_activate` `agent_deactivate` `agent_publish` `agent_exit` |
| 认领 | `claim_next` `claim_take` `claim_release` `claim_list` `claim_doctor` |
| 消息 | `msg_send` `msg_inbox` `msg_wait` `msg_show` `msg_ack` |
| 门禁 | `contract_check` `verify` `audit` |
| 队列 | `queue_add` `queue_list` `queue_sync` |

返回统一为：

```json
{"ok": true, "exit_code": 0, "stdout": "...", "stderr": "", "agent": "pcA-ba-1"}
```

`0 / 3 / 4` 都是业务正常（成功 / 拒绝 / 未读门禁），只有真正失败才 `isError`。

**能阻塞就不要轮询**：等消息用 `msg_wait`（≤120 秒），不要每 5 秒调一次 `msg_inbox`。

MCP 与 CLI 等价；客户端不支持 MCP 时用 `aw.py` + `AW_AGENT_ID`。

### 使用策略（硬规则）

1. **工具列表里出现以 `agent_whoami` 结尾的工具** → 本会话必须用 MCP，禁止 shell 调 `aw.py`（诊断、安装除外）。
2. **没有** → 先执行安装检查，再退回 CLI，并告诉用户重启客户端：
   ```bash
   aw.py mcp ensure                 # 自动检测已存在的客户端配置
   aw.py mcp install --client claude|cursor|vscode|claude-code [--path ...]
   ```
3. **同一个会话不要混用** MCP 与 CLI 做同一类操作：两者的身份/pid 不同，会让 liveness 和认领记录对不上。安装与诊断是唯一例外。
4. 安装会**备份原配置**，但 MCP 工具**不能热加载**——必须重启客户端才生效。

> “强制”指的是流程强制：没有 MCP 就跑安装；不是指能在当前会话里凭空变出工具。

## 脚本

| 命令 | 作用 | 退出码 |
|------|------|--------|
| `aw.py init <dir>` | 建 workspace 项目（幂等） | 0 / 非 0 |
| `aw.py migrate --main <branch>` | 原地迁移已有仓库 | 0 / 非 0 |
| `aw.py verify` | 校验硬约束（可挂 CI / pre-commit） | 0 通过，1 违规 |
| `aw.py audit` | 只读巡检，输出四段报告 | 0 干净，1 有问题 |
| `aw.py upgrade` | 旧项目升级检查（只读）：补什么/清什么/改什么 | 0 无需动作，1 有待处理 |
| `aw.py msg send/inbox/ack/wait` | BA 间消息（空 commit 走 `bus` 分支；wait 阻塞 ≤120s） | 0 成功，3 排队/超时 |
| `aw.py contract check` | 契约一致性：pin 版本、consumer 缺失、未 ack | 0 通过，1 有问题 |
| `aw.py agent bind/roster/exit` | 绑定终端、维护名册、退出会话（防漂移） | 0 成功，2/3 失败 |
| `aw.py next-req` | 计算下一个可用 REQ 编号 | 0 |
| `aw.py queue add/list/sync` | 维护待认领队列 | 0 |
| `aw.py claim whoami/next/take/release/list/doctor` | 任务认领（**WIP=1，工具强制**） | 0 成功，3 拒绝 |

Windows 用 `aw.cmd` / `.\aw.ps1`（自动选 `py` 或 `python`）；中文输出、`/c/...` 路径、跨盘符、长路径等细节见
`references/global/platform-notes.md`。

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
| `references/global/concurrency.md` | 多 BA：身份、WIP=1 认领、锁、doctor |
| `references/global/platform-notes.md` | Windows / macOS / Linux / WSL 差异 |
| `references/global/messaging.md` | BA 间消息：bus 分支、格式、寻址、ack |
| `references/global/mcp.md` | MCP stdio 适配层：配置、工具、返回格式 |
| `references/global/contracts.md` | 契约版本、消费方 pin、检查规则 |
| `references/global/identity.md` | agent 名称的优先级、强制人工指定 |
| `references/roles/*.md` | 六个角色的完整工作流 |
| `references/init/*.md` | 新建 / 迁移 |
| `references/lifecycle/*.md` | 巡检 / 回收 / 发布 |
| `assets/templates/*.tpl` | 根容器、需求、验收、状态、registry、feature 产物 |
| `scripts/aw.py` | init / migrate / verify / audit / next-req |
