# agent-workspace

> 用 Git 当状态层的多 Agent 开发工作流：**一个需求 = 一个 worktree = 一个容器**。

[![Agent Plugins](https://img.shields.io/badge/spec-Agent%20Plugins%201.0.0-blue)](https://agent-plugins.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## 它解决什么

单个 AI Agent 做长任务时，反复踩四个坑：

| 坑 | 这个工作流的解法 |
|----|------------------|
| 上下文被历史污染 | 每个需求一个 worktree + 一个子 Agent，用完即弃 |
| 目录越干越乱 | 仓库根只是容器，业务代码永远在 `code/` |
| 状态靠聊天记录 | 需求状态写进 `BA/demands/REQ-xxx/status.md`，随 Git 持久化 |
| 干了什么没人知道 | 提交信息带需求号与 session，`git log` 就是审计日志 |

## 适用范围

| 适合 | 不适合 |
|------|--------|
| 中大型项目、多需求并行 | 单文件脚本、一次性工具 |
| 多人 / 多 Agent 协作 | 个人短周期验证性开发 |
| 需要"需求 → 开发 → 验证 → 发布"可追溯 | 只求快速出原型 |

衡量标准只有一个：**维护 worktree 的成本 < 上下文隔离带来的收益**。

> 本仓库是**插件源码**，自身不套用该规范（普通 `main` + PR）。所以在仓库根跑
> `aw.py verify` 会提示"不是 workspace 仓库"，属正常。

## 长什么样

```text
<repo-root>/              workspace 分支：只跟踪 README.md + .gitignore
├── code/                 develop   业务源码、CI 源
├── BA/                   demand    需求、迭代、调度表
├── Deploy/               deploy    部署配置（不做构建）
├── feature-REQ-001/      feature/REQ-001   按需创建，合并即回收
└── hotfix-xxx/           hotfix/xxx        按需创建，合并即回收
```

所有 worktree **平铺在仓库根下一层**，没有中间目录、没有嵌套。

## 30 秒跑起来

```bash
# 初始化一个空项目
python skills/agent-workspace/scripts/aw.py init my-project \
  --name "My Project" --remote git@github.com:you/my-project.git

cd my-project
python ../skills/agent-workspace/scripts/aw.py verify   # 自检
python ../skills/agent-workspace/scripts/aw.py audit    # 巡检
```

已有仓库请先读 [迁移指南](skills/agent-workspace/references/init/migrate-project.md) 的前置条件，再执行：

```bash
python skills/agent-workspace/scripts/aw.py migrate --main develop
```

## 角色

| 角色 | 工作区 | 只做 | 规范 |
|------|--------|------|------|
| Planner | `BA/plan`、`BA/decisions` | 总规划、设计、跨 BA 协调（**不领任务、不改状态**） | [roles/planner.md](skills/agent-workspace/references/roles/planner.md) |
| BA | `BA/` | 需求、派单、状态（**唯一**写状态的人） | [roles/ba.md](skills/agent-workspace/references/roles/ba.md) |
| Dev | `feature-REQ-xxx/` | 实现、测试、自验、PR | [roles/dev.md](skills/agent-workspace/references/roles/dev.md) |
| QA | feature / code | 验证、出报告（**不提交**） | [roles/qa.md](skills/agent-workspace/references/roles/qa.md) |
| Deploy | `Deploy/` | 部署配置、发布、回滚 | [roles/deploy.md](skills/agent-workspace/references/roles/deploy.md) |
| Explore | 任意（只读） | 摸底、调用链、风险 | [roles/explore.md](skills/agent-workspace/references/roles/explore.md) |

## 工具

| 命令 | 作用 |
|------|------|
| `aw.py init <dir>` | 初始化 workspace 项目（幂等） |
| `aw.py migrate --main <branch>` | 原地迁移已有仓库（保历史、不改 hash） |
| `aw.py verify [--strict]` | 校验硬约束，可挂 CI / pre-commit |
| `aw.py audit` | 只读巡检：拓扑、僵尸 worktree、stale session |
| `aw.py next-req` | 计算下一个可用 REQ 编号 |
| `aw.py queue add/list/sync` | 维护待认领队列 |
| `aw.py claim next` | 原子认领（**一个 agent 同时只能持 1 个**） |
| `aw.py claim doctor` | 查一人多单 / 死会话 / 孤儿 worktree |
| `aw.py upgrade` | 旧项目升级检查：补什么、清什么、改什么（只读） |
| `aw.py msg` | BA 间消息：空 commit 走 `bus` 分支，带收件人与 ack |
| `aw.py contract check` | 契约一致性：pin 落后、consumer 未声明、变更未 ack |
| `aw.py doctor` | 一页巡检：workspace、拓扑、认领、队列、契约、模式 |
| `aw.py stats` | 运营指标（JSON / 表格） |
| `aw.py agent bind/roster/exit` | 终端绑定身份、维护名册、退出会话 |
| `aw_mcp.py` | stdio MCP 适配层：每个 agent 一个进程，工具即 CLI |

依赖 Python 3.8+ / git 2.20+，只用标准库。

Windows 直接用 `aw.cmd verify` 或 `.\aw.ps1 verify`（自动选择 `py` / `python`）；
Linux / macOS 用 `./scripts/aw verify`。中文输出、盘符、长路径等细节见
[platform-notes.md](skills/agent-workspace/references/global/platform-notes.md)。

## 配套：bus 消息可视化

bus 上的消息是空 commit，直接 `git log` 很难读。配套仓库：

**[agent-workspace-bus-viewer](https://github.com/myg133/agent-workspace-bus-viewer)**

- 只读 bus，不写任何 ref，不替代 `aw.py msg`；
- 生成自包含 HTML，或起本地服务实时刷新；
- 支持按 thread 聚合、全量视角、跨代（`--all-generations`）；
- 对齐消息格式 v2（`expect` / `reply_by` / `re` / `result`）。

```bash
git clone https://github.com/myg133/agent-workspace-bus-viewer
cd agent-workspace-bus-viewer

# 有本地 clone
bun run bus-report.ts serve --repo /path/to/your-workspace --out ./out --port 8787

# 没有 clone：只拉 bus 分支，不检出工作区
bun run bus-report.ts serve --remote git@github.com:you/your-repo.git --out ./out --port 8787
```

打开 <http://127.0.0.1:8787>。Bun / Deno / Node 任一即可。

> 这是独立仓库，不属于本 skill；本仓库只负责写 bus，它负责读 bus。

## 自测

```bash
python -m unittest discover -s skills/agent-workspace/tests -v
```

61 个用例覆盖：布局、巡检、认领并发、消息寻址/游标/回执/离线队列/阻塞等待、反馈义务与欠回复门禁、契约检查、升级检查、身份绑定与令牌、MCP 握手。
全部在临时目录运行，不碰当前仓库。

## 升级已有项目

```bash
aw.py upgrade      # 只读：列出「需要补 / 需要清 / 需要改」
```

目录拓扑在 1.x 内不变，升级只做**补文件**和**改引用**，不重建、不 rebase、不改分支名。
详见 [upgrade.md](skills/agent-workspace/references/lifecycle/upgrade.md)。

## 多个 BA 同机协作

4 个以上 BA 共享一个仓库时，给每个会话注入稳定槽位：

```powershell
$env:AW_AGENT_ID = 'ba-slot-1'; omp
```

认领走工具，不走表格：

```bash
aw.py claim next      # CLAIMED REQ-003 / ALREADY_HOLDING REQ-002 / QUEUE_EMPTY
aw.py claim list
aw.py claim doctor --repair
```

WIP=1 由锁 + 每任务一文件强制，**重启也不会多领**（判定用 agent_id 而非 session）。
详见 [concurrency.md](skills/agent-workspace/references/global/concurrency.md)。

## 仓库结构

```text
plugin.json                          Agent Plugins 清单
com.anspire-open.agents/             六个角色的 agent 定义（薄壳，指向规范）
skills/agent-workspace/
├── SKILL.md                         入口索引（138 行）
├── references/
│   ├── global/                      布局、路径、.gitignore、状态机、并发
│   ├── roles/                       六个角色的完整工作流
│   ├── init/                        新建 / 迁移
│   └── lifecycle/                   巡检 / 回收 / 发布
├── assets/templates/                19 个模板
└── scripts/aw.py                    CLI
docs/                                设计稿与案例（含归档）
```

## 安装

**作为 Agent Plugins 插件**：把本仓库放到客户端的插件目录（含 `plugin.json` 即被识别）。

**作为 Agent Skill**：把 `skills/agent-workspace/` 复制到 `~/.claude/skills/` 或项目的 `.agents/skills/`。

**什么都不装**：直接读 [SKILL.md](skills/agent-workspace/SKILL.md)，手工执行里面的命令。

## 设计取舍

- **仓库根是空容器**：`git clone` 后几乎看不到代码，要用 `code/` 进工作区。代价换来的是"平台锁死运行目录"也不影响并行开发。
- **状态只在 Git 里**：不引入数据库/服务端，任何 Agent 崩溃后 `git pull` 即可恢复现场。
- **规范必须有脚本兜底**：文档只能"告诉"，`aw.py verify` 才能"证明"。两者缺一不可。

## License

[MIT](LICENSE)
