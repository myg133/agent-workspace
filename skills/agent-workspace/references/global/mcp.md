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
| `claim_next` / `claim_take` / `claim_release` / `claim_list` / `claim_doctor` | 认领 |
| `msg_send` / `msg_inbox` / `msg_show` / `msg_ack` | 消息 |
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

## 5. 与 CLI 的关系

| 场景 | 用哪个 |
|------|--------|
| agent 客户端支持 MCP | `aw_mcp.py` |
| CI、脚本、人 | `aw.py` |
| 客户端不支持 MCP | `aw.py` + `AW_AGENT_ID` |

两者行为必须一致：改逻辑只改 `aw.py`，MCP 只做参数映射。

## 6. 限制

- 单次工具调用超时 180 秒（长任务请拆小）；
- 不提供流式输出；
- stdout 只能输出 JSON-RPC，日志一律走 stderr；
- 服务器不缓存身份：每次调用都从环境变量读取，防止中途被改。
