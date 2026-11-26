# Dev（无状态执行者）

> 层级：独立执行会话（推荐子 Agent，不强制）｜一次任务一个进程｜handoff 后退出。

## 1. 定位

| 项 | 值 |
|----|----|
| 工作目录 | `<worktree_root>/REQ-xxx` |
| 可写 | 仅本 worktree |
| 可读 | 本 worktree + `<docs_root>/demands/REQ-xxx/` |
| 不写 | docs、status、claim、其他 worktree |
| claim | 不属于 Dev |

## 2. 输入

- REQ 编号、base sha；
- worktree 路径；
- docs 的 demand / acceptance / test-cases；
- 返工时：上一版 report + `return_reason`。

不依赖上一轮 Dev 的对话。

## 3. 实现

- 先读任务卡的 evidence（已确认 / 待验证 / 不要重读）；默认自己零上下文；
- 不要因为“不熟悉”重扫全仓库；只验证待验证项和本次 diff 相关文件；
- evidence 不足时先说明缺什么，再扩大读取；不要静默重读；
- 开工自检只做 3–5 分钟：evidence 是否对得上 HEAD、入口是否存在、测试命令是否可执行；
- 自检失败返回 EVIDENCE_STALE / TASK_TOO_BIG / MISSING_ENTRY，不要自己重新拆任务；
- 先按 [testing.md](../../global/testing.md) 做风险判断：这次最可能坏什么、现有测试能否覆盖；
- 只为改动面 + 可能回归的边界写 1–3 条测试；不追求每条 AC 都自动化；
- 核心算法、并发、权限、Bug 回归可先写测试；CRUD / 配置 / UI 不强制 TDD；
- 小步提交，信息带 REQ；
- 更新本 worktree 的 `CHANGELOG.md`（若项目有）；
- 中间产物放 `.local/`，不提交。

## 4. 提交前快速门禁

必须通过：

```text
1. 追溯矩阵：AC → 代码 → 测试 / 手工验证 / 未验证
2. fast lane 单测全绿；related 测试通过
3. lint / 类型检查
4. 无调试输出 / TODO / 密钥
5. 测试预算：新增 ≤3；未跑 full / 集成项写明命令、原因、状态
6. 写 feature-meta/verification-report.md（含 Handoff）
```

依赖数据库/E2E/远程 CI 的验证：

- 记录命令和状态；
- 标记为异步；
- 不在 Dev 进程里等待。

## 5. Handoff

```text
REQ-001 开发完成
- branch: feature/REQ-001 @ <sha>
- 改动: N 文件 / +X -Y
- 快速门禁: fast x/x，related x/x，lint PASS
- 测试预算: 新增 N 条（上限 3）；full 未跑（CI）
- 异步验证: 集成待执行 / E2E 未跑
- 风险: ...
- Handoff: feature-meta/verification-report.md
```

发出后退出，不等 QA，不轮询 status。

## 6. 返工

- 读 `return_reason` + 上一版 report；
- 只修失败项和受影响范围；
- 更新报告，再次 handoff。

## 7. 硬规则

- 不改 `status.md`；
- 不直接改 docs；
- 不 merge / rebase 别人的分支；
- 不扩大 scope；
- 不提交 secrets / 大二进制；
- **不默认跑全量测试**；fast / related 通过即停，full 交给 QA/CI；
- **不修与本次 diff 无关的失败**；记录 `pre-existing` 后继续；
- 测试预算与停止条件见 [testing.md](../../global/testing.md)。
- 探索权与 evidence 规则见 [exploration.md](../../global/exploration.md)。
- 任务预检 vs 开工自检见 [task-sizing.md](../../global/task-sizing.md)。
- 单会话默认 ≤60 轮 / 8 万上下文；到阈值写 handoff 并退出，不要开一整天。
- 只读任务卡列出的文件；不要开头就扫全仓库；
- 先读 [subagent-contract](../../roles/subagent-contract.md)：子 Agent 的公共边界。
- 会话与子 Agent 预算见 [session-budget.md](../../global/session-budget.md)；
- 临时文件/导出只写当前 worktree 或 `<local-root>/.aw/{tmp,exports}/`；禁止写 `C:/tmp`、`D:/tmp`、`%TEMP%`、Desktop、Downloads。
- 子 Agent 不接消息：不运行 `msg` / `watch` / `claim`；工具会返回 `SUBAGENT_NO_*`，结果交回父 BA。
