# 消息触发（替代定时轮询）

轮询的问题不是"查得勤"，而是**每次查都要唤醒模型**：
一次检查 = 一个模型回合，成本与等待时长成正比，与消息数量无关。

8 个 agent × 每 5 分钟检查一次 = 每天 2300+ 次模型回合，大部分是空转。

## 1. 三种触发方式

| 方式 | 适用 | 空闲 token |
|------|------|-----------|
| **阻塞等待**（`msg_wait`） | 常驻 agent | 0（工具调用挂起，模型不跑） |
| **watcher + 拉起** | 非常驻 / supervisor | 0（只 fetch，不调模型） |
| 定时轮询 | 客户端不支持长调用 | 高，不推荐 |

原则：**空闲时不要让模型醒着。**

## 2. watcher：每台机器一个

> 不要自己读 `aw.py` 源码写 watchdog。先 `aw.py schema` 看有没有现成命令；
> `watch` 就是为此准备的。



```bash
aw.py watch --interval 5 --json
```

输出（每行一条）：

```json
{"agent":"pcA-ba-2","id":"a1b2","from":"pcA-ba-1","type":"question","expect":"reply"}
```

直接拉起 agent：

```bash
aw.py watch --interval 5 --exec /path/to/start-agent.sh
```

`--exec` 会带这些环境变量：

| 变量 | 值 |
|------|----|
| `AW_WAKE_AGENT` | 收件 agent_id |
| `AW_WAKE_MSG_ID` | 消息 id |
| `AW_WAKE_TYPE` | 消息类型 |
| `AW_WAKE_FROM` | 发送者 |

行为：

- 首次启动会 **seed**，跳过历史消息，不重放；
- 状态在 `.aw/watch-state.json`（pid / 心跳 / wake_dir）；
- 单机文件锁，重复启动输出 `WATCH_RUNNING`；
- 只 `git fetch`，不调用模型；
- `--wake-dir .aw/wake` 会把每个 agent 的唤醒事件写成 `.aw/wake/<agent>.json`，供 MCP 转通知。

### 2.1 一台 PC 多个 agent

watcher 是 **per repo / per machine**，不是 per agent：

| 机器 | agent | watcher |
|------|-------|---------|
| HomePC | dsh + omp + codex | **1 个** |
| workPC | dsh + omp | **1 个** |

- 同一仓库的多个 agent 只是不同的 `AW_WAKE_AGENT`，一个 watcher 全部覆盖；
- 不同仓库（不同项目）才需要各起一个，锁是 per repo 的；
- `--exec` 现在是**非阻塞**的：它会拉起进程后立刻继续监听，不会因为 agent 跑得久而漏消息；
- 派发脚本必须按 `AW_WAKE_AGENT` 路由，并对同一 agent 加锁去重，避免一次 burst 拉起多个实例。

如果 agent 由框架自带的多会话机制管理、不需要外部拉起，也可以让每个 agent
自己跑 `msg watch`，按 `AW_AGENT_ID` 只看自己的收件箱：

```bash
AW_AGENT_ID=pcA-ba-1 aw.py msg watch --once --json   # 有消息 exit 0，没有 exit 3
```

两者区别：`aw.py watch` 是 per machine 的**唤醒器**（告诉你该拉起谁），
`msg watch` 是 per agent 的**收件箱监听**（只看发给自己的消息）。
同一台机器上用了 `aw.py watch` 就不必再让每个 agent 各起一个 `msg watch`，
否则同一条消息会触发两次。

### 2.2 谁启动 watcher

**不要由 agent 启动 watcher。** agent 是任务型进程，生命周期短，无法保证
“只跑一个”，也无法在退出后继续监听。

| 方式 | 适用 |
|------|------|
| supervisor / 启动脚本 | 开发机、容器 entrypoint |
| systemd user service | Linux 常驻 |
| launchd | macOS |
| Windows 计划任务 / 启动文件夹 | Windows |
| 手动 | 临时调试 |

原则：**一台机器、一个仓库、一个 watcher**。

检查：

```bash
aw.py watch --status          # RUNNING / STALE / STOPPED / UNKNOWN
aw.py watch --status --json
aw.py doctor                  # watcher 一行
```

状态来自 `.aw/watch-state.json`：

| 状态 | 含义 | 处理 |
|------|------|------|
| `RUNNING` | pid 存活且心跳新鲜 | 正常 |
| `STALE` | pid 还在，但超过 `max(60s, 6×interval)` 没心跳 | 可能卡在 fetch/锁；看日志后重启 |
| `STOPPED` | pid 不存在 | 重新启动 |
| `UNKNOWN` | 从未启动过 | 启动一次 |

重复启动会被文件锁挡住，输出 `WATCH_RUNNING`，不会出现两个 watcher。

### 2.3 与 MCP 通知的关系

watcher 只写 `.aw/wake/<agent>.json`；MCP 进程读这个文件、发 notification。
这样 fetch 仍然只有一份，MCP 不联网、不碰 git。

如果 MCP 没有启动，wake 文件仍在，只是没人发通知——消息本身还在 bus 上，
`msg_inbox` / `msg_wait` 仍然能取到。

## 3. supervisor 脚本

`start-agent.sh` 示例：

```sh
#!/bin/sh
case "$AW_WAKE_AGENT" in
  pcA-ba-1) exec env AW_AGENT_ID=pcA-ba-1 omp ;;
  pcA-ba-2) exec env AW_AGENT_ID=pcA-ba-2 omp ;;
  *) echo "unknown agent: $AW_WAKE_AGENT" >&2; exit 1 ;;
esac
```

要点：

- 一个 agent 一个进程；
- 启动时注入 `AW_AGENT_ID` / `AW_SESSION_ID`；
- agent 处理完消息后**退出**，不要常驻空转；
- watcher 是唯一常驻进程。

## 4. 常驻 agent 的阻塞等待

如果 agent 必须常驻：

```json
{"tool":"msg_wait","arguments":{"timeout":120,"interval":5}}
```

- 等待期间模型不产生 token；
- 客户端单次工具超时必须 ≥ wait timeout；
- 超时返回 `found:false`，再决定继续等还是退出。

### 4.1 已经常驻的会话怎么办

watcher 不能直接“注入”到一个已经挂起的 dsh / omp / codex 会话里。三种做法：

| 做法 | 说明 |
|------|------|
| agent 阻塞在 `msg_wait` | 最简单；等待期间不耗 token |
| watcher 写 wake 文件，agent 读 | 需要 agent 侧配合轮询本地文件（不 fetch） |
| 收到消息后重启该 agent | 适合“处理完就退出”的模型 |

如果 HomePC 的 omp 已经自带 watchdog，**不要再起第二个 `aw.py watch`**：

- 要么把它的 watchdog 当成唯一的 watcher；
- 要么停掉它，统一用 `aw.py watch`，否则同一条消息会唤醒两次。

## 5. 跨机

- **每台机器一个 watcher**，不要每个 agent 各自 fetch；
- bus 是唯一交换点：watcher fetch 到本地 ref，agent 读本地；
- 多台机器的 watcher 互不冲突（各自维护自己的 `.aw/watch-state.json`）。

## 6. 不要这样做

| 反模式 | 后果 |
|--------|------|
| cron 每分钟启动一次 agent | 空转 token + 冷启动 |
| 每个 agent 定时 `msg inbox` | N 倍模型回合 |
| 为了"等消息"保持 8 个空闲会话 | 8 倍待机成本 |
| watcher 每台机器跑多个 | 重复唤醒 |
