# agent-workspace-single

单机版的轻量 Agent 协作层：**传统代码仓库 + 独立文档仓库 + 本地 `.aw/`**。

它不要求把现有项目改造成 workspace 布局，也不创建 `demand` / `bus` / `deploy` 孤立分支。

- 代码仓库保持原样（通常 `main` / `develop` / `feature/*`）；
- 需求、验收、状态继续放在现有文档仓库；
- feature worktree 放在独立的 `worktrees/` 目录；
- 认领、WIP、session 放在本地 `.aw/`，不提交到任何仓库。

## 状态

MVP 已实现：`scripts/aw_single.py`。

MQTT 依赖已 vendor 到 `vendor/paho/`（paho-mqtt 2.2.0），不需要 `pip install`。

## MQTT 配置

MQTT 默认关闭。需要连接时，在 `.aw/config.json` 写：

```json
{
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

或用 `init` 参数：

```bash
aw_single.py init --root . \
  --code-root D:/proj/app --docs-root D:/proj/docs \
  --base-branch develop \
  --mqtt-host broker.example.com --mqtt-port 8883 \
  --mqtt-username aw --mqtt-ca D:/certs/ca.pem
```

密码通过 `AW_MQTT_PASSWORD` 提供，不写进配置。MQTT 客户端尚未接入 watcher，当前只完成配置契约。

```bash
python scripts/aw_single.py init --root . \
  --code-root D:/proj/app --docs-root D:/proj/docs --base-branch develop

python scripts/aw_single.py whoami
python scripts/aw_single.py queue add REQ-001 --title "登录"
python scripts/aw_single.py claim next
python scripts/aw_single.py claim list
python scripts/aw_single.py claim release REQ-001
python scripts/aw_single.py claim doctor
python scripts/aw_single.py project check
python scripts/aw_single.py bus log

python scripts/aw_single.py msg send --to ba-1 --type question --body "ping"
python scripts/aw_single.py msg inbox
python scripts/aw_single.py msg wait --timeout 120
python scripts/aw_single.py watch --ensure --exec "bash start-agent.sh"
```

当前覆盖：本地 claim、WIP=1、feature worktree、queue、doctor、本地消息、wake。
不解析 docs 状态、不接 CI、不做跨机通信。

## 目录

```text
<local-root>/
├── app/                 # 现有代码仓库
├── docs/                # 现有文档仓库
├── worktrees/           # feature worktree
└── .aw/                 # 本地协调层（不提交）
    ├── config.json
    ├── claims/
    ├── sessions/
    └── queue.json
```

## 角色

| 角色 | 文档 | 说明 |
|------|------|------|
| Planner（可选） | [planner.md](references/roles/planner.md) | 优先级、跨 BA 边界、ADR |
| BA | [ba.md](references/roles/ba.md) | 需求、验收、状态、claim、派单 |
| Dev | [dev.md](references/roles/dev.md) | 无状态执行者，worktree 内实现 |
| QA | [qa.md](references/roles/qa.md) | 只读验证，报告交 BA |

暂不设 Deploy / Explore 常驻角色。

## 只做什么

- 单机多 agent；
- WIP=1；
- feature worktree 隔离；
- 认领、队列、session；
- 读 docs 仓库的需求/验收，写回状态由 BA 负责。

## 不做什么

- 不改代码仓库的分支模型；
- 不建 `demand` / `bus` / `deploy` 分支；
- 不做跨机 claim；
- 不做完整 audit / verify / upgrade；
- 不替代现有 CI/CD 和消息系统；
- 不复制 workspace 版的 `aw.py`。

## 文档

- [单机 profile](references/single-profile.md)
- [工作流](references/workflow.md)
- [目录布局](references/layout.md)
- [Setup / 环境变量](references/setup.md)
- [omp 唤醒插件](references/omp.md)
- [DSH 唤醒插件](references/dsh.md)
- [MQTT + bus 协议](references/mqtt-bus-protocol.md)
