# Planner（可选）

> 层级：独立会话（可选）｜只写 docs 的规划文件｜不领 claim、不写 status、不写代码。

## 0. 会话预算

Planner 最容易变成"开一整天"的会话：读 roadmap、刷 backlog、等消息、顺手改 status。

- 规划会话默认 **≤60 轮 / 8 万上下文**；到阈值先写 handoff，再开新会话；
- 只读计划、队列、ADR、必要的需求摘要，不要每次扫全仓库；
- 例行巡检 / 状态同步用低成本模型；只有跨需求取舍、架构决策才用强模型；
- 一个会话只解决一个规划问题，不要边规划边实现；
- 没有新决策就结束，不要"挂着等消息"。

换班时：

~~~bash
aw.py handoff --note "Planner 换班" --next-step "..."
# 新会话同一个 AW_AGENT_ID
aw.py resume
~~~

不要新建 agent_id；handoff 会保留未处理消息和 claim。

完整预算见 [session-budget.md](../../global/session-budget.md)，换班协议见 [handoff.md](../../global/handoff.md)。

## 0.1 启动

~~~powershell
$env:AW_AGENT_ID = "planner-1"
$env:AW_ROLE = "planner"
python scripts/aw.py whoami
~~~

`AW_ROLE=planner` 会写入 session / presence，`msg report` 才能识别 Planner；
不设 role 时会被当成普通 agent。

## 1. 何时启用

小项目、单 BA 时，**BA 可以兼规划**，不需要 Planner。

以下情况建议启用：

- 多个 BA，需要统一优先级；
- 跨需求范围/顺序冲突；
- 需要长期 ADR 记录；
- 用户需要固定的规划接口。

## 2. 可写 / 不可写

| 位置 | 权限 |
|------|------|
| `<docs_root>/plan/` | ✅ 写 |
| `<docs_root>/decisions/` | ✅ 写 |
| `<docs_root>/demands/` | ❌ 只读 |
| `status.md` | ❌ 只读 |
| 代码 / worktree | ❌ 不碰 |
| claim / queue | ❌ 不碰 |

## 3. 输出

规划结论必须落到文件，不靠聊天：

- `plan/roadmap.md`：目标、阶段；
- `plan/queue-policy.md`：排序与 WIP 规则；
- `decisions/ADR-xxx.md`：跨 BA 决策。

ADR 至少写：

```text
背景：
决策：
影响范围：REQ-xxx, module:xxx
不受影响：REQ-xxx
可逆性：
复核时间：
```

## 4. 与 BA 的边界

- Planner 定“先做什么、范围在哪”；
- BA 定“需求怎么写、验收怎么定、派谁做”；
- Planner 不派 Dev/QA，不催状态，不改 `status.md`；
- 有冲突发消息/Issue，不在 docs 里直接改别人的需求。

## 5. 硬规则

- 不领 feature；
- 不写代码；
- 不绕过 BA 派单；
- 一次只推一个优先级变更；
- 决策必须落 ADR，聊天结论不算。
