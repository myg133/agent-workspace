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
4. DSH 需要 `AW_REPO_ROOT` 指向 workspace 根，且 DSH 会话 cwd 与它一致。

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

### 3.2 启动环境

```powershell
$env:AW_REPO_ROOT = "D:\proj\my-project"
$env:AW_AGENT_ID = "pcA-ba-1"
dsh web
```

插件配置：

```yaml
repoRoot: !!js process.env.AW_REPO_ROOT
agentId: !!js process.env.AW_AGENT_ID
```

- `repoRoot` 必须是 workspace 根；
- `agentId` 必须是收件 agent；
- DSH 会话的 cwd 必须等于 `repoRoot`，否则插件找不到目标会话；
- 改完重启 DSH。

### 3.3 验证

```powershell
Get-Content .aw\aw-wake-debug.json -Tail 40
```

应看到当前 DSH agent 的 `matched: true`；DSH 日志里应出现
`aw-wake: woke ...`。

发消息：

```powershell
AW_AGENT_ID=pcB-ba-1 aw.py msg send --to pcA-ba-1 --type question --body "ping"
```

DSH 会话应自动开始一轮并提示用 `msg_inbox` 取正文。

### 3.4 注意

- 插件按 `repoRoot` 匹配 DSH 会话 cwd；会话在别的目录不会被叫醒；
- `seen` 状态在 `.aw/aw-wake-seen.json`，重启不重放；
- `minIntervalMs` 默认 10 秒，避免消息 burst 反复打扰；
- 只 wake，不代替 `msg_inbox` / `msg_reply`。

## 4. 共同验证清单

| # | 检查 | 期望 |
|---|------|------|
| 1 | `aw.py watch --status` | RUNNING |
| 2 | `.aw/wake/<agent>.json` | 有新消息后出现 |
| 3 | omp 日志 | `recv` + `steer` |
| 4 | DSH debug | `matched: true` |
| 5 | 会话里再 `msg_inbox` | 能看到同一条消息 |
| 6 | 不重复 | 同 id 只 wake 一次 |

## 5. 安全与边界

- 插件**不自动回复、不 ack、不 claim**；只把“有消息”变成一轮提示；
- 通知/唤醒内容只带 id、from、type、expect、subject，不带正文；
- 共享配置不得写死 `AW_AGENT_ID`；
- 插件不是消息可靠通道：消息仍在 bus 上，`msg_inbox` 才是事实；
- 卸载：删除扩展/插件并重启；watcher 可继续保留。

## 6. 故障排查

| 现象 | 检查 |
|------|------|
| omp 只有 `bridge loaded` | MCP 是否发 `notifications/message`；`aw_mcp.py` 是否默认开启 |
| omp 没有 `steer` | 是否重复 id（seen 去重）；MCP 是否绑定了别的 agent |
| DSH 没有 `matched` | `AW_REPO_ROOT` 与 DSH 会话 cwd 是否一致 |
| DSH 没有 wake | watcher 是否 RUNNING；wake 文件是否存在；agentId 是否写对 |
| 重复唤醒 | 是否同时跑了两个 watcher / 两个 MCP 进程 |
