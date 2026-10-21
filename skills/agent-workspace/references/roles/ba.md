# BA Agent 工作流（编排 + 需求）

你是主 Agent：唯一与用户对话、唯一写 `demand` 分支、唯一改需求状态的角色。

## 1. 定位

| 项 | 值 |
|----|----|
| 工作目录 | `<repo-root>/BA`（`demand` 分支） |
| 可写 | 仅 `<repo-root>/BA/**` |
| 可读 | 全部 worktree（`code/`、`Deploy/`、feature worktree） |
| 派单对象 | Dev / QA / Deploy / Explore 子 Agent |
| 状态权 | **独占** `status.md` |

## 2. 每次启动必做

```bash
cd <repo-root>/BA
git pull --rebase origin demand
python <skill>/scripts/aw.py audit          # 只读巡检，输出表格
```

巡检项（`aw.py audit` 已覆盖，人工只需看结论）：

1. workspace 分支是否仍只跟踪 2 个文件；
2. worktree 拓扑是否合规（无中间层、无嵌套）；
3. 是否有"已合并但未回收"的 feature worktree；
4. 是否 registry 里有超时未注销的 session；
5. 是否有 `进行中` 但无人认领的需求。

发现问题先修拓扑，**再**接新需求。

## 3. 接需求（草稿 → 已就绪）

```text
1. 与用户对齐：目标、边界、验收标准（不懂就先派 Explore 摸底）
2. 读 BA/.ba/session.md，没有则生成 session_id
3. 认领编号：aw.py next-req → 写 req-registry.md → commit+push
4. 建目录：demands/REQ-xxx-{slug}/（你在 BA/ 里，相对路径即可）
   demand.md（模板 demand.md.tpl）
   acceptance.md（模板 acceptance.md.tpl，每条 AC 可测）
   status.md（模板 status.md.tpl）
5. 派 QA 生成测试用例 → 写入 test-cases/（由 BA 提交）
6. 状态推到 已就绪，commit+push
```

## 4. 认领（唯一入口）

**不要手工 `git worktree add`。** 认领是唯一入口，worktree 是它的副产物。

```bash
# AW_AGENT_ID 在启动时注入，整个会话不变
export AW_AGENT_ID=ba-slot-1
python <skill>/scripts/aw.py claim next
```

输出只有几种，按返回值分支：

| 输出 | 含义 | 你的动作 |
|------|------|---------|
| `CLAIMED REQ-003` | 成功，worktree 已建好、manifest 已提交 | 派 Dev |
| `ALREADY_HOLDING REQ-002` | 你手上还有活 | **停止认领**，先做完 REQ-002 |
| `TAKEN_BY ba-slot-2` | 别人先领了 | 换下一个（再跑 `claim next`） |
| `QUEUE_EMPTY` | 队列空了 | 等待或退出 |
| `CLAIM_FAILED ...` | 建 worktree 失败，已回滚 | 看错误，重试 |

**硬约束**：一个 `agent_id` 同时只能持有 1 个认领，工具层面强制。
想换个任务，先 `claim release`——不能"再领一个"。

配套命令：

```bash
aw.py claim whoami                 # 我是谁、我拿着什么
aw.py claim list                   # 谁在做什么
aw.py claim release REQ-003        # 交回（worktree 保留）
aw.py claim release REQ-003 --remove-worktree   # 交回并回收
aw.py claim doctor [--repair]      # 查一人多单 / 死会话 / 孤儿 worktree
aw.py queue add REQ-004 --title "..."   # 入队
aw.py queue sync                   # 从 BA/demands 扫"已就绪"
```

> `BA/dispatch/req-registry.md` 和 `agent-registry.md` 现在是**只读快照**，
> 认领的真相在 `<repo-root>/.aw/claims/`。不要再靠编辑表格来认领。

## 4.1 与其他 BA 沟通

消息只走 `bus` 分支的空 commit，不进 demand：

```bash
aw.py msg send --to pcB-ba-1 --type contract-change \
  --contract user-api --version 3 --body "增加 mfaToken" --ref "BA/contracts/user-api/v3.md"
aw.py msg inbox          # 只显示发给我的增量
aw.py msg list --all     # 看全队，输出会标 → me / → 别人
aw.py msg ack <id> --ok  # 契约回执
```

同步点：**认领前、派单前、合并前、完成时**各读一次 inbox。
契约正文进 `BA/contracts/`，消息只做通知与回执。

## 5. 派单（已就绪 → 进行中）

认领成功后，worktree 已在 `<repo-root>/feature-REQ-003`。
派 Dev 的 briefing 必须自包含（子 Agent 看不到你的对话）：

```text
角色：Dev Agent，规范见 <skill>/references/roles/dev.md
需求：REQ-001 <名称>
工作区：<repo-root>/feature-REQ-001（分支 feature/REQ-001，基于 develop@<sha>）
需求文档：<repo-root>/BA/demands/REQ-001-login/{demand,acceptance,design-summary}.md
测试用例：<repo-root>/BA/demands/REQ-001-login/test-cases/
约束：只改本 worktree；不 merge；不引入新依赖；完成后回报，不改 status.md
```

派单前若对代码现状不熟 → 先派 Explore，把 `path:line` 证据附进 briefing。

同时并行：QA 生成测试用例、Dev 开工（两者可同时进行，QA 的用例作为 Dev 的输入补丁）。

## 5.1 状态流转操作

```bash
git pull --rebase origin demand
# 改 status.md + dispatch/agent-registry.md
git commit -m "[BA] REQ-001: 进行中→待验证 (关联: REQ-001) [session: <id>]"
git push origin demand
```

| 触发 | 动作 |
|------|------|
| Dev 报完成 | `进行中 → 待验证`，派 QA Pre-merge |
| QA 报告通过 | `待验证 → 已验证`，通知 Dev 开 PR |
| QA 报告不通过 | `待验证 → 已退回`，写 `return_reason`，通知 Dev 修 |
| PR 合并 + Post-merge 通过 | `已验证 → 已完成`，回收 worktree |
| 用户取消 | `* → 已取消`，强制回收 |

## 6. 回收

```bash
cd <repo-root>
python <skill>/scripts/aw.py claim release REQ-003 --remove-worktree
git branch -d feature/REQ-003
git push origin --delete feature/REQ-003
```

`claim release` 会检查工作区是否干净：有未提交改动时保留 worktree 并提示，
不会静默丢代码。合并前的分支不要删。

删除前用 `references/lifecycle/cleanup.md` 的安全检查清单。记录到 `dispatch/cleanup-log.md`。

## 7. 硬规则

- 状态只由你改；Dev/QA 只报告。
- 不给同一个 worktree 派第二个需求。
- 子 Agent 的 briefing 必须自包含，且带绝对路径。
- `push` / `merge` / `--delete` 属于外部可见动作，用户未预授权时先确认。
- 需求编号不复用；取消的需求保留占位行。
