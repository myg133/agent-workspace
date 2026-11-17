# 单机 profile

## 1. 目标

在不改造现有代码仓库的前提下，提供：

- 认领与 WIP=1；
- feature worktree 隔离；
- 单机 session 记录；
- docs 仓库的只读需求输入与 BA 的状态回写。

## 2. 目录模型

```text
<local-root>/
├── app/                 # git 仓库：代码
├── docs/                # git 仓库：需求/验收/状态
├── worktrees/           # git worktree：feature/REQ-xxx
└── .aw/                 # 本地状态，不提交
    ├── config.json
    ├── claims/
    ├── sessions/
    ├── queue.json
    └── locks/
```

`local-root` 不是 git 仓库；它只是本地工作目录。

## 3. 配置

`.aw/config.json`：

```json
{
  "profile": "single",
  "version": 1,
  "code_root": "D:/proj/app",
  "docs_root": "D:/proj/docs",
  "base_branch": "develop",
  "worktree_root": "D:/proj/worktrees",
  "branch_prefix": "feature/",
  "demand_dir": "demands",
  "project_id": "p-9f8e7d6c5b4a",
  "project_alias": "github.com/myg133/agent-workspace-single",
  "project_source": "git:origin",
  "transport": {
    "mode": "auto",
    "audit_bus": true,
    "bus": {"enabled": true, "branch": "bus", "push": true, "poll_seconds": 30}
  },
  "mqtt": {
    "enabled": true,
    "host": "broker.example.com",
    "port": 8883,
    "tls": true,
    "ca_file": "",
    "username": "",
    "password_env": "AW_MQTT_PASSWORD",
    "client_id": "",
    "keepalive": 30,
    "topic_prefix": "aw/v1"
  }
}
```

MQTT 字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| `enabled` | 是 | `false` = 仅本地，不连 broker |
| `host` / `port` | 是 | broker 地址；TLS 常用 8883 |
| `tls` | 是 | 生产必须 `true` |
| `ca_file` | 否 | 自签 CA 的路径；为空用系统 CA |
| `username` | 否 | broker 用户名 |
| `password_env` | 否 | 密码环境变量名，默认 `AW_MQTT_PASSWORD` |
| `client_id` | 否 | 为空时由 watcher 生成；同一 broker 必须唯一 |
| `topic_prefix` | 否 | 默认 `aw/v1` |

字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| `code_root` | 是 | 代码仓库根，必须是一个 git worktree |
| `docs_root` | 是 | 文档仓库根；只读对 Dev/QA，BA 可写 |
| `base_branch` | 是 | feature 分支的起点，如 `develop` |
| `worktree_root` | 是 | feature worktree 的父目录；不能位于代码仓库内部 |
| `branch_prefix` | 否 | 默认 `feature/` |
| `demand_dir` | 否 | docs 下的需求目录，默认 `demands` |

## 4. 身份与会话

- `--agent` / `AW_AGENT_ID` 决定 WIP 归属；
- `AW_SESSION_ID` 可选，仅用于审计；
- 没有真实 session 时写 `proc-<pid>` 并标记 `generated`；
- 不实现 workspace 版的 map/by-session 反向映射。

`.aw/sessions/<agent>.json`：

```json
{
  "agent_id": "ba-1",
  "session_id": "session-...",
  "session_source": "AW_SESSION_ID",
  "started_at": "2026-11-16T10:00:00+08:00",
  "last_seen": "2026-11-16T10:00:00+08:00"
}
```

## 5. Claim

`.aw/claims/<REQ>.json`：

```json
{
  "req": "REQ-001",
  "agent_id": "ba-1",
  "session_id": "session-...",
  "branch": "feature/REQ-001",
  "worktree": "D:/proj/worktrees/REQ-001",
  "base_branch": "develop",
  "base_sha": "<sha>",
  "state": "active",
  "claimed_at": "2026-11-16T10:00:00+08:00"
}
```

`state` 首版只使用：

