# MCP 适配层（stdio）

`aw_mcp.py` 把 `aw.py` 暴露成 MCP 工具，**不重写任何逻辑**：
每个工具调用都是 `aw.py` 子进程，CLI 仍是唯一事实源。

## 1. 形态

```text
agent 客户端 ──stdio──► aw_mcp.py（每个 agent 一个进程）
                              │ 子进程
                              ▼
                           aw.py
```

- **一个 agent 一个终端 / 一个进程**：`AW_AGENT_ID` 由启动环境注入；
- 服务器进程启动时：
  - `AW_AGENT_PID = 本进程 pid`（liveness 用这个）
  - `AW_SESSION_ID = proc-<pid>`（一个进程 = 一个会话）
- 因此**不需要 `--agent` 参数，也不依赖 session_id 关联**。

## 1.1 安装（自动写配置）

> `mcp install` 直接支持 claude / cursor / vscode / claude-code。
> omp / mcode / DSH 的格式不同，见 §5.2。

```bash
aw.py mcp status                  # 检测各客户端是否已有 aw 条目
aw.py mcp install --client claude # 写 Claude Desktop 配置
aw.py mcp install --client cursor --path ~/.cursor/mcp.json
aw.py mcp install --client vscode --path .vscode/mcp.json
aw.py mcp ensure                  # 只对已存在的配置做安装
aw.py mcp print                   # 打印通用 JSON（手工粘贴）
```

行为：

- 写配置前**备份**为 `<name>.bak-<时间戳>`；
- 条目指向 `.aw/mcp/aw-mcp.cmd`（Windows）或 `.aw/mcp/aw-mcp.sh`（POSIX）包装器，
  包装器负责 `cd` 到仓库根，避免客户端不支持 `cwd`；
- 已安装且内容一致时输出 `ALREADY INSTALLED`，不重复写；
- `--dry-run` 只打印不改；
- **装完必须重启客户端**，MCP 工具才会出现在工具列表里。

## 2. 客户端配置

通用 stdio 配置：

```json
{
  "mcpServers": {
    "aw": {
      "command": "python",
      "args": ["<skill-path>/scripts/aw_mcp.py"],
      "cwd": "<repo-root>",
      "env": { "AW_AGENT_ID": "pcA-ba-1" }
    }
  }
}
```

- `cwd` 必须是 workspace 根（或任一 worktree 目录，`aw.py` 会自己解析根）；
- 每个 agent 用同一份配置，只改 `AW_AGENT_ID`；
- 没有 `AW_AGENT_ID` 时服务照常启动，但每次工具调用返回 `MISSING_AGENT_ID`。

## 3. 工具

| 工具 | 作用 |
|------|------|
| `agent_whoami` / `agent_roster` | 身份与名册 |
| `agent_register` / `agent_activate` / `agent_deactivate` | 注册与启停 |
| `agent_publish` | 把名册提交并推送到 demand，其他机器可见 |
| `claim_next` / `claim_take` / `claim_release` / `claim_list` / `claim_doctor` | 认领 |
| `msg_send` / `msg_inbox` / `msg_show` / `msg_ack` | 消息 |
| `msg_wait` | 阻塞等新消息（≤120 秒，默认不消费） |
| `contract_check` | 契约门禁 |
| `verify` / `audit` | 自检 |
| `queue_add` / `queue_list` / `queue_sync` | 队列 |

参数与 CLI 一一对应；schema 里有枚举与必填项，agent 不需要读源码。

## 4. 返回格式

每个工具返回一段 JSON 文本：

```json
{
  "ok": true,
  "exit_code": 0,
  "stdout": "...",
  "stderr": "...",
  "agent": "pcA-ba-1"
}
```

- `exit_code` 保留原语义（0 成功、3 业务拒绝、4 未读门禁）；
- `isError` 只在真正的失败时为 true（0/3/4 都算正常业务返回）；
- `ALREADY_HOLDING`、`UNREAD_MESSAGES` 都在 `stdout` 首行。

## 4.1 注册流程（推荐）

名册在仓库里（`BA/plan/agents.json`），所以 agent 之间能互相看见：

```text
① Planner 调 agent_register × 8
② Planner 调 agent_publish        → commit + push demand
③ 其他机器 git pull --rebase      → 拉到名册
④ 每个 agent 调 agent_roster      → 看到全部人和在线状态
⑤ 离岗调 agent_deactivate；收工调 agent_exit
```

- `agent_roster` 返回 JSON：`id / role / status / host / session_alive`；
- 没有 publish，名册只在本机，其他机器“不知道有谁”；
- 没有 pull，本机看到的是旧名册——**发送前先 pull**。

## 4.2 等待而不是轮询

> `msg_send` / `msg_ack` 只对 BA / Planner 开放；子 agent 调用会被拒绝。
> 子 agent 进程应设置 `AW_ROLE=dev`（或 roster 里 role=dev），不要复用 BA 的身份去发消息。

`msg_wait` 在服务端阻塞，最多 120 秒：

```json
{"tool":"msg_wait","arguments":{"timeout":120,"interval":5,"thread":"a1b2"}}
```

- 命中：返回 `{"found":true,"count":N,"messages":[...]}`，退出码 0；
- 超时：返回 `{"found":false}`，退出码 3（`isError=false`）；
- **默认不消费**：消息仍是未读，BA 自己决定何时 `msg_inbox` 或加 `consume:true`；
- 过滤器：`thread` / `contract` / `type` / `sender`。

这样一次工具调用就能等两分钟，替代 24 次 5 秒轮询。

## 5. 与 CLI 的关系

