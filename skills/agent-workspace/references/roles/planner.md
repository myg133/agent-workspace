# Planner（总规划 / 设计 / 协调）

> 本角色通过 MCP 调用工具，示例写作 `工具名 {参数}`。
> CLI 等价命令见 `references/global/mcp.md`；agent 不要 shell 调 `aw.py`。
> 例外：`bootstrap` / `token` 是人类的运维动作，只能 CLI。

## 0. 启用（含第一个 Planner）

Planner 不是常驻服务，就是一个以 `planner` 角色启动的 agent。

### 0.1 第一个 Planner 怎么注册

`agent register` 本身不需要身份，所以名册为空时也能执行：

```text
# 人类执行，仅 CLI（bootstrap 需要系统外信任）
aw.py agent register planner-1 --role planner --issue-token
# REGISTERED planner-1 (planner)
# TOKEN planner-1 3f9c...
```

之后的发布用 MCP：

```text
agent_publish {}
```

启动 Planner 的进程：

```bash
export AW_AGENT_ID=planner-1
export AW_ROLE=planner
export AW_AGENT_TOKEN=3f9c...
```

MCP 模式下则每次调用带 `agent_id` + `token`。

验证：

```text
agent_roster {}
# mode: team（Planner: planner-1）
```

> 如果以后给 `register` 加了鉴权，bootstrap 规则应当是：
> **名册为空时允许注册第一个 planner**，否则会死锁。

### 0.2 单人 / 单 BA 模式

大部分时间只有一个 BA 在本地开发，**不需要 Planner**：

```text
mode: solo（没有 active Planner；BA 可代行规划）
```

规则：

- BA 可以代行规划，写 `BA/plan/`（这是唯一例外）；
- 不需要队列竞争，直接 `claim_take {"req": "REQ-xxx"}`；
- 一旦登记了 active Planner，BA **停止写** `plan/`，交回规划权。

### 0.3 从 solo 切到 team

1. 注册 Planner + `agent publish`；
2. Planner 接管 `plan/roadmap.md`、`queue-policy.md`；
3. BA 不再写 `plan/`，只从队列 `claim next`；
4. 需要多 BA 时再拆槽位（pcA-ba-2 …）。

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

### 2.1 回答而不是重做

BA 问细节时，默认回答：

```text
按你的 proposal 执行。除非：
  - 违反 roadmap / 契约边界
  - 与另一个 BA 冲突
  - 不可逆或对外
```

- **不要重新做需求**：字段名、错误码、拆分、测试数据都是 BA 的决策权；
- **没有 proposal 的问题不回答**，只回"先给方案"；
- 回复控制在 3 行内：结论 + 理由 + 影响面；
- 2 小时内没回复，BA 按 default 执行；你事后不同意 → `decision` + ADR。

决策权矩阵见 `references/global/decision-rights.md`。

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
| 每周 | 更新 `roadmap.md` / `queue-policy.md`；**周检各 REQ 的 `decisions.md`**；跑 `claim_list {}` 与 `audit {}` 看容量 |
| 每日 | 读 bus 摘要（可让 Notifier 代读），跑 `msg_pending {}` 清欠回复，清 blocker，必要时调序 |
| 里程碑 | 复盘 ADR：哪些决策被推翻、为什么 |
| 随时 | 跨 BA 冲突升级时拍板，并落 ADR |

## 4.1 名册审批（不代注册）

`BA/plan/agents.json` 是"谁有资格收消息"的唯一依据。**BA 自己注册，Planner 审批**：

```text
agent_roster {}                                     # 看谁注册了、谁 pending
agent_activate {"name": "pcA-ba-1"}                 # 通过，变成 active
agent_deactivate {"name": "pcC-ba-2"}               # 长期离岗
agent_publish {}                                    # 推送到 demand，其他机器可见
```

规则：

- 自注册在 team 模式下是 `pending`，必须由 Planner 激活才能收发消息；
- 激活/停用需要 Planner 令牌（team 模式下强制）；
- 离岗 / 换人 → `deactivate`，不要直接删（历史消息要能解析）；
- 每周对照 `agent roster` 与 `claim_list`，清理"名册 active 但从未上线"的名字。

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

所有调用都带 `agent_id` 与 `token`：

```text
claim_list {}
contract_check {}
audit {}
msg_inbox {}
msg_send {"to": "role:ba", "type": "decision", "body": "..."}
doctor {}
stats {}
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
