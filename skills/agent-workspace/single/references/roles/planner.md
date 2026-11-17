# Planner（可选）

> 层级：独立会话（可选）｜只写 docs 的规划文件｜不领 claim、不写 status、不写代码。

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
