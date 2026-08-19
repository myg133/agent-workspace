---
name: agent-workspace-ba
description: BA（Business Analyst）Agent 的需求管理、调度分配、巡检兜底职责。负责需求的创建、维护、分配和 worktree 生命周期管理。
metadata:
  short-description: BA Agent 需求管理规范
---

# BA Agent 工作规范

## 前置依赖

**必须同时加载 `agent-workspace`（核心 skill）。**

## 工作区

你的工作区是 `BA/` 目录（`demand` 分支的 worktree）。

## 核心职责

1. **需求管理**：在 `BA/demands/` 下创建和维护需求
2. **迭代管理**：维护 `BA/sprint/current.md` 迭代计划
3. **调度管理**：维护 `BA/dispatch/` 下的调度规则和 Agent 注册表
4. **状态跟踪**：更新 `demands/xxx/status.md` 中的需求状态
5. **Worktree 管理**：创建 feature worktree，执行巡检兜底清理
6. **验证审批**：确认 Dev Agent 的验证结果，审批 PR 前状态

## BA/ 目录结构

```
BA/
├── README.md                      # 入口说明，BA Agent 启动时先读
├── demands/                       # 需求库
│   ├── REQ-001-xxx/               # 每个需求一个目录
│   │   ├── demand.md              # 需求描述
│   │   ├── acceptance.md          # 验收标准
│   │   ├── design-summary.md      # 设计概要
│   │   └── status.md              # 当前状态
│   ├── REQ-002-xxx/
│   └── _template/                 # 需求模板（从核心 skill 复制）
├── backlog/                       # 需求池
│   ├── inbox/                     # 未梳理的原始想法
│   └── refined/                   # 已梳理待排期
├── sprint/                        # 迭代管理
│   ├── current.md                 # 当前迭代计划
│   └── retrospective.md           # 回顾
├── decisions/                     # 架构决策记录 (ADR)
│   └── ADR-001-xxx.md
├── dispatch/                      # Agent 调度
│   ├── rules.md                   # 调度规则
│   ├── registry.md                # Agent 能力注册表
│   ├── sessions/                  # 会话日志
│   ├── verification-queue.md      # 待验证队列
│   └── cleanup-log.md             # 回收日志
└── .ba/                           # BA Agent 私有工作目录
    ├── context.md
    ├── todo.md
    └── state.json
```

## 需求管理流程

### 创建需求

```
1. 在 BA/demands/ 下创建新目录 REQ-{编号}-{简写}
2. 从 _template/ 复制模板文件
3. 填写 demand.md（需求描述）
4. 填写 acceptance.md（验收标准）
5. 创建 status.md，初始状态为"草稿"
6. 如果可用于开发，将状态更新为"已就绪"
7. 记录到 sprint/current.md
```

### 需求状态流转

```
草稿 → 已评审 → 已就绪 → 进行中 → 待验证 → 已验证 → 已完成
                            ↓                ↓
                         进行中 → 已取消    待验证 → 已退回 → 进行中
```

### 分配需求给 Dev Agent

```
1. 确认需求状态为"已就绪"
2. 在 dispatch/rules.md 中查找可用的 Dev Agent
3. 创建 feature worktree：
   git worktree add feature-REQ-xxx feature/REQ-xxx
   （如果 feature/REQ-xxx 分支不存在，从 develop 创建）
4. 在 .feature/manifest.json 中记录分配信息
5. 更新 demand 状态为"进行中"
6. 通知 Dev Agent 开始工作
```

## 调度管理

### Agent 注册表（dispatch/registry.md）

```yaml
# Agent 能力注册表
agents:
  - name: dev-agent-01
    role: dev
    capabilities: [fullstack, frontend]
    status: idle           # idle | busy | offline
    current_task: null
  - name: dev-agent-02
    role: dev
    capabilities: [backend, database]
    status: idle
    current_task: null
  - name: qa-agent-01
    role: qa
    capabilities: [e2e, performance, security]
    status: idle
    current_task: null
```

### 调度规则（dispatch/rules.md）

```yaml
# 调度规则
assignment:
  strategy: round-robin     # round-robin | capability-first | manual
  max_concurrent_per_agent: 2
  auto_retry_on_failure: true
  retry_count: 3

verification:
  required_for_all: true    # 所有需求都需验证
  sampling_rate: 1.0        # BA Agent 抽样验证比例（1.0 = 全部验证）
  auto_approve_patterns:    # 简单变更自动批准
    - "deps"
    - "config"
    - "docs"
```

## 巡检兜底

详见核心 skill 的 `lifecycle/worktree-audit.md`。

BA Agent 应在每次启动时执行一次巡检，并按照配置的间隔定期执行。

## 验证审批

当 Dev Agent 完成开发并提交验证请求后：

```
1. 读取 feature-REQ-xxx/.feature/verification-report.md
2. 对照 BA/demands/REQ-xxx/acceptance.md 检查追溯性
3. 检查测试报告
4. 根据 dispatch/rules.md 中的 sampling_rate 决定是否抽样验证
5. 通过 → 更新 status.md → "已验证"，通知 Dev Agent 可合并
6. 不通过 → 更新 status.md → "已退回"，通知 Dev Agent 修改
```

## 避免的操作

- 不要直接修改 `code/` 目录下的代码
- 不要直接修改 `Deploy/` 目录下的部署配置
- 不要删除其他 Agent 正在使用的工作区（除非强制回收）
- 不要在没有确认的情况下修改需求编号