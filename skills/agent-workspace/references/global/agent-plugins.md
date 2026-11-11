# 唤醒插件（omp / pi / DSH）

watcher 只写 wake 文件；**把“有新消息”变成“模型起一轮”**需要客户端插件。

本仓库提供两个：

| 客户端 | 插件 | 机制 |
|--------|------|------|
| omp / pi | `agents/pi/agent/extension/aw-bus.ts` | 监听 MCP `notifications/message`，转成一次用户消息 |
| DSH | `agents/dsh/aw-wake/` | 轮询 `.aw/wake/<agent>.json`，调用 `agent.followup()` |

两者都**只负责叫醒**，不回复、不 ack、不改认领。

## 1. 前置条件

1. 同仓库有 watcher 在跑：

   ```bash
   aw.py watch --ensure --interval 5 --wake-dir .aw/wake
   aw.py watch --status
   ```

2. 一个 agent 一个进程 / 终端；`AW_AGENT_ID` 指向当前 agent。
3. omp / pi 还需要配置 MCP `aw`（见 `references/global/mcp.md`）。
4. DSH 的仓库由会话 cwd 自动发现（向上最多 6 层找 `.aw/`）；`repoRoot` / `repoRoots` 可选，只用于限定范围，不是必填。

## 2. omp / pi

### 2.1 安装

把本仓库的 `agents/pi/agent/extension/aw-bus.ts` 复制到 omp 扩展目录：

**Windows**

```powershell
New-Item -ItemType Directory "$env:USERPROFILE\.omp\agent\extensions" -Force
Copy-Item agents\pi\agent\extension\aw-bus.ts "$env:USERPROFILE\.omp\agent\extensions\aw-bus.ts"
```

**macOS / Linux**

```bash
mkdir -p ~/.omp/agent/extensions
cp agents/pi/agent/extension/aw-bus.ts ~/.omp/agent/extensions/aw-bus.ts
```

重启 omp。

### 2.2 日志

默认：

- Windows：`%USERPROFILE%\.omp\logs\aw-bus-bridge.log`
- macOS / Linux：`~/.omp/logs/aw-bus-bridge.log`

可用环境变量 `AW_BUS_LOG` 改路径。

### 2.3 验证

```powershell
Get-Content "$env:USERPROFILE\.omp\logs\aw-bus-bridge.log" -Tail 20
```

应看到：

```text
... bridge loaded pid=...
... recv {"id":"...","from":"...","type":"question",...}
... steer <id>
```

然后从另一个 agent 发消息：

```powershell
AW_AGENT_ID=pcA-ba-1 aw.py msg send --to pcA-ba-2 --type question --body "ping"
```

pcA-ba-2 的 omp 会话应被插入一条 `[bus ...]` 用户消息。

### 2.4 注意

- omp 的 MCP 配置里必须有 `AW_AGENT_ID`，或至少第一次 `tools/call` 带 `agent_id`；
  通知线程只绑定一次身份；
- 共享 `.mcp.json` 不要写死具体 agent 名字；
- 如果日志只有 `bridge loaded` 没有 `recv`，检查 MCP 是否发出了
  `notifications/message`（`aw_mcp.py` 默认开启）。

## 3. DSH

DSH 插件**不需要 MCP 通知**，直接读 wake 文件。

### 3.1 安装

把 `agents/dsh/aw-wake` 复制到 profile 的 plugins 目录：

**Windows**

```powershell
$profile = "$env:USERPROFILE\.dsh\profiles\web"
New-Item -ItemType Directory "$profile\plugins" -Force
Copy-Item -Recurse agents\dsh\aw-wake "$profile\plugins\aw-wake"
dsh plugin --profile web add ./plugins/aw-wake
```

**macOS / Linux**

```bash
mkdir -p ~/.dsh/profiles/web/plugins
cp -r agents/dsh/aw-wake ~/.dsh/profiles/web/plugins/aw-wake
dsh plugin --profile web add ./plugins/aw-wake
```

`dsh plugin` 只是把参数转发给 profile 里的 pnpm；它会把本地包加入依赖，
并读取包里的 `dsh.bundle.patch`。

### 3.2 启动环境与仓库发现

**不需要先设 `AW_REPO_ROOT`，`repoRoot` 可省略。** 插件从每个活跃会话的 cwd 自动发现仓库：
向上最多 6 层查找 `.aw/` 目录，命中即仓库根。因此：

