# 会话换班：agent handoff / resume

> **agent_id 是工位，session 是租约。** 换班不换 agent_id；inbox、claim、已读集合都按 agent_id 走。

## 1. 命令

~~~bash
# 旧会话退出前
aw.py agent handoff --note "换班原因" --next-step "下一步" [--json] [--no-fetch]

# 新会话启动后（同一个 AW_AGENT_ID）
aw.py agent resume [--json]
~~~

## 2. handoff 做什么

- 读取 bus + 本地 inbox，收集：
  - 未读消息；
  - `expect=ack/reply` 且尚未回复的消息；
- 写入 `.aw/handoff/<agent_id>.json`（不含正文，只含 id / 类型 / 主题 / 状态）；
- 把 `.aw/sessions/<agent_id>.json` 标记为 `offline`；
- 清掉 `.aw/msg-notified/<agent_id>.json`，让未读消息还能叫醒新会话；
- **保留 claim**，不释放、不删除、不改 `status.md`；
- **不推进已读**，不会替新会话消费消息。

## 3. resume 做什么

- 读 `.aw/handoff/<agent_id>.json`；
- 写入 `resumed_at` / `resumed_session_id`；
- 再次清掉已通知状态；
- 打印当前 claim、未处理消息、换班备注和下一步；
- **不消费消息**，新会话仍需 `msg show` / `msg inbox` 处理。

## 4. 换班流程

### 旧会话

1. 停止接新任务；claim 保持；
2. 做一次只读盘点（不要先标已读）：
   ~~~text
   msg inbox --json --no-advance
   msg pending --json
   ~~~
3. 写 handoff：
   ~~~bash
   aw.py agent handoff --note "BA 值班换班" --next-step "先处理未读消息"
   ~~~
4. 停止旧进程；
5. **不要对未结束的 claim 执行 `agent exit --force`**，那会把 claim 留成死会话。  
   REQ 结束才先 `claim release`，再 `agent exit`。

### 新会话

1. 用**同一个 `AW_AGENT_ID`** 启动；
2. 显式设置 `AW_SESSION_ID`（或启动器传入真实 session id），让 session map 可写；
3. 先 `agent whoami` 更新 session 文件 / map；
4. `agent resume`；
5. 按 handoff 里的 id 用 `msg show` 处理，处理完再推进已读；
6. `claim list` 确认 claim 还在；
7. 启动/接管 watcher，继续值班。

## 5. 状态边界

| 状态 | 按什么 | 换 session 后 |
|------|--------|--------------|
| inbox / 已读集合 | agent_id | 保留 |
| claim / WIP | agent_id | 保留 |
| session 文件 / map | session_id | 新会话覆盖 |
| 唤醒通知状态 | agent_id | handoff 清空，未读重新可叫醒 |
| 终端绑定 | 终端 | 新终端需 `agent bind` 或显式 `--agent` |

## 6. 常见错误

| 错误 | 后果 | 正确做法 |
|------|------|----------|
| 新会话用了新 agent_id | 新 inbox、新 claim，看起来"消息丢了" | 始终复用同一个 agent_id |
| 旧进程还活着 | 两个会话抢同一 inbox / 重复回复 | 先停旧进程 |
| 旧会话先 `agent exit --force` | claim 变成死会话 | 只 handoff，不 exit |
| handoff 前已读消息 | 新会话看不到未处理项 | 用 `--no-advance` 盘点，handoff 记录未处理 id |
| 不清 `msg-notified` | 新会话不再被未读叫醒 | handoff 自动清；手工换班也要清 |
| 新会话不写 map | watcher 仍路由到旧 session | 先 `agent whoami` |

## 7. 常驻模式

- **常驻的是 watcher + agent 工位，不是模型会话**；
- BA 值班会话只做 triage / claim / 派单，默认 ≤20–30 轮；
- 到换班点或上下文阈值，handoff → 停旧会话 → 新会话 resume；
- Dev / QA 每个任务一个短会话，完成后退出，不需要长期驻留；
- Planner 按需短会话，计划/ADR 写文件，不靠聊天记忆。

完整预算见 [session-budget.md](session-budget.md)。
