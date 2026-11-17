# MQTT + Git bus 协议（v0.1）

> 目标：跨机实时通信 + 可审计消息历史 + BA 在线状态。
> MQTT 是传输/唤醒层；Git bus 是审计事实；docs 是需求/状态事实。

## 1. 边界

| 层 | 负责 |
|---|---|
| docs 仓库 | 需求、验收、status、决策 |
| Git bus 分支 | 消息正文、不可变审计 |
| MQTT | 实时通知、唤醒、presence |
| 本地 `.aw/` | inbox 缓存、claim、session、outbox |

不做：

- 用 MQTT retained 消息存任务状态；
- 用 MQTT 做 claim 仲裁；
- 把 presence 写进 bus。

## 1.1 Project 身份

`project_id` 不手填，由代码仓库 remote 自动推导：

```text
origin = git@github.com:myg133/agent-workspace-single.git
       ↓ 归一化
alias  = github.com/myg133/agent-workspace-single
id     = p-<sha256(alias)[:12]>
```

规则：

- 优先 `origin`，没有就用第一个 remote；
- 支持 scp-like / ssh / https；
- 去掉用户名、密码、协议、`.git`；
- host 小写；默认端口（22/80/443）省略；
- 没有 remote 时用根 commit：`root:<sha>`；
- 配置文件写入 `project_id / project_alias / project_source`；
- MQTT 启动前跑 `project check`，config 与 remote 不一致就拒绝连接。

```bash
aw_single.py project id
aw_single.py project alias
aw_single.py project check
```

## 1.2 Broker 配置

用户必须在 `.aw/config.json` 的 `mqtt` 段指定 broker；不配置就是仅本地模式：

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

也可以用 `aw_single.py init` 参数写入：

```bash
aw_single.py init --root . \
  --code-root D:/proj/app --docs-root D:/proj/docs \
  --base-branch develop \
  --mqtt-host broker.example.com --mqtt-port 8883 \
  --mqtt-username aw --mqtt-ca D:/certs/ca.pem
```

密码不要写配置文件；用环境变量：

```bash
export AW_MQTT_PASSWORD='...'
```

规则：

- 没有 `mqtt.host` / `enabled=false` → 仅本地，不连接；
- `tls=false` 只用于本地测试；
- `client_id` 为空时由 watcher 生成；同一 broker 下必须唯一；
- `ca_file` 支持自签 CA；
- 配置只在本地 `.aw/config.json`，不提交。

## 2. Bus 分支

位置：**代码仓库**的 orphan 分支 `refs/heads/bus`。

```text
bus
└── messages/
    ├── <id>.json
    └── ...
```

每个 commit 追加一个消息文件，commit message 只做索引：

```text
[aw] <id> <from> -> <to> <type>
```

消息文件：

```json
{
  "id": "a1b2c3d4",
  "from": "planner-1",
  "to": ["ba-1"],
  "type": "question",
  "expect": "reply",
  "subject": "接口版本",
  "body": "这个接口用 v2 吗？",
  "at": "2026-11-16T10:00:00Z",
  "reply_to": null,
  "docs_repo": "product-docs",
  "docs_ref": "demands/REQ-001/",
  "docs_sha": "<sha>"
}
```

规则：

- 文件名是唯一 id，不同消息不会内容冲突；
- 不 checkout bus，不把 bus 合进 main/develop；
- 不允许 force-push / 删除；
- 大小上限：正文建议 1 MB，硬上限 8 MB；附件只存链接；
- 写入用 `git hash-object` / `commit-tree` / `update-ref`，不碰工作区。

## 3. MQTT

### 3.1 Topic

```text
aw/v1/{project}/agent/{agent}/inbox
aw/v1/{project}/agent/{agent}/presence
aw/v1/{project}/broadcast
```

- `project` 是稳定项目标识，不要用本机绝对路径；
- `agent` 是稳定 agent_id；
- 一个 agent 一个 inbox。

### 3.2 消息 payload