- 会话开在 `<repo>/code` 这类子目录，也能归到 `<repo>` 根；
- 一台 DSH 可以同时服务多个 workspace，**不需要每个仓库起一个实例**；
- `repoRoot` / `repoRoots` 只用于**限定监听范围**，不是必填。

插件配置（模板见 `agents/dsh/aw-wake/cordis.patch.yml`）：

```yaml
# repoRoot / repoRoots 可省略；省略 = 按会话 cwd 自动发现
# repoRoot: D:/proj/my-project
# repoRoots:
#   - D:/proj/a
#   - D:/proj/b

# 单 agent：填 agentId
# agentId: pcA-ba-1
# 多 agent：不填 agentId（或填 "*"），可选 agents 白名单
# agents: [pcA-ba-1, pcA-ba-2]
```

- `repoRoot`：固定一个仓库（单仓库部署时用）；
- `repoRoots`：数组，限定多个仓库；和 `repoRoot` 可同时出现，合并成监听范围；
- 不写 `repoRoot` / `repoRoots`：自动发现，适合一台 DSH 服务多个仓库；
- `agentId` 可选：填了是 **single** 模式；不填 / `*` 是 **multi** 模式，
  监听 `.aw/wake/*.json` 并按每条消息自带的 `agent` 字段路由；
- `agents` 可选白名单，限制 multi 模式只处理列出的收件人；
- 命令行 / 服务启动可用 `AW_REPO_ROOT` 注入 `repoRoot`；它仍可选，等价于在配置里写 `repoRoot`；
- 改完重启 DSH。

> **桌面版 DSH**：从开始菜单启动通常拿不到 shell 环境变量。
> 桌面用户建议**不写 `repoRoot`**，让插件自动发现；或在部署副本里直接写死 `repoRoot`。
> `env` 模板适合命令行 / 服务方式启动。

### 3.2.1 会话解析顺序

按 `(repo, agent)` 解析，绝不广播：

1. `<repo>/.aw/sessions/<agent>.map.json` 通过形状校验，且 TTL 内只有一个 session id → `map`
2. legacy `<repo>/.aw/sessions/<agent>.json` 且 `session_authoritative === true` → `sessions-file`
3. 配置里的 `sessionId`（pin）→ `config`
4. **single** 模式（写了 `agentId`）：cwd 唯一命中该仓库内一个活跃会话 → `cwd-unique`
5. **multi** 模式 + `agents` 白名单只有一项：允许一次 `cwd-bootstrap`（首次还没有 map 时）
6. 其余一律拒绝并 warn

**仓库归属来自会话 cwd，不是来自配置。** `repoRoot` / `repoRoots` 只裁剪候选范围。

### 3.2.2 map 的形状校验与陈旧提示

消费方读 `.aw/sessions/<agent>.map.json` 前**必须**先做形状校验，任一不满足即拒绝并按原因记录：

| 校验 | 失败 reason |
|------|-------------|
| JSON 可解析、字段类型正确、`map_version` 存在 | `map-invalid` |
| `map_version == 2` | `map-version` |
| `session_authoritative === true` | `map-not-authoritative` |
| `agent_id` 与文件名 `<agent>` 一致 | `map-agent-mismatch` |
| `session_id` 非空且不以 `proc-` 开头 | `map-no-session` |
| `host` 非空 | `map-no-host` |

**手写 map 的问题**：没有 `aw.py` 的 60 秒节流，也没有后续刷新；形状即使正确，也可能很快变陈旧。
map 只能由 CLI 的 `agent whoami` / `claim` 写；MCP 调用被 `AW_FROM_MCP` 挡住，写不了 map。
这是设计，不是缺陷。

**陈旧策略**：不设硬 TTL。`updated_at` 超过 24 小时只在 debug 写 `stale_hours` 并 warn，**不拒绝**。
真实陈旧由 `map-offline`（目标会话不存在）和 session id 变化覆盖；硬 TTL 会误伤安静会话。

> **当前实现差异（以 `index.js` 为准）**：`mapDecision` 目前只检查
> `session_authoritative === false`、`freshSessions` 数量和 `session_id`；
> 上表的 `map-invalid` / `map-version` / `map-agent-mismatch` / `map-no-session` /
> `map-no-host`，以及 debug 的 `age_minutes` / `stale_hours`，尚未落地。
> 在补齐前，这些 reason 不会出现在 `routes`；文档保留 ADR v6 契约，交接时不要另立规则。

