# BA 间消息（bus 分支）

## 0. 谁能写 bus

| 角色 | 发送 / ack | 读取 |
|------|-----------|------|
| Planner | ✅ | ✅ |
| BA | ✅ | ✅ |
| Dev / QA / Deploy / Explore | ❌ | 只读（一般也不需要） |
| Notifier | ❌ | ✅（只读） |

子 agent 与自己的 BA 交互，由 BA 决定是否对外发消息。

判定顺序：

1. `AW_ROLE` 环境变量（spawn 子 agent 时注入，如 `AW_ROLE=dev`）；
2. roster 里该 agent 的 `role`（`agent register <name> --role dev`）；
3. 都没有 → 按 `ba` 处理（向后兼容）。

不是 `ba` / `planner` 时，`msg send` / `ack` / `flush` 直接拒绝：

```text
错误: bus 只允许 BA / Planner 使用；子 agent 请与你的 BA 交互，不要直接发消息。
```

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
| `ref` | — | **仓库相对路径** `路径 @ sha`，**不要写分支名、不要写本机绝对路径** |
| `contract`/`version` | contract-* 必填 | 与 `BA/contracts/INDEX.md` 对齐 |
| `deadline` | — | 超时未 ack 由巡检提醒 |
| `thread` | — | 话题 id |
| `re`/`result` | ack 时 | 被回执的消息 id + ok/no |
| body | ✅ | ≤ 2000 字符，契约正文放 `BA/contracts/` |

类型：`fyi` `question` `blocker` `handoff` `contract-change` `contract-ack` `decision`。

### 收件人校验

`msg send` 只允许发给**已注册且 active** 的 agent：

| 收件人 | 规则 |
|--------|------|
| 具名 `pcA-ba-1` | 在 `BA/plan/agents.json` 中且 `status=active` |
| `all` | 至少一个 active |
| `role:ba` | 至少一个该角色 active |

未注册 → 拒绝并列出可用名字。应急可 `--force`，但会在日志里留下痕迹。
名册由 Planner 用 `aw.py agent register/deactivate` 维护。

### 路径约定（重要）

消息会跨机器读，**不能出现本机绝对路径**：

| 场景 | 写法 |
|------|------|
| 引用仓库内文件 | `BA/contracts/user-api/v3.md`（推荐） |
| 带根占位 | `<repo-root>/BA/contracts/user-api/v3.md` → 发送时自动归一化为相对路径 |
| 引用代码位置 | `src/auth/login.ts:42` |
| 禁止 | `C:\proj\BA\...`、`/Users/me/...`、`/home/...`、`\\server\share` |

`aw.py msg send` 会拒绝以上绝对路径（`ref` 和 `body` 都检查），原因有两个：

1. **跨机不可读**：Mac / Linux 上没有 `C:\`；
2. **泄露目录结构**：用户目录、机器名、项目布局都会进入 bus 历史，且无法撤回。

同理，`.feature/manifest.json` 的 `demand_dir` 也存仓库相对路径，不存本机路径。

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

## 7. 已读状态（按消息 id，不按时间）

**本机状态，不走 git**：`.aw/msg-read/<agent_id>.json` 记录"已读过哪些消息 id"。

```text
未读 = bus 上所有消息 - 已读 id 集合
```

为什么不用 `(at, id)` 时间游标（1.7.0 及更早）：

| 问题 | 后果 |
|------|------|
| 消息按发送端时钟排序 | 时钟慢的机器发来的消息 `at` 更早 → 永远排在上次游标之前 → **被静默跳过** |
| 乱序到达（重试、补推） | 同上，直接丢 |
| `--limit` 只显示最新的 N 条，游标却推到最新 | 更旧的未读被永久跳过 |
| 读一次就算消费 | 任何以同 `agent_id` 运行的进程（如 Notifier）都会替 BA 消费 |

现在的规则：

- **按 id 判断已读**：与时钟无关，乱序到达照样能看见；
- **按 `agent_id` 隔离**：A 读过不影响 B；
- `--limit` 取**最旧的 N 条**，且只标记真正显示过的；
- `--no-advance` 不标记（Notifier 专用）；
- 旧游标在首次运行时自动转换成等价的 id 集合，不会重复推送历史消息。

**注意**：同一个 `agent_id` 等于同一个收件箱。BA 和它的 Notifier、或者两个同名会话，
共享同一份已读集合——所以 Notifier 必须用 `--no-advance`，且名称必须一会话一个。

## 8. 和 demand 的分工

| 内容 | 通道 | 理由 |
|------|------|------|
| 通知、提问、交接、阻塞 | bus | 高频、短命 |
| 契约变更通知 | bus（正文在 demand） | 通知是消息，契约是事实 |
| 契约、ADR、需求状态 | demand | 需要 review 与追溯 |

**禁止**把对话直接提交到 demand——那会让需求历史不可读。

## 9. 谁在读消息

BA 不会主动读——所以分两层：

| 层 | 作用 |
|----|------|
| **门禁** | `claim next` 发现未读 → `UNREAD_MESSAGES`，exit 4，不读不许领新任务 |
| **Notifier** | 只读子 agent，跑 `msg inbox --json --no-advance` 整理摘要交回 BA（不推进游标） |

Notifier 的硬限制（只读、不回复、不 ack）见 `references/roles/notifier.md`。

## 10. 故障处理

| 现象 | 处理 |
|------|------|
| `QUEUED` 一直不消失 | 检查 remote/网络；恢复后 `aw.py msg flush` |
| `git log bus` 为空但发过消息 | 检查是否推到了别的 remote；`git fetch origin bus` |
| 消息解析失败被忽略 | 检查 `---` 分隔与必填字段；`aw.py msg list --all --full` 看原文 |
| bus 被误删 | 最后一条消息的 commit 仍在 reflog；用 `git update-ref` 重建 |

## 11. 等待消息（优先于轮询）

能阻塞就不要轮询。MCP 形态下用 `msg_wait`，一次调用最长 120 秒：

```json
{"timeout":120,"interval":5,"thread":"a1b2","contract":"user-api"}
```

| 结果 | 返回 | 退出码 |
|------|------|--------|
| 命中 | `found:true` + 消息列表 | 0 |
| 超时 | `found:false` | 3 |

默认**不消费**（不推进已读）；需要消费时加 `consume:true`。

CLI 无 MCP 时可退回轮询，但建议按状态分档（见下）：

| 状态 | 间隔 |
|------|------|
| 阻塞等 CI | 1 / 5 / 15 分钟 |
| 有任务在手 | 15 分钟 |
| 空闲 | 30 → 60 分钟退避 |
| 等某个决定 | 2–3 分钟，最多 30 分钟 |

## 12. 规模

| 指标 | 数值 |
|------|------|
| 单条 commit | ~250 B |
| 4 BA × 20 条/天 | ~20 KB/天 |
| 一年 | ~7 MB |
| 拉取成本 | 增量 fetch，只有新 commit |
