# 多 BA 并发协作（同机同仓库）

4 个以上的 BA 共享一个仓库时，需要三样东西：**身份、互斥、WIP 上限**。
缺任何一个，都会出现"一个 BA 领了多个任务"或"同一个任务被两个人做"。

## 1. 身份：agent_id + session_id

> 名称来源与强制规则见 `identity.md`：`--agent` > `AW_AGENT_ID` > 硬失败（exit 2）。
> 下面只讲并发语义。

| | agent_id | session_id |
|---|---|---|
| 生命周期 | 长期（机器上的槽位） | 每次启动 |
| 来源 | `--agent` / `AW_AGENT_ID` / 首次 `agent_id` | `--session` / `AW_SESSION_ID` / `PI_SESSION_ID` / `DSH_SESSION_ID` / `CLAUDE_SESSION_ID` / `proc-<pid>` |
| 用途 | **WIP 判定、任务归属** | 审计、存活辅助判定 |
| 记录 | `.aw/claims/<REQ>.json` 的 `agent_id` | `.aw/sessions/<agent>.json` 的 `session_id` + `session_source` |
| 示例 | `ba-slot-1` … `ba-slot-4` | `session-5cbba30e-…` / `proc-12345` |

```powershell
$env:AW_AGENT_ID = 'ba-slot-1'
$env:AW_SESSION_ID = 'session-5cbba30e'
omp
```

**WIP 只看 agent_id**：会话重启后 session 变了，但槽位不变，因此不会被允许再领一个。

如果同一 agent 换了 session，旧认领会保留并标记 `superseded`（不 requeue）：
旧会话可能还在跑，静默退回队列会让两个人做同一个需求。

### 1.1 会话↔agent 权威映射

`.aw/sessions/<agent>.map.json` 是「会话↔agent」的唯一权威映射（v3）：

```json
{
  "agent_id": "tree",
  "session_id": "session-488f...",
  "session_source": "DSH_SESSION_ID",
  "session_authoritative": true,
  "sessions": [
    {"session_id": "session-488f...", "source": "DSH_SESSION_ID", "at": "2026-11-10T23:37:00+08:00"},
    {"session_id": "session-bbbb...", "source": "PI_SESSION_ID", "at": "2026-11-10T23:20:00+08:00"}
  ],
  "host": "PC-A",
  "cwd": "E:/proj",
  "pid": 0,
  "updated_at": "2026-11-10T23:37:00+08:00",
  "map_version": 2
}
```

反向映射 `.aw/sessions/by-session/<sha256(session_id)[:16]>.json` 供会话从自身 session id 反查 agent id。

- 只在真实会话来源下写；`generated` / `mcp` 的记录只代表“某个进程用过这个身份”，
  **不得用于会话定位**；
- 同一 `session_id` 已被另一个 agent 占用时：**不覆盖** `by-session`，当前 agent 的 map
  写 `session_authoritative: false` 并 warn，消费方据此判定冲突；
- `sessions` 保留最近 8 条；120 分钟内出现不同 `session_id` 时追加并 warn，不覆盖历史；
- 同 `session_id` 60 秒内不重复写；写失败只 warn，不改变退出码；
- `by-session` 最多 500 条 / 保留 7 天，写满清理最旧；`proc-*` 不写反向映射；
- `agent whoami --session <SID>`：已声明身份（`--agent` / `AW_AGENT_ID`）优先；
  两者都没有时才用反向映射，冲突时保留已声明身份并 warn；`--json` 的 `resolved_by` 为 `session-map`；
- 消费方读不到反向映射时回退到「唯一 cwd」规则，不得直接拒绝、更不得广播；
- 映射是本机文件，不跨机同步。

> **已知限制**：MCP 身份是**进程/配置级**，不是会话级：同一 profile 内的多个 DSH 会话共享同一个
> `AW_AGENT_ID`。本映射解决「插件该叫醒哪个会话」，不解决「两个会话共用同一 agent 身份」。
> 后者需要每会话显式传 `agent_id`，或每 BA 一个 profile。

## 2. 为什么不能用「一张登记表」认领

旧做法：`git pull → 读 req-registry.md → 写一行 → commit → push`。

在 4 个进程共享同一个工作区时，这是**读-改-写竞态**：

- 两个 BA 同时读到"空闲"，各写一行，后写覆盖前写 → 一行凭空消失；
- 表里出现重复行，看起来像"一个人领了多个"；
- push 失败后重试，可能又写一遍。

结论：**共享表格不能作为并发认领的状态载体。**

## 3. 状态放文件，锁放内核

```text
<repo-root>/.aw/                 # 本地协调层（gitignore）
├── locks/claims.lock            # 全局写锁
├── claims/REQ-003.json          # 一个任务一个文件
├── sessions/<agent_id>.json     # pid / session / last_seen
├── queue.json                   # 待认领队列（有序）
└── archive/                     # 已释放的认领
```

