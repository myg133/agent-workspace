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

依赖 Python 3.8+ / git 2.20+，只用标准库。

## 仓库结构

```text
plugin.json                          Agent Plugins 清单
com.anspire-open.agents/             五个角色的 agent 定义（薄壳，指向规范）
skills/agent-workspace/
├── SKILL.md                         入口索引（138 行）
├── references/
│   ├── global/                      布局、路径、.gitignore、状态机、并发
│   ├── roles/                       五个角色的完整工作流
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
