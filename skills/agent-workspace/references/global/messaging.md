# BA 间消息（bus 分支）

## 1. 为什么统一走 bus

| 方案 | 冲突 | 历史噪音 | 跨机 | 结论 |
|------|------|---------|------|------|
| 写文件不提交 | 无 | 无 | ❌ 不共享 | 仅限同机 |
| 提交到 demand | 有 | **严重**（80 条/天） | ✅ | 污染需求历史 |
| **空 commit 到 bus** | **无** | 隔离在独立分支 | ✅ | ✅ |

bus 是**零文件的 orphan 分支**，每条消息一个空 commit。约 250 字节/条，一个月 0.5MB。

## 2. 分支约定

```text
refs/heads/bus      # orphan，tree 为空，永远不 checkout
```

三条铁律：

1. **不要 checkout bus**（空树会把工作区文件删掉）。工具内部用 `git commit-tree`，不碰工作区。
2. **禁止 force-push**（在远端开分支保护），否则全队通信历史被抹。
3. **CI 排除 bus 分支**（`if: github.ref != 'refs/heads/bus'`）。

## 3. 消息格式

commit message 本身就是消息：

```text
[msg] contract-change user-api -> pcB-ba-1

---
id: a1b2c3d4
from: pcA-ba-1
to: [pcB-ba-1]
cc: [pcA-ba-2]
at: 2026-10-21T07:40:12Z
type: contract-change
ref: BA/contracts/user-api/v3.md @ 4f2a9c1
contract: user-api
version: 3
deadline: 2026-10-22T00:00:00Z
---
`POST /login` 增加可选 `mfaToken`，v1 消费者不受影响。
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 8 位十六进制，重试不变 |
| `from` | ✅ | 自动填当前 `AW_AGENT_ID` |
| `to` | ✅ | 数组；`all` / `role:ba` / `agent_id` |
| `cc` | — | 同上 |
| `at` | ✅ | RFC3339 UTC（`Z`） |
| `type` | ✅ | 见下 |
| `ref` | — | `路径 @ sha`，**不要写分支名** |
| `contract`/`version` | contract-* 必填 | 与 `BA/contracts/INDEX.md` 对齐 |
| `deadline` | — | 超时未 ack 由巡检提醒 |
| `thread` | — | 话题 id |
| `re`/`result` | ack 时 | 被回执的消息 id + ok/no |
| body | ✅ | ≤ 2000 字符，契约正文放 `BA/contracts/` |

类型：`fyi` `question` `blocker` `handoff` `contract-change` `contract-ack` `decision`。

## 4. 寻址与可见性

> **物理上所有 BA 都能读到所有消息。`to` 是路由标签，不是访问控制。**

判定“这条是不是发给我的”：

```text
to/cc 含 我的 agent_id   → 是
to/cc 含 all             → 是（广播）
to/cc 含 role:<我的角色>  → 是
其余                     → 不是
```

命令行输出必须带标记：

```text
2026-10-21T07:40Z  pcA-ba-1  → me         contract-change  user-api@3
2026-10-21T07:45Z  pcA-ba-2  → pcB-ba-1   question
```

## 5. 命令

```bash
aw.py msg send --to pcB-ba-1 --type contract-change \
  --contract user-api --version 3 --body "..." \
  [--cc ...] [--ref "path @ sha"] [--deadline ...] [--thread ...] [--priority p1]

aw.py msg inbox [--all] [--sender X] [--since 2026-10-21T00:00:00Z] [--full] [--no-fetch]
aw.py msg list  [--all] [--limit N]
aw.py msg ack <id> [--ok|--reject] [--note "附言"]
aw.py msg flush           # 重试 outbox 里的未发送消息
```

退出码：`0` 已发送/已读；`3` 已排队（网络失败）、被拒绝或无消息。

## 6. 离线与并发

- **发送先落 `.aw/outbox/`**：push 成功才删除；失败返回 `QUEUED`，下次 send/inbox 自动重试。
- **并发推送**：push 被拒 → 重新 fetch → 基于最新 tip 重放 outbox → 再 push（最多 4 次）。
- **永不 rebase / force**：远端历史只增不改，消息顺序 = push 顺序。
- **时间戳用 UTC**：跨机时钟不一致时仍可比；排序以 commit 图为准。

## 7. 读取与游标

`.aw/msg-cursor.json` 记录每个 agent 读到的 `(at, id)`，`inbox` 只显示增量。
游标是本机的，不随 git 同步。

## 8. 和 demand 的分工

| 内容 | 通道 | 理由 |
|------|------|------|
| 通知、提问、交接、阻塞 | bus | 高频、短命 |
| 契约变更通知 | bus（正文在 demand） | 通知是消息，契约是事实 |
| 契约、ADR、需求状态 | demand | 需要 review 与追溯 |

**禁止**把对话直接提交到 demand——那会让需求历史不可读。

## 9. 故障处理

| 现象 | 处理 |
|------|------|
| `QUEUED` 一直不消失 | 检查 remote/网络；恢复后 `aw.py msg flush` |
| `git log bus` 为空但发过消息 | 检查是否推到了别的 remote；`git fetch origin bus` |
| 消息解析失败被忽略 | 检查 `---` 分隔与必填字段；`aw.py msg list --all --full` 看原文 |
| bus 被误删 | 最后一条消息的 commit 仍在 reflog；用 `git update-ref` 重建 |

## 10. 规模

| 指标 | 数值 |
|------|------|
| 单条 commit | ~250 B |
| 4 BA × 20 条/天 | ~20 KB/天 |
| 一年 | ~7 MB |
| 拉取成本 | 增量 fetch，只有新 commit |
