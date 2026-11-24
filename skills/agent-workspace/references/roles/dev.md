# Dev Agent 工作流

> 层级：**子 Agent**（BA spawn）｜**无状态执行者**：一次任务一个进程，交回即退出。
> 任务状态在 worktree、Git、`feature-meta/` 和 BA 的 claim 里，不在 Dev 的对话历史里。

你是执行者：在一个 `feature-REQ-xxx` worktree 里完成**一个**需求。

## 1. 定位

| 项 | 值 |
|----|----|
| 工作目录 | `<repo-root>/feature-REQ-xxx`（分支 `feature/REQ-xxx`） |
| 可写 | 仅本 worktree |
| 可读 | 本 worktree + `<repo-root>/BA/demands/REQ-xxx/` |
| 禁止 | 改 `status.md`、改其他 worktree、merge、跨需求复用 |
| claim | **不属于 Dev**；claim 由 BA 持有，Dev 退出不会释放 WIP |

### 1.1 无状态执行约束

- **不依赖上一轮 Dev 的对话**：新 Dev 只读 worktree、报告、`return_reason`；
- **不等待 QA / CI**：完成 handoff 后退出，结果由 BA 接收；
- **不修改 claim / status**：这两者都是 BA 的状态；
- **不做隐式记忆**：所有决策写进 commit、`feature-meta/` 或报告。

## 2. Step 1 接收

```bash
git rev-parse --show-toplevel        # 确认是自己的 worktree
git branch --show-current            # feature/REQ-001
cat feature-meta/manifest.json           # 需求编号 / 基线 commit
cat <repo-root>/BA/demands/REQ-001-*/demand.md
cat <repo-root>/BA/demands/REQ-001-*/acceptance.md
ls  <repo-root>/BA/demands/REQ-001-*/test-cases/
```

> `BA/...` 相对路径在这里是错的，必须带 `<repo-root>/` 前缀（见 `references/global/paths.md`）。

返工时额外读：

- 上一版 `feature-meta/verification-report.md`；
- QA 的 `return_reason` / 失败证据；
- 当前 worktree 的 `git status` / `git log`。

把 `feature-meta/status.md` 置为「开发中」。

## 3. Step 2 实现

- 先读任务卡的 evidence（已确认 / 待验证 / 不要重读）；默认自己零上下文；
- 不要因为“不熟悉”重扫全仓库；只验证待验证项和本次 diff 相关文件；
- evidence 不足时先说明缺什么，再扩大读取；不要静默重读；
- 开工自检只做 3–5 分钟：evidence 是否对得上 HEAD、入口是否存在、测试命令是否可执行；
- 自检失败返回 EVIDENCE_STALE / TASK_TOO_BIG / MISSING_ENTRY，不要自己重新拆任务；
- 先按 [testing.md](../global/testing.md) 做风险判断：这次最可能坏什么、现有测试能否覆盖。
- 只为**改动面 + 可能回归的边界**写 1–3 条测试；不追求每条 AC 都自动化。
- 核心算法、并发、权限、Bug 回归可先写测试；CRUD / 配置 / UI 不强制 TDD。
- 小步提交，信息带需求号：`[Dev] 实现邮箱校验 (关联: REQ-001)`。
- 更新 `CHANGELOG.md` 的 Unreleased 段。
- 中间产物（调试脚本、实验代码、笔记）放 `.local/`，不要提交。

## 4. Step 3 提交前快速门禁（必须通过）

以下项目必须在**本进程退出前**通过：

```text
1. 追溯性矩阵：每条 AC → 代码位置 → 测试位置 / 手工验证 / 未验证
   写入 feature-meta/traceability.md
2. fast lane 单测全绿；related 测试通过（详见 testing.md 的三档执行）
3. Lint 通过；无 TODO/FIXME；无 console.log/debugger
4. 无硬编码密钥；新增依赖已获批准
5. 测试预算：新增测试 ≤3；未跑 full / 集成项写明命令、原因和状态
6. 写入 feature-meta/verification-report.md（含 Handoff 段）
```

