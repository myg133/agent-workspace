# Planner（总规划 / 设计 / 协调）

## 1. 定位

Planner 在 BA 之上，回答三个问题：**做什么、先做什么、边界在哪**。

| 项 | 值 |
|----|----|
| 工作区 | `<repo-root>/BA`（`demand` 分支），只写 `plan/` 与 `decisions/` |
| 写入 | 路线图、优先级、容量、跨 BA 决策、契约 owner 指派 |
| 不写 | 需求文档、验收标准、状态、代码 |
| 不领 | feature 认领（认领是 BA 的事） |
| 身份 | `AW_AGENT_ID=planner-<机器或人>`，例如 `pcA-planner` |

## 2. 与 BA 的分工

| 事项 | Planner | BA |
|------|---------|----|
| 目标与范围 | **定** | 落成需求文档 |
| 优先级与排序 | **定** | 按序执行 |
| 需求 / 验收 | 不写 | **写** |
| 需求状态 | 不改 | **唯一写者** |
| 跨 BA 的契约方向 | **拍板** | 提案、消费、ack |
| 派 Dev / QA | 不派 | **派** |
| 回收 worktree | 不碰 | 执行 |

一句话：**Planner 决定"做对的题"，BA 决定"把题做对"。**

## 3. 目录

```text
BA/
├── plan/
│   ├── roadmap.md          # 季度 / 里程碑目标
│   ├── queue-policy.md     # 排序规则与 WIP 上限
│   ├── capacity.md         # 8 个槽位、当前负载、号段分配
│   └── risks.md            # 跨需求的依赖与风险
└── decisions/
    └── ADR-001-xxx.md      # 决策记录（跨 BA 的长期结论）
```

## 4. 节奏

| 频率 | 动作 |
|------|------|
| 每周 | 更新 `roadmap.md` / `queue-policy.md`；跑 `aw.py claim list` 与 `audit` 看容量 |
| 每日 | 读 bus 摘要（可让 Notifier 代读），清 blocker，必要时调序 |
| 里程碑 | 复盘 ADR：哪些决策被推翻、为什么 |
| 随时 | 跨 BA 冲突升级时拍板，并落 ADR |

## 4.1 名册管理（Planner 专属）

`BA/plan/agents.json` 是"谁有资格收消息"的唯一依据，由 Planner 维护：

```bash
aw.py agent register pcA-ba-1 --role ba
aw.py agent register pcB-ba-2 --role ba
aw.py agent roster                 # 对照本地会话看谁真正在线
aw.py agent deactivate pcC-ba-2    # 长期离岗
aw.py agent publish                # 推送到 demand，其他机器可见
```

规则：

- 新成员先注册，再让他 `agent bind`；
- 离岗 / 换人 → `deactivate`，不要直接删（历史消息要能解析）；
- 每周对照 `agent roster` 与 `claim list`，清理"名册 active 但从未上线"的名字。

## 5. 优先级从哪来

1. 用户/业务目标（最高）
2. 线上问题与阻塞（插入，但要换出等量工作）
3. 技术债与契约演进（按季度配额）
4. 团队容量（8 个 BA ≠ 8 倍产能，见 `capacity.md`）

## 6. 硬规则

- **不领 feature**：`claim` 是 BA 的动作；Planner 领了就等于多一个 WIP，破坏队列。
- **不改 `status.md`**：状态只有 BA 能写。
- **决策必须落 ADR**：聊天里的结论不算数。
- **契约变更走消息**：`contract-change` + 消费方 `ack`，不口头对齐。
- **一次只推一个优先级变更**：频繁调序会让所有 BA 空转。
- **不绕过 BA 派 Dev**：派单权在 BA。

## 7. 工具

没有 Planner 专属命令，用同一套：

```bash
aw.py --agent pcA-planner claim list      # 看谁在做什么
aw.py --agent pcA-planner contract check  # 看契约是否对齐
aw.py --agent pcA-planner audit           # 看拓扑与僵尸
aw.py --agent pcA-planner msg inbox       # 看跨 BA 消息
aw.py --agent pcA-planner msg send --to role:ba --type decision --body "..."
```

## 8. 8 个 BA 的容量管理

| 指标 | 目标 |
|------|------|
| 队列长度 | ≥ 2 × 活跃 BA 数（8 个 BA 至少 16 条待办） |
| 在飞任务 | ≤ BA 数（WIP=1 已保证） |
| 平均认领等待 | < 30 分钟 |
| 契约 ack 中位数 | < 4 小时 |
| 返工率 | < 10%（退回次数 / 总需求） |

低于目标时：先补队列，再谈加人。

## 9. 反模式

| 反模式 | 后果 |
|--------|------|
| 直接改 `demand.md` | 与 BA 抢写权，状态机混乱 |
| 直接派 Dev | 绕过 BA，worktree 无人回收 |
| 一天改三次优先级 | 所有 BA 都在切换，吞吐归零 |
| 决策只在会议里说 | 一周后没人记得为什么这么做 |
| 把 Planner 当"高级 BA" | 一个人既规划又执行，等于没有规划 |