### 3.3 验证

```powershell
Get-Content .aw\aw-wake-debug.json -Tail 80
```

`aw-wake-debug.json` 现在包含：

- `repo`：该 debug 文件对应的仓库根；
- `config`：`mode` / `agentId` / `agents` / `repoRoots` / `wakeAll` /
  `sessionId` / `pollMs` / `minIntervalMs` / `ttlMinutes`；
- `map`：**按 agent 分组的对象**（即使 single 模式也是对象），每项包含
  `session_id` / `session_authoritative` / `fresh_sessions`；
  ADR v6 要求的 `age_minutes` / `stale_hours` 目前实现尚未写入，见最终报告；
- `agents`：该仓库内的活跃会话，字段 `id` / `cwd` / `status`；
- `routes`：每条消息的 `repo` / `agent` / `ids` / `resolve` / `sessions`。

DSH 日志里应出现 `aw-wake: woke ...`。

发消息：

```powershell
AW_AGENT_ID=pcB-ba-1 aw.py msg send --to pcA-ba-1 --type question --body "ping"
```

DSH 会话应自动开始一轮并提示用 `msg_inbox` 取正文。

### 3.4 注意

- 插件优先用 map/legacy/config 定位会话；multi 模式默认不做 cwd 猜测；
  single 模式才允许唯一 cwd 兜底；多个会话同 cwd 时放弃唤醒，不广播；
- `seen` 状态在 `.aw/aw-wake-seen.json`，重启不重放；
- `minIntervalMs` 默认 10 秒，避免消息 burst 反复打扰；
- 只 wake，不代替 `msg_inbox` / `msg_reply`。

## 4. 共同验证清单

| # | 检查 | 期望 |
|---|------|------|
| 1 | `aw.py watch --status` | RUNNING |
| 2 | `.aw/wake/<agent>.json` | 有新消息后出现 |
| 3 | omp 日志 | `recv` + `steer` |
| 4 | DSH debug | `routes` 有 `resolve`；`map` 有对应 agent 的 `session_id` |
| 5 | 会话里再 `msg_inbox` | 能看到同一条消息 |
| 6 | 不重复 | 同 id 只 wake 一次 |

## 5. 安全与边界

- 插件**不自动回复、不 ack、不 claim**；只把“有消息”变成一轮提示；
- 通知/唤醒内容只带 id、from、type、expect、subject，不带正文；
- 共享配置不得写死 `AW_AGENT_ID`；
- 插件不是消息可靠通道：消息仍在 bus 上，`msg_inbox` 才是事实；
- 卸载：删除扩展/插件并重启；watcher 可继续保留。

## 6. 故障排查

以 `.aw/aw-wake-debug.json` 的 `routes[].resolve` 为准：

| resolve 原因 | 含义 / 检查 |
|--------------|-------------|
| `no-map` | 没跑过 CLI `agent whoami`，或 map 不存在/不合规；先跑一次 whoami |
| `map-version` / `map-not-authoritative` / `map-agent-mismatch` / `map-no-session` / `map-no-host` | map 形状不合规；按提示修 `.aw/sessions/<agent>.map.json`，或删掉重跑 whoami（当前实现尚未全部产生这些 reason） |
| `map-offline` | 映射的会话已不存在（换会话/会话关闭）；重跑 whoami 刷新 map |
| `map-ambiguous:N` | 120 分钟内同一 agent 有 N 个会话；需人工确认，不要广播 |
| `session-shared` | 两个 agent 的 map 指向同一 session；双方拒绝唤醒（防串号） |
| `ambiguous-cwd` | 同一仓库多个活跃会话且缺 map；跑 whoami 或显式 `sessionId` |
| `cwd-unique` / `cwd-bootstrap` | cwd 兜底命中；仅 single 模式或单元素 `agents` 白名单允许 |
| `sessions-file` / `config` | 走 legacy 或 pin；检查对应 `.aw/sessions/<agent>.json` / `sessionId` |
| DSH 没有 wake | watcher 是否 RUNNING；wake 文件是否存在；`agentId` / `agents` 是否写对 |
| 重复唤醒 | 是否同时跑了两个 watcher / 两个 MCP 进程 |

> 注：`map-version` 等形状 reason 属于 ADR v6 契约；当前 `index.js` 尚未实现，
> 见 `3.2.2 的“当前实现差异”。
