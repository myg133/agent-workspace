# 单机工作流

## 1. 角色

| 角色 | 职责 |
|------|------|
| Planner（可选） | 优先级、跨 BA 边界；首版不强制 |
| BA | 需求、验收、状态；唯一写 docs 状态的人 |
| Dev | 在 feature worktree 实现，handoff 后退出 |
| QA | 只读验证，报告交 BA |

没有 Deploy 角色；部署继续用现有流程。

## 1.1 角色不是进程层级

角色是**权限契约**，不是“必须由 BA spawn 的子进程”。

- 单机小项目可以由同一个人/同一个 agent 切换角色；
- 但 QA 的独立性会下降，**建议至少 QA 使用独立会话**；
- 技术约束仍然是：BA 写 status、Dev 只写 worktree、QA 只读不提交；
- `aw_single.py` 不检查父子进程关系，只看 `agent_id` / 可选 `AW_ROLE`。

## 2. BA

1. 在 docs 仓库创建 `demands/REQ-xxx/`；
2. 写 `demand.md` / `acceptance.md` / `status.md`；
3. `aw_single.py queue add REQ-xxx`；
4. `aw_single.py claim next`；
5. 把 worktree 路径、docs 路径、base sha 交给 Dev。

## 2.0 接用户任务先报备

用户直接把任务交给 BA 时，BA 先报备，再 claim / 实现。

~~~bash
python scripts/aw_single.py msg report \
  --subject "用户新任务：REQ-001" \
  --body "来源：用户直接指派；目标：...；优先级：...；预期：..."
~~~

行为：

- 有 online Planner → 只发 Planner；
- 没有 online Planner → 广播给所有 online agent（排除自己）；
- 默认 type=fyi、expect=none；
- 报备不是 claim 的前置门禁，但必须先留下记录。

## 2.1 异常：分支/worktree 被占用

如果子 Agent 先认领了，claim 仍属于它：

~~~bash
# 优先让子 Agent 自己释放
$env:AW_AGENT_ID='<子 agent id>'
python scripts/aw_single.py claim release REQ-001

# 或者 BA 强制释放（只释放 claim，不删 worktree）
$env:AW_AGENT_ID='ba-1'
python scripts/aw_single.py claim release REQ-001 --force
~~~

如果 claim 已经不在了，但分支/worktree 还在（孤儿 worktree），不要先删：

~~~bash
python scripts/aw_single.py claim adopt REQ-001 --branch feature/REQ-001
~~~

`claim adopt` 会：

- 保留 worktree 里的未提交改动；
- 把 claim 转给当前 BA；
- 把队列里的 REQ 移除；
- 不重建分支，不丢现场。

之后正常让 Dev 在该 worktree 继续，QA 验证，BA 合并/回收。
## 3. Dev

1. 只读 docs；
2. 在 worktree 实现；
3. 按 `testing.md` 的预算写 1–3 条目标/回归测试；
4. 跑 fast / related 快速门禁（不默认跑 full）；
5. 写 `feature-meta/verification-report.md`；
6. 发 handoff，退出；
7. 不等 QA，不修改 docs 的 `status.md`。

## 4. QA

1. 只读 docs + worktree；
2. 先 related；full 只在 merge 前跑一次；
3. 审查测试有效性 + 测试套件成本（慢/重复/实现耦合/flaky）；
4. 报告交 BA；
5. 不提交、不改状态、不替 Dev 补测试。

## 4.1 测试克制

测试按风险测，不按覆盖率测。默认预算：

- 每个任务新增测试 ≤3；Bug 修复 1 条回归；重构 0 条；
- Dev 只跑 fast / related；full 交给 QA / CI；
- 不测未改动代码、第三方库、私有实现、日志/文案/格式；
- 目标测试 + related 通过即停止，不补覆盖率；
- 无关失败记录 `pre-existing`，不修。

完整规则、失败分诊、测试审计和度量见 [testing.md](../global/testing.md)。

## 4.2 会话与子 Agent 预算

- 主会话默认 ≤60 轮 / 8 万上下文；到阈值先 handoff，再开新会话；
- 一个 REQ 最多 2–3 个子 Agent；**没有 diff 预期的任务不 spawn**；
- 探索 / 文档 / status 用低成本模型，复杂实现 / 关键 review 才用强模型；
- 单会话只做一个阶段，不要从探索一路做到上线；
- 常驻 BA / Planner 换班用：

  ~~~bash
  aw_single.py handoff --note "换班" --next-step "..."
  # 新会话：同一个 AW_AGENT_ID + 显式 AW_SESSION_ID
  aw_single.py whoami
  aw_single.py resume
  ~~~

- 完整规则、会话任务卡、度量与反模式见 [session-budget.md](../global/session-budget.md)，换班协议见 [handoff.md](../global/handoff.md)。

## 4.3 探索权唯一

- BA 只做业务/验收/文档/接口探索；代码探索交给 Dev；
- 一个任务只有一个代码探索 owner；
- fresh 子 Agent 默认零上下文，任务卡必须带 evidence（已确认/待验证/不要重读）；
- QA 验证 diff/AC，不重新探索架构；
- 规则与模板见 [exploration.md](../global/exploration.md)。

## 4.4 任务预检与开工自检

- BA 下派前判断模块/文件/AC/依赖/预算；太大就拆；
- 子 Agent 只做开工自检：evidence 对 HEAD、入口存在、测试命令可执行；
- 自检失败返回 EVIDENCE_STALE / TASK_TOO_BIG / MISSING_ENTRY，不自己重新拆；
- 第一次 compaction 就停，不要连续压缩；
- 规则见 [task-sizing.md](../global/task-sizing.md)。

## 5. 返工

- BA 在 docs 的 `status.md` 写 `return_reason`；
- BA spawn 新 Dev；
- 新 Dev 只读上一版报告 + return_reason，继续同一 worktree。

## 6. 消息与唤醒

本地消息，不走 bus，不写 git：

```text
.aw/
├── inbox/<agent>/<id>.json
├── msg-read/<agent>.json
├── wake/<agent>.json
└── watch-state.json
```

```bash
aw_single.py msg send --to ba-1 --type question --body "这个接口用 v2 吗？"
aw_single.py msg inbox
aw_single.py msg ack <id>
aw_single.py msg wait --timeout 120
aw_single.py watch --ensure --exec "bash start-agent.sh"
```

- `msg send/inbox/ack/wait`：同机通信，原子文件，无网络；
- `watch`：扫描未读消息，写 `.aw/wake/<agent>.json`；
  - `--exec` 可拉起 agent 进程；
  - `--ensure` 后台常驻，`--status` / `--stop` 管理；
  - 每次只写消息摘要（id/from/type/expect），不写正文；
- 需要审计的决策仍写 docs 的 `decisions.md`，消息只是通知。

## 7. 状态

docs 的 `status.md` 仍是唯一事实：

```text
草稿 → 已就绪 → 进行中 → 待验证 → 已验证 → 已完成
```

`aw_single.py` 不写 status，只负责 claim/worktree。