```json
{
  "v": 2,
  "id": "a1b2c3d4",
  "project": "product-x",
  "from": "planner-1",
  "to": ["ba-1"],
  "type": "question",
  "expect": "reply",
  "subject": "接口版本",
  "at": "2026-11-16T10:00:00Z",
  "bus_sha": "9f8e7d6",
  "body_in_bus": true
}
```

- `id` 全局唯一，接收方按 id 去重；
- `bus_sha` 指向审计记录；
- `body_in_bus=true` 时，body 从 bus 读；
- 小消息可以在 payload 里带 `body`，但仍然必须带 `bus_sha`。

QoS 1，retained=false。

### 3.3 发送流程

```text
1. 生成 id
2. 写 bus commit（本地）
3. publish MQTT（id + bus_sha）
4. 异步 push bus；失败进 outbox
```

- 默认先本地 commit，再 MQTT；
- 需要强审计时可配置“bus push 成功后才 publish”；
- MQTT 失败不丢消息：bus 仍在，watcher 可补通知。

### 3.4 接收流程

```text
1. 收到 MQTT，按 id 去重
2. 落本地 .aw/inbox/<agent>/<id>.json
3. 写 wake
4. 唤醒会话
5. 需要时按 bus_sha 读正文
```

- 不依赖 MQTT 顺序；
- 不把 MQTT 消息当唯一存储；
- body 缺失时先看 bus，bus 不可用则提示待同步。

## 4. Presence

### 4.1 权威

每台机器一个 watcher，由 watcher 发布本机 agent 的 presence。
agent 不直接发 presence。

### 4.2 Topic 与 payload

```text
aw/v1/{project}/agent/{agent}/presence
QoS 1, retain=true
```

```json
{
  "agent": "ba-1",
  "role": "ba",
  "status": "online",
  "session": "session-...",
  "host": "pc-a",
  "pid": 12345,
  "pid_started_at": "2026-11-16T09:00:00Z",
  "ts": "2026-11-16T10:00:00Z",
  "ttl_s": 90
}
```

### 4.3 Session 文件

agent 运行时写：

```text
.aw/sessions/<agent>.json
```

```json
{
  "agent_id": "ba-1",
  "role": "ba",
  "session_id": "session-...",
  "pid": 12345,
  "pid_started_at": "2026-11-16T09:00:00Z",
  "host": "pc-a",
  "last_seen": "2026-11-16T10:00:00Z"
}
```

watcher 每 30 秒检查：

- pid 存在；
- `pid_started_at` 与进程创建时间一致（防 PID 复用）；
- 失败 → 发布 offline。

### 4.4 状态

| 状态 | 含义 |
|---|---|
| `online` | 连接 + 心跳新鲜 |
| `stale` | ts 超过 ttl_s，但未收到 offline |
| `offline` | 正常退出 / PID 不存在 / TTL 过期 |
| `unknown` | 从未见过 presence |

消费方只把 `online + 新鲜 ts` 当作在线；stale/unknown 不阻塞消息发送，只是不主动唤醒。

### 4.5 Watcher 崩溃

watcher 挂掉后没有新心跳，消费者按 TTL 判 stale。  
watcher 重启后扫描 session，重新发布 online。

## 5. 去重与 ack

- 接收方维护 `seen_ids`（本地文件）；
- 重复 id 直接丢弃；
- ack 作为一条普通消息写 bus + MQTT；
- 不依赖 MQTT 的 exactly-once。

## 6. 安全

- TLS；
- 每客户端用户名/密码或证书；
- ACL 限制：只能订阅自己的 inbox/presence，按项目允许发布；
- 不把 token 写进消息；
- bus 分支访问权限 = 代码仓库权限。

## 7. 当前状态

已实现：

- 本地 inbox / wake / watcher；
- 单机 claim/worktree；
- bus v2 写入/读取/log/show；
- MQTT publish/subscribe（vendored paho-mqtt）；
- watcher presence 发布；
- transport `auto / mqtt / bus / local` 基础选择。

待完善：

- bus 冲突重试与批量 push；
- MQTT 断线重连细节；
- presence 的 watcher 级 TTL/告警；
- 完整多机联调。

## 8. 不做

- MQTT claim；
- retained 消息正文；
- 把 presence 写进 bus；
- 用 MQTT 替代 docs/status。