- **互斥**：`msvcrt.locking`（Windows）/ `fcntl.flock`（POSIX）。进程退出自动释放，崩溃不留死锁。
- **一任务一文件**：认领 REQ-003 只写 `REQ-003.json`，物理上不可能覆盖别人的 REQ-004。
- **锁内窗口极短**：只保护「检查持有 → 选队首 → 写文件」，不做 git 操作。

## 4. 认领流程（工具已实现）

```text
claim next:
  1. 取全局锁
  2. 我这个 agent_id 已有 active 认领？ → ALREADY_HOLDING <REQ>，结束
  3. 清理死会话占用的认领（归档 + 退回队列）
  4. 从队列取第一个未被占用的 REQ，写 claims/<REQ>.json
  5. 释放锁
  6. git worktree add feature-REQ-xxx -b feature/REQ-xxx develop（失败重试 4 次）
  7. 写 feature-meta/manifest.json 并提交（记录谁领的）
  8. 输出 CLAIMED <REQ>
```

返回码固定，agent 按字符串分支，不解析自然语言：

| 输出 | 退出码 | 动作 |
|------|--------|------|
| `CLAIMED REQ-003` | 0 | 开始干活 |
| `ALREADY_HOLDING REQ-002` | 3 | 先做完手上的 |
| `TAKEN_BY ba-slot-2` | 3 | 换一个 |
| `QUEUE_EMPTY` | 3 | 等待 |
| `CLAIM_FAILED ...` | 1 | 看错误 |

## 5. 存活判定

优先看**长驻进程 pid**（`AW_AGENT_PID`，可选），其次看**心跳新鲜度**（默认 120 分钟）：

```text
session 文件里的 pid 还活着        → alive
last_seen 在 TTL 内                → alive
否则                                → dead（认领可被回收）
```

> 不要用「agent 每条命令的 pid」——那是短命子进程，命令结束就"死"了。
> 要么由启动器注入 `AW_AGENT_PID`，要么依赖心跳。

## 6. WIP 上限与例外

| 状态 | 占名额 | 说明 |
|------|--------|------|
| `active` | ✅ | 正在做 |
| `blocked` | ✅ | 等外部输入，仍归你 |
| `review` | ✅ | 已交 QA，等结果 |
| 释放 | — | `claim release` 后才能领下一个 |

**默认严格 1**。如果你的流程需要"1 个开发 + 1 个等待"，用 `blocked` 显式标记，
而不是偷偷再领一个——后者会让队列和看板全部失真。

> **当前实现说明**：CLI 只创建 `active`；`blocked` / `review` 还没有
> `claim block` / `claim review` 子命令，不要手工改 `.aw/claims/*.json`。
> `claim` 始终属于 BA；无状态 Dev 退出**不会**释放 WIP。

## 7. 巡检（doctor）

```bash
aw.py claim doctor          # 只报告
aw.py claim doctor --repair # 修复
```

检查项：

| 检查 | 处置 |
|------|------|
| 同一 agent 有多个 active | 保留最早，其余归档并退回队列 |
| 认领的会话已死 | 归档并退回队列 |
| 认领存在但 worktree 不存在 | 归档并退回队列 |
| worktree 存在但无认领 | 只报告（可能是历史遗留） |
| 队列空但有空闲 BA | 提示补需求 |

## 8. 仍然需要的 Git 纪律

即使认领有锁，**共享工作区**（4 个 BA 同一个 `BA/`）里还有两个坑：

1. **禁止 `git add -A` / `git add .`** —— 会把别人改到一半的文件一起提交。
   一律写明确路径：`git add BA/demands/REQ-003/`。
2. **提交带 pathspec**：
   ```bash
   git commit -m "[BA] REQ-003: 进行中→待验证 [session: ...]" -- BA/demands/REQ-003/
   ```
3. `.git/index.lock` 冲突是 fail-fast：捕获后 `git pull --rebase` 重试，不要直接放弃。

## 9. 编号与队列

- 编号仍用 `aw.py next-req` 计算，**不复用**。
- 队列来源：`aw.py queue add`（手工）或 `aw.py queue sync`（扫 `BA/demands/*/status.md` 里的"已就绪"）。
- BA **不挑任务**：从队首拿。挑任务会让 WIP 约束形同虚设。

## 10. 跨机怎么办

`.aw/` 是本机文件，跨机不可见。跨机协作时：

- 认领状态改为 git 分支承载（每次认领一次 commit + push），回到"用 push 冲突做锁"；
- 或者给每台机器分配 agent 槽位（`ba-a-1` / `ba-b-1`），机器间只共享 `queue.json` 的只读快照。

同机多进程是当前主场景，优先保证它简单可靠。
