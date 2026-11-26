# DSH 唤醒插件

单机版使用 host 插件读 `<local-root>/.aw/wake/<agent>.json`，把消息转成
DSH `agent.followup()`。

插件来源：`agents/dsh/aw-wake/`，与多 agent workspace 版共用实现，
但这里的 `repoRoot` 指向**本地根**（包含 `.aw/`），不是代码仓库。

## 1. 安装

把 `agents/dsh/aw-wake` 复制到 DSH profile 的 plugins 目录：

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

重启 DSH。

## 2. 配置

`agents/dsh/aw-wake/cordis.patch.yml` 默认不写 `repoRoot`，让插件从会话 cwd
向上找 `.aw/`。单机版通常：

```text
D:/proj/                 # 本地根，含 .aw/
├── app/                 # DSH 会话 cwd 在这里
├── docs/
└── .aw/
```

DSH 会话 cwd 在 `app/` 或 `app/` 子目录时，插件向上找到 `D:/proj/.aw/`。

如果 DSH 会话 cwd 不在本地根下：

```yaml
config:
  repoRoot: D:/proj
```

或者限定多个：

```yaml
config:
  repoRoots:
    - D:/proj/a
    - D:/proj/b
```

- `agentId` 不写 = multi 模式，监听所有 `.aw/wake/*.json`；
- `agentId` 写了 = single 模式；
- `agents` 可选白名单。

## 3. 写 map（关键）

DSH 插件用 `.aw/sessions/<agent>.map.json` 判断 agent 对应哪个 DSH 会话。
每个 DSH 会话需要跑一次：

```bash
aw.py whoami
```

如果该会话有 `DSH_SESSION_ID`，会写：

```text
.aw/sessions/<agent>.map.json
.aw/sessions/by-session/<sha256(session)[:16]>.json
```

map 内容包含：

```json
{
  "agent_id": "ba-1",
  "session_id": "session-...",
  "session_source": "DSH_SESSION_ID",
  "session_authoritative": true,
  "sessions": [...],
  "host": "pc-a",
  "cwd": "D:/proj/app",
  "pid": 0,
  "updated_at": "...",
  "map_version": 2
}
```

DSH 插件按 `session_id` 找 live session；找不到就 `map-offline`，不会广播。

## 4. 启动 watcher

```bash
aw.py watch --ensure --interval 5
```

消息：

```bash
aw.py msg send --to ba-1 --type question --body "ping"
```

watcher 写 `.aw/wake/ba-1.json`，DSH 插件唤醒对应会话。

## 5. 验证

```powershell
Get-Content .aw\aw-wake-debug.json -Tail 80
```

看：

- `repo`：本地根；
- `map`：按 agent 分组的 map；
- `routes`：每条消息的 `resolve` 原因；
- `agents`：该本地根内的活跃 DSH 会话。

DSH 日志应出现：

```text
aw-wake: woke <session> for N message(s) of <agent>
```

## 6. 注意

- DSH 桌面版如果拿不到 shell 环境变量，仍需要在 DSH 会话里运行
  `aw.py whoami` 来写 map；插件本身不写 map；
- `repoRoot` 是本地根，不是 `app/`；
- 不要把 `agentId` 写死给多个 BA；
- 一个 DSH 会话对应一个 agent；不要两个 agent 共用一个 session；
- 插件只 wake，不回复、不 ack、不改状态。
