# Setup

单机版不依赖 pip 安装包；只需要 Python 3.8+、git，以及一组环境变量。

## 1. 一次性初始化

```bash
python scripts/aw_single.py init \
  --root D:/proj \
  --code-root D:/proj/app \
  --docs-root D:/proj/docs \
  --base-branch develop
```

如果客户提供 MQTT：

```bash
python scripts/aw_single.py init \
  --root D:/proj \
  --code-root D:/proj/app \
  --docs-root D:/proj/docs \
  --base-branch develop \
  --mqtt-host broker.example.com \
  --mqtt-port 8883 \
  --mqtt-username aw \
  --mqtt-ca D:/certs/ca.pem
```

没有 `--mqtt-host` 就是本地/bus 模式，不会尝试连接 broker。

## 2. 环境变量

每个 agent 进程启动前设置，只影响当前进程及其子进程。

| 变量 | 必填 | 说明 |
|------|------|------|
| `AW_AGENT_ID` | 是 | 稳定 agent 槽位，如 `ba-1` / `planner-1` |
| `AW_SESSION_ID` | 否 | 本次会话 id；省略时用 `proc-<pid>` |
| `AW_SINGLE_ROOT` | 否 | 本地根目录；omp 插件默认从 cwd 向上找 `.aw/config.json` |
| `AW_ROLE` | 否 | `ba` / `planner` / `dev` / `qa`，写入 session 和 presence |
| `AW_MQTT_PASSWORD` | 否 | MQTT 密码；配置中的 `password_env` 默认指向它 |
| `AW_WAKE_DISABLE` | 否 | 设为 `1` 时插件不唤醒；子 agent 推荐设置 |
| `AW_OMP_WAKE_LOG` | 否 | omp 插件日志路径覆盖 |

不要把密码写进 `.aw/config.json`。

## 3. Windows PowerShell

每个终端 / omp 会话分别设置：

```powershell
$env:AW_AGENT_ID = "ba-1"
$env:AW_SESSION_ID = "session-20261116-ba1"
$env:AW_SINGLE_ROOT = "D:/proj"
$env:AW_ROLE = "ba"

# 仅 MQTT 需要
$env:AW_MQTT_PASSWORD = "..."
```

然后启动 omp：

```powershell
omp
```

## 4. macOS / Linux

```bash
export AW_AGENT_ID=ba-1
export AW_SESSION_ID=session-20261116-ba1
export AW_SINGLE_ROOT=/path/to/proj
export AW_ROLE=ba

# 仅 MQTT 需要
export AW_MQTT_PASSWORD='...'
omp
```

## 5. 多 agent 示例

每个 agent 一个终端，`AW_AGENT_ID` 必须不同：

```powershell
# 终端 1
$env:AW_AGENT_ID = "planner-1"
$env:AW_ROLE = "planner"
omp
```

```powershell
# 终端 2
$env:AW_AGENT_ID = "ba-1"
$env:AW_ROLE = "ba"
omp
```

同一个 `AW_AGENT_ID` 不要同时开两个会话；否则 presence 和 claim 都会冲突。

## 6. 启动 watcher

```bash
python scripts/aw_single.py watch --ensure --interval 5
python scripts/aw_single.py watch --status
```

查看本地在线状态：

```bash
python scripts/aw_single.py presence --json
```

## 7. MQTT 配置

MQTT 默认关闭。需要时在 `.aw/config.json` 配置：

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

连接前检查：

```bash
python scripts/aw_single.py project check
```

## 8. 验证

```bash
python scripts/aw_single.py whoami
python scripts/aw_single.py project id
python scripts/aw_single.py project check
python scripts/aw_single.py presence
```

omp 插件：

```bash
python scripts/aw_single.py msg send --to ba-1 --type question --body "ping"
```

应看到 omp 收到 `[local] 收到 ...`。

## 9. 不要做的事

- 不要把 `AW_AGENT_ID` 写进共享 MCP 配置；
- 不要把 MQTT 密码提交到仓库；
- 不要用目录名代替 `AW_AGENT_ID`；
- 不要同时跑旧 `aw.py watch` 和新 `aw_single.py watch`；
- 不要给 `watch` 配 `--exec` 的同时又装 omp wake 插件，二选一。
