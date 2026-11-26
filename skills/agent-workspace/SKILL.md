---
name: agent-workspace
description: 一套 skill、两种模式的多 Agent 协作规范。workspace 模式面向 code/BA/Deploy 平铺 worktree、demand/bus 分支、多 BA 并行；single 模式面向传统 main/develop/feature 仓库 + 独立 docs 仓库 + 本地 .aw。两者共享角色、claim、handoff、测试/会话预算、消息与写目录规则；按 .aw/config.json 或仓库布局选择模式。
metadata:
  short-description: 多 Agent 协作（workspace / single 双模式）
  version: 2.1.0
---

# Agent Workspace

一套 skill，两个模式：

| 模式 | 适用 | 运行时 |
|------|------|--------|
| **workspace** | 多仓库/多需求并行，`code/ BA/ Deploy/` 平铺 worktree，需要 demand/bus 分支 | `scripts/aw.py` |
| **single** | 已有传统仓库 + 独立 docs 仓库，本地 `.aw/`，不想改代码仓库布局 | `scripts/aw_single.py` |

**不要混用两种模式。** 先判断模式，再读对应文档和执行命令。

## 0. 先判断模式

按顺序：

1. 读当前目录向上最近的 `.aw/config.json`；
2. `profile: single` → **single**；
3. 存在 `code/ BA/ Deploy/` 布局，或 config 声明 workspace → **workspace**；
4. 两者都不匹配 → 不猜，运行 `onboard` 或问用户。

模式判断失败时不要自动 init，也不要把 workspace 的 demand/bus/deploy 规则套到 single 项目上。

## 1. 共享硬规则

1. **一个需求，一个容器**：一个 REQ 一个 worktree；合并/关闭即回收。
2. **一个事实，一个写者**：状态只有 BA 改；claim 只有本人持；契约只有 owner 批。
3. **WIP=1**：一个 agent 同时只持一个 REQ；先 claim，再实现。
4. **子 Agent 不接消息**：不接 inbox / 不 watch / 不 claim / 不写 bus；只读任务卡和 evidence，结果交回父 BA。
5. **探索权唯一**：BA 只做业务/文档探索；Explore/Dev 是代码探索 owner；fresh 子 Agent 默认零上下文。
6. **任务预检 + 开工自检**：BA 切片；子 Agent 只验 evidence/HEAD/入口/测试命令；第一次 compaction 就停。
7. **写入目录限定**：只写项目根/当前 worktree；临时 `.aw/tmp/`，导出 `.aw/exports/<REQ>/`；禁止盘根、`%TEMP%`、Desktop、Downloads、`..` 逃逸。
8. **BA 接用户任务先报备**：`msg report`；有 active Planner 发 Planner，否则广播。
9. **换班不换 agent_id**：handoff → 停进程；同一 `AW_AGENT_ID` 新会话 resume。

共享细节：

- [测试预算](references/global/testing.md)
- [会话预算](references/global/session-budget.md)
- [探索权唯一](references/global/exploration.md)
- [任务预检](references/global/task-sizing.md)
- [换班 handoff](references/global/handoff.md)
- [写入边界](references/global/paths.md)（workspace 路径；single 用 [layout](references/single/layout.md)）
- [通信层 Port/Adapter](references/comm/README.md)
- [消息机制](references/global/messaging.md)、[通道](references/global/transport.md)
- [子 Agent 契约](references/roles/subagent-contract.md)

## 2. 角色

workspace 共 8 个角色：

| 类型 | 角色 |
|------|------|
| 主 Agent | Planner / BA / Guide |
| 子 Agent | Dev / QA / Deploy / Explore / Notifier |

single 使用其中 4 个：

~~~text
Planner（可选） / BA / Dev / QA
~~~

角色是权限契约，不是岗位名称。子 Agent 先读 [subagent-contract](references/roles/subagent-contract.md)，再读具体角色：

- [Planner](references/roles/planner.md)
- [BA](references/roles/ba.md)
- [Guide](references/roles/guide.md)
- [Dev](references/roles/dev.md)
- [QA](references/roles/qa.md)
- [Deploy](references/roles/deploy.md)
- [Explore](references/roles/explore.md)
- [Notifier](references/roles/notifier.md)

single 的模式差异命令见 `references/single/roles/`。

## 3. Workspace 模式

入口：`scripts/aw.py`；MCP：`scripts/aw_mcp.py`（仅 workspace）。

~~~bash
python <skill>/scripts/aw.py onboard
python <skill>/scripts/aw.py init my-project --name "My Project" --remote <url>
python <skill>/scripts/aw.py claim next
python <skill>/scripts/aw.py claim adopt REQ-001 --branch feature/REQ-001
python <skill>/scripts/aw.py path check .aw/tmp/x.txt
python <skill>/scripts/aw.py msg report --subject "用户新任务" --body "..."
~~~

文档：

- [布局与分支](references/global/layout.md)
- [路径基准](references/global/paths.md)
- [MCP](references/global/mcp.md)
- [唤醒插件](references/global/agent-plugins.md)
- [init / migrate](references/init/)
- [生命周期](references/lifecycle/)

## 4. Single 模式

入口：`scripts/aw_single.py`；**没有 MCP**。

~~~bash
python <skill>/scripts/aw_single.py init --root . \
  --code-root <code-root> --docs-root <docs-root> --base-branch develop
python <skill>/scripts/aw_single.py whoami
python <skill>/scripts/aw_single.py claim next
python <skill>/scripts/aw_single.py claim adopt REQ-001 --branch feature/REQ-001
python <skill>/scripts/aw_single.py path check .aw/tmp/x.txt
python <skill>/scripts/aw_single.py msg report --subject "用户新任务" --body "..."
~~~

文档：

- [single 布局](references/single/layout.md)
- [single 工作流](references/single/workflow.md)
- [setup](references/single/setup.md)
- [single profile](references/single/single-profile.md)
- [MQTT + bus](references/single/mqtt-bus-protocol.md)
- [OMP 唤醒](references/single/omp.md)
- [DSH 唤醒](references/single/dsh.md)

## 5. 读什么

| 你在 | 先读 |
|------|------|
| 不确定模式 | 本页 + `aw.py onboard` / 配置检查 |
| workspace BA / Planner | 角色文档 + `global/state-machine` + `global/concurrency` + `global/messaging` |
| workspace Dev / QA / Explore | 对应角色 + `global/exploration` + `global/task-sizing` |
| single BA / Planner | `references/single/workflow.md` + 角色 + 共享预算 |
| single Dev / QA | `references/single/workflow.md` + 角色 + 共享预算 |
| 发布/巡检 | `references/lifecycle/` |

## 6. 测试

~~~bash
python -m unittest discover -s tests -v
python -m unittest discover -s tests/single -v
~~~

测试按风险分层：fast / related / full；不要每次全量。

依赖：Python 3.8+、git 2.20+；只用标准库（single 的 paho 已 vendor）。
