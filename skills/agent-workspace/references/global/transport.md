# 消息通道：本地 inbox + bus + MQTT

> 三层各司其职，按消息 id 去重，任意一层先到都能读。
> **bus 仍是唯一审计事实**；MQTT 只是实时层；本地 inbox 只是投递缓存。

## 1. 分层

| 层 | 位置 | 作用 | 跨机 | 丢消息风险 |
|----|------|------|------|-----------|
| 本地 inbox | `.aw/inbox/<agent>/<id>.json` | 先落盘、离线可读、MQTT 到达即写 | ❌ | 本机磁盘 |
| Git bus | `refs/heads/bus`（空 commit） | 可追溯、可重放、兜底投递 | ✅ | 未 push 时在 outbox |
| MQTT | broker topic | 实时推送、presence | ✅ | 断线后由 bus 补 |

发送顺序（`auto`）：

```text
1. 写本地 inbox（同机 agent 立即可读）
2. publish MQTT（若已配置且可达）
3. 写 outbox → commit 到 bus → push（失败留在 outbox，下次重试）
```

接收顺序：

```text
watcher 收到 MQTT → 写本地 inbox → 写 wake → agent 醒
watcher 轮询 bus   → 解析新 commit → 写 wake → agent 醒
msg inbox / wait / watch → bus + 本地 inbox 并集，按 id 去重
```

## 2. 模式

`.aw/config.json` 的 `transport.mode`：

| mode | 行为 | 适用 |
|------|------|------|
| `auto`（默认） | 有 MQTT 就实时 + bus 审计；没有/连不上就退回 bus | 绝大多数项目 |
| `mqtt` | 强制 MQTT；发送失败直接报错；默认仍写 bus 审计 | 明确要求实时、broker 稳定 |
| `bus` | 只走 bus，不连 MQTT | 没有 broker / 纯离线 |
| `local` | 只写本地 inbox，不写 bus、不连 MQTT | 单机试跑、临时协作 |

原则：**默认不要手动设 mode**。没有 `mqtt.host` 时 `auto` 就是 `bus`；配了 broker 才启用实时。
MQTT 连续失败会写 `.aw/transport-state.json`，60 秒内不重试，避免每条消息都卡 5 秒。

## 3. 配置

配置文件：`.aw/config.json`（本地，**不要提交**）。

```json
{
  "transport": {
    "mode": "auto",
    "audit_bus": true,
    "bus": { "enabled": true }
  },
  "mqtt": {
    "enabled": true,
    "host": "broker.example.com",
    "port": 1883,
    "tls": false,
    "ca_file": "",
    "username": "",
    "password_env": "AW_MQTT_PASSWORD",
    "client_id": "",
    "keepalive": 30,
    "topic_prefix": "aw/v1"
  },
  "project_id": "p-xxxxxxxxxxxx",
  "project_alias": "github.com/org/repo"
}
```

- 没有 `mqtt.host` 或 `mqtt.enabled=false` → 不连 MQTT；
- 密码只放环境变量（默认 `AW_MQTT_PASSWORD`），**不要写进配置**；
- `tls=true` 时用系统 CA；自签 CA 填 `ca_file`；
- `client_id` 为空时自动生成（含 host + pid + 随机后缀），同一 broker 下不会撞；
- `audit_bus=true`（默认）表示即使 `mode=mqtt` 也把消息写进 bus；关掉会失去审计与补投能力。

### 3.1 用命令写配置

不用手写 JSON：

```bash
# 查看当前通道
aw.py transport status
aw.py transport status --json

# 配置 broker（内网无 TLS）
aw.py transport set --mqtt-host 192.168.1.10 --mqtt-port 1883 --no-mqtt-tls

# 公网 / TLS
aw.py transport set --mqtt-host broker.example.com --mqtt-port 8883 --mqtt-tls

# 关闭 MQTT（回到 bus）
aw.py transport set --mqtt-disable

# 单机临时模式
aw.py transport set --mode local

# remote 变更后重写 project_id
aw.py transport set --reset-project

# 连通性测试（会发一条 retained presence）
aw.py transport test
```

`transport set` 会把 `project_id` 固定到配置里；之后 remote 变了会拒绝连 MQTT（防止串项目）。

## 4. project_id

不手填，从代码仓库 remote 推导：

```text
git@github.com:org/repo.git
  → alias github.com/org/repo
  → project_id p-<sha256(alias)[:12]>
```

规则：

- workspace 里优先用 `code/` 的 remote；没有 `code/` 时用 workspace 根；
- 没有 remote 时退化为根 commit：`root:<sha>`；
- 支持 scp-like / ssh / https，去掉用户名、密码、协议、`.git`、默认端口；
- `transport set` 时写入 `project_id / project_alias`；
- `transport test` / MQTT 发送前校验配置与当前 remote 一致，不一致拒绝。

```bash
aw.py transport status --json | grep project_id
```

## 5. MQTT topic 与 payload

### 5.1 Topic