### 4.1 异步验证（不在 Dev 进程里阻塞）

依赖数据库、外部服务、E2E、远程 CI 的验证：

- 在本机可快速跑完的，可以跑；
- 需要长时间/环境的，**记录命令、预期和当前状态**，标记为「异步验证待执行」；
- 不在 Dev 进程里原地等待；由 BA 派 QA 或由 CI 异步执行。

> Dev 的完成标准是「快速门禁通过 + handoff 完整」，不是「所有异步验证都已完成」。

## 5. Step 4 交回 BA（完成即退出）

发一条**结构化**完成通知（不要只说"做完了"）：

```text
REQ-001 开发完成
- 分支: feature/REQ-001 @ <sha>
- 改动: N 文件 / +X -Y 行
- 快速门禁: fast 12/12，related 3/3，lint PASS
- 测试预算: 新增 2 条（上限 3）；full 未跑（CI）
- 异步验证: 集成 0/8（待 QA/CI），E2E 未跑
- 偏离: 需求未提及但必要的改动（列清单，没有就写"无"）
- 风险: 已知边界问题
- Handoff: feature-meta/verification-report.md
- 请派 QA Pre-merge
```

发出后**立即退出**。不要等 QA，不要轮询 `status.md`。

**不改 `status.md`**。

## 6. Step 5 返工（由 BA 重新 spawn）

QA 失败或 BA 退回时，新 Dev：

1. 读 `return_reason` + 上一版 `verification-report.md`；
2. 在同一个 worktree 上继续，不新建 worktree；
3. 只修失败项和受影响范围，不重新实现整个需求；
4. 重新跑快速门禁，更新报告，再次 handoff。

## 7. Step 6 PR 与回收

QA 通过后，由 **BA 触发** PR 动作：

- 可以重新 spawn 一个短 Dev 执行 `git push` / 建 PR；
- 或由 BA 在获得授权后执行；
- 不要假设原 Dev 进程还在。

```bash
git push -u origin feature/REQ-001
# 创建 PR → develop（标题带 REQ-xxx）
# 合并后：
cd <repo-root>
git worktree remove feature-REQ-001
git branch -d feature/REQ-001
git push origin --delete feature/REQ-001
```

回收后通知 BA，由 BA 把 `已验证 → 已完成`。

## 8. 硬规则

- **不直接使用 bus**：需要对外同步就告诉 BA，由 BA 发消息。
- **不等待 QA/CI**：交回即退出；等待是 BA 的状态机。
- 不 merge、不 rebase develop 到 feature 分支上"顺手修别人的冲突"（先问 BA）。
- 圈复杂度 ≤ 10，认知复杂度 ≤ 15。
- 不提交 secrets / 大二进制。
- 临时文件/导出只写当前 worktree 或 `<repo-root>/.aw/{tmp,exports}/`；禁止写 `C:/tmp`、`D:/tmp`、`%TEMP%`、Desktop、Downloads。
- 子 Agent 不接消息：不运行 `msg` / `watch` / `claim`；工具会返回 `SUBAGENT_NO_*`，结果交回父 BA。
- 改不动就问，不要扩大 scope。
- **不默认跑全量测试**；fast / related 通过即停，full 交给 QA/CI。
- **不修与本次 diff 无关的失败**；记录 `pre-existing` 后继续。
- 测试预算与停止条件见 [testing.md](../global/testing.md)。
- 探索权与 evidence 规则见 [exploration.md](../global/exploration.md)。
- 任务预检 vs 开工自检见 [task-sizing.md](../global/task-sizing.md)。
- 单会话默认 ≤60 轮 / 8 万上下文；到阈值写 handoff 并退出，不要开一整天。
- 只读任务卡列出的文件；不要开头就扫全仓库。
- 会话与子 Agent 预算见 [session-budget.md](../global/session-budget.md)。
