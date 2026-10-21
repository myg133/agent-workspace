# 回收 / 巡检日志

格式：`{日期} | {对象} | {类型} | {详情} | {执行者}`

| 日期 | 对象 | 类型 | 详情 | 执行者 |
|------|------|------|------|--------|
| _（示例）2026-10-21 | workspace-audit | clean | 无违规 | ba-a1b2 |
| _（示例）2026-10-21 | REQ-001 | merged-cleanup | worktree + branch removed | dev-c3d4 |

类型：`workspace-audit` / `merged-cleanup` / `cancelled` / `forced` / `violation-fixed`。