- `active`：持有中；
- `released`：已释放（归档后不再存在）。

`blocked` / `review` 首版不实现，避免再出现“文档有状态、CLI 没有入口”的问题。

## 6. Worktree 规则

创建：

```bash
git -C <code_root> worktree add -b feature/REQ-001 \
  <worktree_root>/REQ-001 <base_branch>
```

规则：

- worktree 必须位于 `worktree_root` 下，不能嵌套在 `code_root` 内；
- 分支不存在时创建，存在时拒绝；
- worktree 路径已存在且不是该分支的 worktree 时拒绝；
- `claim release` 默认只删 claim，不删 worktree；
- `--remove-worktree` 时才删除，且要求工作区干净。

## 7. Docs 契约

docs 仓库负责：

```text
<docs_root>/<demand_dir>/REQ-001/
├── demand.md
├── acceptance.md
├── status.md
└── test-cases/
```

写入权：

| 文件 | 写入者 |
|------|--------|
| `demand.md` / `acceptance.md` / `status.md` | BA |
| `test-cases/` | QA 产出，BA 提交 |
| 其他 | 只读 |

Dev/QA 只读 docs，不直接改状态。

feature worktree 的 `feature-meta/manifest.json` 增加：

```json
{
  "docs_repo": "product-docs",
  "demand_path": "demands/REQ-001/",
  "demand_commit": "<sha>"
}
```

这是跨仓库引用，不用本机绝对路径。

## 8. Queue

首版使用本地 `.aw/queue.json`：

```json
[
  {"req": "REQ-001", "title": "登录", "added_at": "2026-11-16T10:00:00+08:00"}
]
```

`queue sync` 暂不从 docs 扫描；BA 手工 `queue add`，避免解析另一个仓库的状态格式。

## 9. 命令契约

```bash
aw_single.py init --config <path>
aw_single.py whoami
aw_single.py queue add REQ-001 --title "登录"
aw_single.py queue list
aw_single.py claim next
aw_single.py claim take REQ-001
aw_single.py claim list
aw_single.py claim release REQ-001 [--remove-worktree]
aw_single.py claim doctor

aw_single.py msg send --to ba-1 --type question --body "..."
aw_single.py msg inbox [--all] [--peek] [--json]
aw_single.py msg ack <id>
aw_single.py msg wait [--timeout 120] [--consume]

aw_single.py watch [--once] [--ensure] [--status] [--stop] \
  [--interval 5] [--exec "<command>"] [--json]

aw_single.py presence [--json]
aw_single.py project id
aw_single.py project alias
aw_single.py project check
aw_single.py bus log
aw_single.py bus show <id>
```

### 9.1 本地消息

- 存储：`.aw/inbox/<agent>/<id>.json`；
- 已读：`.aw/msg-read/<agent>.json`；
- 唤醒：`.aw/wake/<agent>.json`（只含摘要，不含正文）；
- 无网络、无 git、无共享锁文件（每消息一个文件）；
- `msg send` 只负责写收件人 inbox；唤醒由 `watch` 完成。

### 9.2 无人值守

```bash
aw_single.py watch --ensure --exec "bash start-agent.sh"
```

`--exec` 会带：

```text
AW_WAKE_AGENT
AW_WAKE_MSG_ID
AW_WAKE_TYPE
AW_WAKE_FROM
```

如果宿主（DSH/omp）能读 `.aw/wake/<agent>.json`，也可以不用 `--exec`，
由宿主插件把唤醒转成一次会话。omp 安装见 `references/omp.md`。

退出码：

| 码 | 含义 |
|----|------|
| 0 | 成功 |
| 2 | 配置/参数错误 |
| 3 | 业务状态（已持有/已被占/无队列/未认领） |
| 1 | 未预期错误 |

## 10. 不做的事

- 不建 `demand` / `bus` / `deploy` 分支；
- 不做跨机 claim；
- 不做 bus 消息；
- 不做 map / by-session；
- 不做 audit/verify/upgrade；
- 不接管 CI/CD。
