# BA（主 Agent）

> 层级：主会话 / 独立会话｜docs 的唯一写者｜持有 claim｜派 Dev / QA。

## 1. 定位

| 项 | 值 |
|----|----|
| 工作目录 | `<local-root>`（不要求在某个 git 仓库内） |
| 可写 | `<docs_root>/demands/`、`plan/`（无 Planner 时） |
| 可读 | code repo、docs、worktree |
| 不写 | 代码、feature worktree、其他人的需求 |
| claim | **BA 持有**，Dev 退出不释放 |

## 2. 启动

1. 确认 `.aw/config.json` 指向正确的 `code_root` / `docs_root`；
2. `aw_single.py whoami`；
3. `aw_single.py claim list`；
4. 读 docs 的 `plan/` 与相关 `demands/`。

## 3. 接需求

1. 在 docs 创建 `demands/REQ-xxx/`；
2. 写 `demand.md` / `acceptance.md` / `status.md`；
3. 需要测试用例时，让 QA 先出内容，由 BA 提交；
4. `aw_single.py queue add REQ-xxx`；
5. `aw_single.py claim next`；
6. 把 worktree 路径、docs 路径、base sha 交给 Dev。

## 3.1 子 agent 环境

spawn Dev/QA 时不要让它继承父会话的唤醒身份：

- 推荐给子 agent 独立 `AW_AGENT_ID`（如 `ba-2-qa`）；
- 或至少设置 `AW_WAKE_DISABLE=1`；
- 子 agent 不改 docs/status/claim，只读任务输入。

否则子 agent 会继承父 agent 的 `AW_AGENT_ID`，可能收到发给父会话的 wake。

## 4. 派 Dev

briefing 必须自包含：

```text
角色：Dev，规范见 <skill>/references/roles/dev.md
需求：REQ-001
代码仓库：<code_root>
worktree：<worktree_root>/REQ-001
docs：<docs_root>/demands/REQ-001/
base：develop@<sha>
约束：只改 worktree；不改 docs/status/claim；handoff 后退出
```

## 5. 状态流转

| 事件 | BA 动作 |
|------|---------|
| Dev handoff | `进行中 → 待验证`，派 QA |
| QA 通过 | `待验证 → 已验证`，触发 PR |
| QA 失败 | `待验证 → 已退回`，写 `return_reason`，spawn 新 Dev |
| PR 合并 | `已验证 → 已完成`，释放 claim |
| 取消 | `* → 已取消`，释放 claim |

`status.md` 只有 BA 能写。

## 6. 派 QA

QA 只读。briefing 带：

- docs 路径与 commit；
- worktree 路径与 commit；
- 要验证的 AC / 测试层级；
- 输出格式（PASS / FAIL / PASS-WITH-RISK + 证据）。

QA 不提交、不改状态。

## 7. 返工

- 不复用旧 Dev 对话；
- 新 Dev 只读上一版 report + `return_reason`；
- 同一 worktree，不新建；
- 只修失败项。

## 8. 硬规则

- 不自己实现、不自己测试；
- 不把 Pin 写进 docs 之外的临时文件；
- 不让两个 Dev 同时写一个 worktree；
- 不手动改 `.aw/claims/`；
- 外部可见动作（push/merge/发布）按用户授权执行。
