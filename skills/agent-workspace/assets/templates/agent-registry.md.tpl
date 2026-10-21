# BA Agent 注册表（只读快照）

> 1.3 起**不再用于认领**：任务归属以 `<repo-root>/.aw/claims/` 为准，本表仅供人阅读。
> 生成方式：`aw.py claim list`。

> 由每个 BA 在**首次写操作**时自动注册（懒注册），后续每次 commit 更新 `last_seen`。
> 超过 120 分钟无 commit 视为 `stale`；接管需人工确认。

| session_id | host | role | status | started_at | last_seen |
|------------|------|------|--------|------------|-----------|
| _（示例）ba-mbp-20261021143022-a1b2 | macbook | ba | online | 2026-10-21 14:30 | 2026-10-21 14:35 |

状态取值：`online` / `stale` / `offline` / `archived`。

> 追加行，不改历史行；状态变化就地更新该行。
