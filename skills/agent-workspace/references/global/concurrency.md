# 多 BA 并发协作

## 1. 为什么需要它

多个 BA Agent 同时改 `demand` 分支 → 必须有一个协调原语。这里用 **Git 本身**：

> push 的原子性是锁，pull --rebase 是重试，commit trailer 是日志。

不引入数据库、不引入锁服务。

## 2. Session ID

格式（**不含 pid**，进程重启不应换身份）：

```text
{role}-{host}-{YYYYMMDDHHmmss}-{rand4}
例：ba-macbook-20261021143022-a1b2
```

会话开始时生成一次，写入 `BA/.ba/session.md`（不跟踪）：

```markdown
# Session
- session_id: ba-macbook-20261021143022-a1b2
- started_at: 2026-10-21 14:30:22
- role: ba
```

## 3. 懒注册（注册绑定在第一次写操作中）

不存在"先注册再干活"的独立步骤 —— 那样一定有人忘。注册是写操作的前置片段：

```text
1. git pull --rebase origin demand
2. 读 BA/.ba/session.md 取 session_id
3. registry 里没有本 session → 追加一行（status=online）
   registry 里已有            → 更新 last_seen（心跳）
4. 执行真正的修改
5. git add <改的文件> BA/dispatch/agent-registry.md
6. git commit -m "[BA] {描述} [session: {id}]"
7. git push origin demand → 失败 → pull --rebase → 重试（≤3 次，退避 2/4/8s）
```

注册与业务改动在**同一个 commit** 里，因此无法跳过。

## 4. 心跳与 stale

| 项 | 值 |
|----|----|
| 心跳来源 | 每次对 `demand` 的 commit（同 commit 内更新 registry） |
| 心跳备份 | `git log --format=%ct --grep="\[session: <id>\]" -1` |
| 判定阈值 | 默认 **120 分钟**无 commit → `stale`（可配） |
| 判定者 | 任意 BA 巡检时 |
| 接管 | **必须人工确认**，不自动抢占 |

> 阈值别设太小：一次需求澄清 + 方案讨论很容易超过 30 分钟。以"会不会误判"为优先，而不是"看起来更实时"。

## 5. REQ 编号认领

```text
1. git pull --rebase origin demand
2. python .../aw.py next-req          # 读出当前最大号 + 1
3. 在 BA/dispatch/req-registry.md 追加：
   | REQ-004 | 登录限流 | ba-...-a1b2 | 2026-10-21 14:35 |
4. commit + push
   push 被拒 → 说明别人抢了同一个号 → pull → 换 next-req 重来（≤3 次）
5. 认领成功后才创建 worktree
```

**编号永不复用**，取消的需求保留占位行（状态列写 `cancelled`）。

## 6. 并发上限

| 活跃 BA 数 | 策略 |
|-----------|------|
| ≤ 3 | 共享编号空间，靠 push 冲突协调 |
| > 3 | 改用号段：BA-A 用 001-099，BA-B 用 100-199… 号段写进 `req-registry.md` 表头 |

超过 3 个 BA 还在抢同一个号，重试成本会超过收益。

## 7. 冲突处理

- **只改不同文件** → `pull --rebase` 自动过。
- **同改 `agent-registry.md`** → 以 `last_seen` 较新者为准，保留双方行。
- **同改 `req-registry.md`** → 双方都要保留，编号冲突时序号大的一方改用下一个可用号。
- **`status.md` 冲突** → 这不该发生（单一写入者）；若发生，说明有人绕过规范，按 `git log` 时间取后者，并在 `decisions/` 记一条。