| 场景 | 用哪个 |
|------|--------|
| agent 客户端支持 MCP | `aw_mcp.py` |
| CI、脚本、人 | `aw.py` |
| 客户端不支持 MCP | `aw.py` + `AW_AGENT_ID` |

两者行为必须一致：改逻辑只改 `aw.py`，MCP 只做参数映射。

## 5.1 Linux / macOS

### 配置位置

| 客户端 | 路径 |
|--------|------|
| Claude Desktop (macOS) | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Desktop (Linux) | `~/.config/Claude/claude_desktop_config.json` |
| Cursor | `~/.cursor/mcp.json` |
| VS Code | `<repo>/.vscode/mcp.json` |
| Claude Code | `<repo>/.mcp.json` |

### 配置

```json
{
  "mcpServers": {
    "aw": {
      "command": "python3",
      "args": ["/home/me/skills/agent-workspace/scripts/aw_mcp.py"],
      "cwd": "/home/me/proj/my-project"
    }
  }
}
```

### 身份

```bash
export AW_AGENT_ID=pcA-ba-1
omp
# 或一次性：
AW_AGENT_ID=pcA-ba-1 omp
```

### 客户端不支持 cwd 时

```sh
#!/usr/bin/env sh
# ~/bin/aw-mcp.sh
set -eu
cd "${AW_REPO_ROOT:-$HOME/proj/my-project}"
exec python3 "$HOME/skills/agent-workspace/scripts/aw_mcp.py"
```

```bash
chmod +x ~/bin/aw-mcp.sh
```

配置里 `"command": "/home/me/bin/aw-mcp.sh"`，`args` 留空。

### POSIX 启动器

CLI 侧有 `scripts/aw`（sh），等价于 Windows 的 `aw.cmd`：

```bash
./scripts/aw verify
# 或加入 PATH 后
aw verify
```

> `aw.py` 在 POSIX 上用 `fcntl.flock` 做锁，Windows 用 `msvcrt.locking`；行为一致。

## 5.2 客户端差异（omp / mcode / DSH）

同一个 `aw_mcp.py`，三个客户端的配置格式和工具命名都不同。

| 客户端 | 配置文件 | 父键 | 工具名 | 环境变量 |
|--------|----------|------|--------|----------|
| omp | `.omp/mcp.json` 或 `~/.omp/agent/mcp.json` | `mcpServers` | 原名 | 大概率继承终端 |
| mcode | 项目根 `.mcp.json` 或 `~/.minimax/mcp.json` | `mcpServers` | 原名 | 源码里是显式构造 |
| DSH | `~/.dsh/profiles/<profile>/cordis.patch.yml` | YAML 列表 | `mcp__<server>__<tool>` | 必须显式转发 |

### omp

```json
{
  "$schema": "https://raw.githubusercontent.com/can1357/oh-my-pi/main/packages/coding-agent/src/config/mcp-schema.json",
  "mcpServers": {
    "aw": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/aw_mcp.py"],
      "cwd": "/path/to/repo",
      "enabled": true,
      "timeout": 180000
    }
  }
}
```

- 支持 `cwd` 与 `timeout`，不需要包装器；
- `timeout` 是给 `msg_wait` 留的余量（若客户端按秒计，写 `180`）；
- 不要在配置里写 `AW_AGENT_ID`，它必须来自终端。

### mcode

项目根放 `.mcp.json`：

```json
{
  "mcpServers": {
    "aw": {
      "type": "stdio",
      "enabled": true,
      "command": "python",
      "args": ["/path/to/aw_mcp.py"],
      "cwd": "./"
    }
  }
}
```

两个限制（源码确认）：

1. `cwd` 只接受 `./` 或 `${PLUGIN_ROOT}` 形式，不能写绝对路径；
2. `env` 是显式构造的，没有合并 `process.env` 的迹象——**先用 `agent_whoami` 验证**。

如果返回 `MISSING_AGENT_ID`：改用 CLI，或给每个 agent 独立的配置目录并在 `env` 里写死名字。
不要在一份共享 `.mcp.json` 里写死 `AW_AGENT_ID`，否则 8 个 agent 会变成同一个。

### DSH

追加到 `~/.dsh/profiles/<profile>/cordis.patch.yml`：

```yaml
- id: mcp-aw
  name: "@deepseek-ai/dsh-mcp-client"
  config:
    serverName: aw
    transport: stdio
    command: python
    args:
      - /path/to/aw_mcp.py
    cwd: /path/to/repo
    env:
      AW_AGENT_ID: !!js process.env.AW_AGENT_ID
    toolCallTimeoutMs: 180000
    failOnStartupError: false
```

- DSH 会清洗环境变量，必须用 `!!js process.env.AW_AGENT_ID` 转发；
- 工具名带前缀：`mcp__aw__claim_next`、`mcp__aw__msg_wait`；
- 默认调用超时 60 秒，`msg_wait` 会超时，调大到 180000。

### 共同验证

```text
1. 调 agent_whoami（DSH: mcp__aw__agent_whoami）
2. stdout 里有 agent_id，exit_code = 0
3. 调 agent_roster
4. 调 msg_wait timeout=10
```

| 现象 | 原因 |
|------|------|
| MISSING_AGENT_ID | 环境没传进来 |
| not a git repository | cwd 不对 |
| msg_wait 60 秒断 | 客户端调用超时 |
| 工具列表里没有 | 服务没起 / 配置没加载 |

## 6. 限制

- 单次工具调用超时 180 秒（长任务请拆小）；
- 不提供流式输出；
- stdout 只能输出 JSON-RPC，日志一律走 stderr；
- 服务器不缓存身份：每次调用都从环境变量读取，防止中途被改。
