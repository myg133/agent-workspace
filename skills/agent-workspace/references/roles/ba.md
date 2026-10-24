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

## 1.1 注册自己（每个 agent 第一次启动）

BA **自己注册**，不需要 Planner 代劳：

```text
agent_register {"name": "pcA-ba-1", "role": "ba"}
# REGISTERED pcA-ba-1 (ba, pending)
# TOKEN pcA-ba-1 3f9c...
```

- **solo 模式**（没有 active Planner）：直接 `active`；
- **team 模式**：先 `pending`，Planner 执行 `agent_activate` 后才能收发消息；
- 记下 `TOKEN`，后续调用带上（或设 `AW_AGENT_TOKEN`）；
- 名字已被占用时，重新注册需要本人 token 或 Planner token。

## 1.2 默认自决（防止变笨）

**你是需求所有者，细节默认你拍板。** Planner 只定顺序、跨 BA 边界、不可逆事项。

| 你决定 | 你升级 |
|--------|--------|
| 字段名、错误码、重试、日志 | 跨 BA 契约冲突 |
| 验收标准、测试数据 | 优先级 / 范围变更 |
| 需求拆分、内部先后 | 数据迁移 / 公开 API 等不可逆 |
| 单 REQ 技术选型（约束内） | 文档互相矛盾 |

- 问之前先查 `plan/roadmap.md`、`plan/queue-policy.md`、`decisions/`；
- 升级必须带 **proposal + default**（2 小时无回复就按 default 执行）；
- 自决结果写进 `decisions.md`，Planner 周检，不逐条审批。

详见 `references/global/decision-rights.md`。

## 2. 每次启动必做

> 本角色通过 MCP 调用工具，示例写作 `工具名 {参数}`。
> CLI 等价命令见 `references/global/mcp.md`；agent 不要 shell 调 `aw.py`。

```text
git pull --rebase origin demand   # git 仍用命令行
audit {}
```

巡检项（`audit` 已覆盖，人工只需看结论）：

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
3. 认领编号：next_req {} → 写 req-registry.md → commit+push
4. 建目录：demands/REQ-xxx-{slug}/（你在 BA/ 里，相对路径即可）
   demand.md（模板 demand.md.tpl）
   acceptance.md（模板 acceptance.md.tpl，每条 AC 可测）
   status.md（模板 status.md.tpl）
   decisions.md（模板 decisions.md.tpl，BA 自决记录）
5. 派 QA 生成测试用例 → 写入 test-cases/（由 BA 提交）
6. 状态推到 已就绪，commit+push
```

## 4. 认领（唯一入口）

**不要手工 `git worktree add`。** 认领是唯一入口，worktree 是它的副产物。

```text
claim_next {}
```

身份来自 MCP 调用的 `agent_id` + `token`（桌面端每次带；终端启动可继承 `AW_AGENT_ID`）。

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

```text
agent_whoami {}
claim_list {}
claim_release {"req": "REQ-003"}
claim_release {"req": "REQ-003", "remove_worktree": true}
claim_doctor {"repair": false}
queue_add {"req": "REQ-004", "title": "..."}
queue_sync {}
```

> `BA/dispatch/req-registry.md` 和 `agent-registry.md` 现在是**只读快照**，
> 认领的真相在 `<repo-root>/.aw/claims/`。不要再靠编辑表格来认领。

## 4.1 与其他 BA 沟通

消息只走 `bus` 分支的空 commit，不进 demand：

```text
msg_send {"to": "pcB-ba-1", "type": "contract-change",
          "contract": "user-api", "version": "3",
          "body": "增加 mfaToken", "ref": "BA/contracts/user-api/v3.md"}
msg_inbox {}
msg_list {"all": true}
msg_ack {"id": "<id>"}
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

```text
claim_release {"req": "REQ-003", "remove_worktree": true}
git branch -d feature/REQ-003
git push origin --delete feature/REQ-003
```

`claim release` 会检查工作区是否干净：有未提交改动时保留 worktree 并提示，
不会静默丢代码。合并前的分支不要删。

删除前用 `references/lifecycle/cleanup.md` 的安全检查清单。记录到 `dispatch/cleanup-log.md`。

## 6.1 与 Planner 的分工

- **Planner 定方向**：优先级、范围、跨 BA 契约方向、容量。
- **你定落地**：需求文档、验收标准、派单、状态。
- Planner 的结论看 `BA/plan/queue-policy.md` 与 `BA/decisions/`；
  有异议在 bus 上发 `type: question`，**必须带 proposal + default**，不要私下改 `demand.md` 绕过。
- 你**不改** `plan/`，Planner **不改** `status.md`。

## 7. 硬规则

- 状态只由你改；Dev/QA 只报告。
- 不给同一个 worktree 派第二个需求。
- 子 Agent 的 briefing 必须自包含，且带绝对路径。
- `push` / `merge` / `--delete` 属于外部可见动作，用户未预授权时先确认。
- 需求编号不复用；取消的需求保留占位行。
