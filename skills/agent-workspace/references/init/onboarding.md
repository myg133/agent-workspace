# 首次接入（onboarding）

第一次在一个项目上使用本 skill 时，**不要直接 `init`**。先判断模式，再动手。

## 0. 先跑一次检查

```bash
aw.py onboard --json
```

MCP 侧：`onboard {}`。

输出会告诉你：

| 字段 | 含义 |
|------|------|
| `initialized` | 是否已经是 workspace 仓库 |
| `mode` | `local`（无 origin）或 `remote` |
| `team` | `solo`（无 Planner）或 `team` |
| `identity` | 本终端有没有 `AW_AGENT_ID` |
| `roster` | active / total / Planner |
| `hook` | pre-push 是否安装 |
| `questions` | 还需要问用户的问题 |
| `next` | 建议执行的命令 |

**只问 `questions` 里缺的，不要重复问已经确定的。**

## 1. 六个问题（按需）

### Q1 新项目还是迁移？

| 情况 | 动作 |
|------|------|
| 空目录 / 只有 README | `aw.py init <dir> --name ...` |
| 已有仓库、已有分支 | `aw.py migrate --main <branch>`，先读 `init/migrate-project.md` |

### Q2 本地还是远程？

| 模式 | 适用 | 后果 |
|------|------|------|
| `local` | 单机、单人、试跑 | 没有 origin，bus 只在本地，不能跨机 |
| `remote` | 多机 / 多人 / 需要备份 | 有 origin，bus/demand 可 push，其他机器可加入 |

remote 需要：仓库 URL、是否立即 push（`--push` 是外部可见动作，先确认）。

### Q3 单人还是团队？

| 模式 | 角色 | 注册 |
|------|------|------|
| `solo` | 只有一个 BA（可兼规划） | BA 自注册直接 `active` |
| `team` | Planner + 多个 BA | 第一个 Planner 用 `agent bootstrap`，BA 自注册后 `pending`，Planner 激活 |

只有一个人时，**不要为了“规范”硬加 Planner**。

### Q4 BA / Agent 叫什么？

命名建议：

```text
<机器>-<角色>-<序号>      pcA-ba-1 / pcA-planner / pcB-ba-2
```

之后：

```text
agent_register {"name": "pcA-ba-1", "role": "ba"}
```

- solo：直接 active；
- team：pending，等 Planner `agent_activate`；
- 需要令牌就加 `--issue-token`，token 只交给该 agent。

### Q5 主分支叫什么？

`init` 默认 `main` / `develop`。已有仓库如果是 `master`，用 `migrate --main master`，不要硬改。

### Q6 现在装 hook 吗？

建议装：

```bash
aw.py hook install
```

不装也能跑，但手工 commit 的 bus 消息不会被校验。

### Q7 watcher 和主动通知

MCP 主动通知**默认开启**，不需要设 `AW_MCP_NOTIFY`；但需要同仓库有 watcher 在写
`.aw/wake/`：

```bash
aw.py watch --ensure --interval 5 --wake-dir .aw/wake
```

- 第一个 agent 调一次即可，后续 agent 得到 `WATCH_RUNNING`；
- 不想让 MCP 发通知：`AW_MCP_NOTIFY=0` 或 `--no-notify`；
- 宿主是否把通知变成一轮对话由客户端决定；不支持时用 `msg_inbox` / `msg_wait`。

## 2. 推荐流程

### 新项目（solo、本地）

```bash
aw.py init my-project --name "My Project"
cd my-project
aw.py hook install
aw.py agent register pcA-ba-1 --role ba
aw.py watch --ensure --interval 5 --wake-dir .aw/wake
aw.py doctor
```

### 新项目（team、远程）

```bash
aw.py init my-project --name "My Project" --remote git@host:org/my-project.git --push
cd BA
aw.py agent bootstrap pcA-planner --role planner
aw.py agent publish
# 各 BA 终端：
#   agent register <name> --role ba
#   Planner: agent_activate <name>
#   agent publish
```

### 已有仓库

```bash
aw.py migrate --main master
aw.py hook install
aw.py doctor
# 旧 .feature/ → feature-meta/（每个 feature worktree 一次）
git mv .feature feature-meta && git commit -m "[Dev] 迁移元数据目录"
```

## 3. 不要做的

| 反模式 | 原因 |
|--------|------|
| 目录非空还强行 init | 会拒绝或覆盖，先 migrate |
| 单机单人却上 Planner + 8 个 BA | 协调成本大于收益 |
| 本地模式却指望跨机 | 没有 origin，bus 出不去 |
| 不命名 agent 就开始派单 | 认领/消息没有 owner |
| 不装 hook 就允许手写 bus commit | 16.8% 绕过就是这么来的 |