```text
<prefix>/<project_id>/agent/<agent>/inbox
<prefix>/<project_id>/agent/<agent>/presence
```

默认 `prefix=aw/v1`。`agent` 是稳定 `agent_id`，一个 agent 一个 inbox。

### 5.2 消息 payload

```json
{
  "v": 2,
  "project": "p-xxxxxxxxxxxx",
  "id": "a1b2c3d4",
  "from": "pcA-ba-1",
  "to": ["pcB-ba-1"],
  "at": "2026-11-17T07:40:12Z",
  "type": "question",
  "expect": "reply",
  "subject": "接口版本",
  "body": "这个接口用 v2 吗？",
  "ref": "BA/contracts/user-api/v3.md @ 4f2a9c1"
}
```

- QoS 1，`retain=false`；
- 接收方按 `id` 去重：同一消息可能同时从 MQTT 和 bus 到达；
- `body` 直接带在 payload 里（工作区消息上限 2000 字符），不依赖接收方回读 bus；
- 保留 bus 作为审计：MQTT 丢了仍能在 `msg inbox` 里看到。

### 5.3 发送目标展开

`to` / `cc` 支持：

| 写法 | 展开 |
|------|------|
| `pcB-ba-1` | 该 agent |
| `all` | roster 里所有 active agent |
| `role:ba` | roster 里该角色的 active agent |

MQTT 按展开后的具体 agent 逐个 publish；没有 roster 时 `all` / `role:x` 无法展开，会报错（bus 同样需要 roster 才能定向）。

## 6. 接收与唤醒

watcher（`aw.py watch`）在 MQTT 配置可用时：

1. 订阅 `<prefix>/<project>/agent/+/inbox` 与 `.../presence`；
2. 收到消息 → 写 `.aw/inbox/<agent>/<id>.json` → 唤醒主循环；
3. 主循环写 `.aw/wake/<agent>.json`（配了 `--wake-dir`）并执行 `--exec`；
4. 同时按 `--interval` 轮询 bus，作为断线兜底。

没有 MQTT 时行为与旧版一致：只轮询 bus。

```bash
# 每台机器一个
aw.py watch --ensure --interval 5 --wake-dir .aw/wake
aw.py watch --status
```

## 7. Presence

watcher 启动时和每 30 秒把本机 session 发布到 retained topic：

```json
{
  "agent": "pcA-ba-1",
  "role": "ba",
  "status": "online",
  "session": "session-...",
  "host": "pc-a",
  "pid": 12345,
  "ts": "2026-11-17T07:40:12Z",
  "ttl_s": 90
}
```

- `retain=true`，新订阅者立刻拿到最后状态；
- watcher 退出后不再续心跳，消费方按 `ttl_s` 判 stale；
- `agent exit` 会把 session 置 offline，下一次 watcher 发布时生效；
- 消费方：`aw.py agent presence`（本地 session + MQTT 缓存合并）。

```bash
aw.py agent presence
aw.py agent presence --json
```

只把 `online + 新鲜 ts` 当作在线；stale/offline 不阻塞发消息，只是不主动唤醒。

## 8. 失败与降级

| 现象 | 行为 |
|------|------|
| MQTT 连不上（auto） | stderr 警告，降级 bus/local；60 秒内不重试 |
| MQTT 连不上（mqtt） | 报错 exit 1，不静默降级；bus 审计仍写入（audit_bus=true） |
| bus push 失败 | 消息留在 `.aw/outbox/`，返回 `QUEUED`，下次 send/inbox 自动重试 |
| 没有 remote | bus 只写本地分支；同机 agent 可投递，远端收件人会报错 |
| MQTT 收到但还没进 bus | 本地 inbox 已可读；bus 追上后按 id 去重 |
| `project_id` 不匹配 | 拒绝 MQTT，避免串到别的项目 topic |

## 9. 为什么 bus 仍是空 commit，而不是文件树

单仓版本的 bus v2 是 `messages/<id>.json`。workspace 模式刻意保留**空 commit**：

| 指标 | 空 commit | 每消息一个文件 |
|------|-----------|----------------|
| 单条体积 | ~250 B | commit + tree + blob |
| 4 BA × 20 条/天 × 1 年 | ~7 MB | 树对象随消息数增长，可达数百 MB |
| 解析 | 读 commit message | 读 tree / show 文件 |
| 冲突 | 无文件冲突 | 同 id 不会冲突，但历史树持续膨胀 |

消息正文已经同时存在本地 inbox 和 MQTT payload 里；bus 只承担**不可变审计 + 补投**，不需要再存一份 JSON 文件。

## 10. 安全

- 公网必须 TLS；内网也建议开认证；
- 密码只走环境变量，不写配置、不进消息；
- ACL 至少限制：只能订阅本项目 topic；不能订阅别的 project；
- presence 只暴露 agent_id / role / host / session，不暴露路径或 token；
- bus 分支权限 = 代码仓库权限；禁止 force-push；
- 不要把 token、cookie、内网地址写进消息正文。
