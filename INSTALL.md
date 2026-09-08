# Agent Workspace Skill - 安装指南

> **本文件专门给 agent 读**。读完后请按"安装"章节执行。
> 人类用户也可以参考下方步骤手动安装。

## 这是什么

- **仓库**：https://github.com/myg133/agent-workspace
- **类型**：Git skill（多文件 + Git 版本控制）
- **安装路径**：`.agents/skills/agent-workspace/`
- **文档入口**：`SKILL.md`（必读）

加载这个 skill 后，你能：

- 理解 workspace / develop / demand / deploy / feature / hotfix 等多分支工作流
- 知道 worktree 在仓库根平铺（无中间目录层）
- 理解 workspace 根分支 + .gitignore 白名单防御机制
- 知道 BA / Dev / QA / Deploy 四个角色的工作流
- 知道需求状态机（草稿 → 已评审 → 已就绪 → 进行中 → 待验证 → 已验证 → 已完成）

## 适用场景

加载本 skill 的判断标准：

- ✅ 多 Agent 协作任务（BA + Dev + QA + Deploy 协同）
- ✅ 复杂任务需要隔离（每个 feature worktree 独立上下文）
- ✅ 长期迭代项目（需求 / 迭代 / 调度 / 状态管理）
- ✅ Git worktree 隔离开发
- ❌ 单 agent 单任务的简单场景（无需加载）

## 安装

### 方式 1：直接 clone（推荐）

```bash
# 把仓库克隆到本地的 .agents/skills/ 目录
git clone https://github.com/myg133/agent-workspace.git .agents/skills/agent-workspace
```

### 方式 2：浅克隆（节省空间 / 网络）

```bash
git clone --depth 1 https://github.com/myg133/agent-workspace.git .agents/skills/agent-workspace
```

### 方式 3：符号链接（开发 / 跨项目共享）

```bash
# 在某处完整克隆一份
git clone https://github.com/myg133/agent-workspace.git ~/projects/agent-workspace
# 符号链接到当前项目的 skills 目录
ln -s ~/projects/agent-workspace/.agents/skills/agent-workspace .agents/skills/agent-workspace
```

未来更新：

```bash
cd ~/projects/agent-workspace
git pull
# 符号链接自动生效，无需重做
```

### 方式 4：直接读 URL（无需安装，仅查阅）

如果只需要读规范不参与本地 worktree 操作（不创建 worktree、不 commit），可以直接通过 URL 读：

- SKILL.md：https://raw.githubusercontent.com/myg133/agent-workspace/main/.agents/skills/agent-workspace/SKILL.md
- 模板：https://github.com/myg133/agent-workspace/tree/main/.agents/skills/agent-workspace/templates

## 验证安装

```bash
# 1. 关键文件存在
ls .agents/skills/agent-workspace/SKILL.md
ls .agents/skills/agent-workspace/INSTALL.md

# 2. 模板齐全
ls .agents/skills/agent-workspace/templates/
# 应看到 6 个 .tpl 文件：
#   acceptance.md.tpl
#   demand.md.tpl
#   root-gitignore.tpl
#   root-readme.md.tpl
#   sprint-current.md.tpl
#   verification-report.md.tpl

# 3. （可选）防御性机制只在"用作 workspace 根"时验证
#     skill 自身不需要跑这个测试，参考 templates/root-gitignore.tpl 的注释
```

## 加载规范

安装后，**每次执行多 Agent 协作任务前**加载 SKILL.md：

```
请加载 .agents/skills/agent-workspace/SKILL.md
并按其中"第一部分：全局规范"+"对应角色"工作流执行任务。
```

按角色加载：

- **BA Agent**（主 agent）：加载 SKILL.md 全部
- **Dev Agent**（子 agent）：加载 SKILL.md 第三部分
- **QA Agent**（子 agent）：加载 SKILL.md 第四部分
- **Deploy Agent**（子 agent）：加载 SKILL.md 第五部分
- **跨角色协作**：BA Agent 作为主 agent，按需创建子 agent 注入对应章节

## 应用到当前项目（消费方首次配置）

> 本节针对"想把自己的项目改造为 workspace 项目"的场景，**不是** skill 安装。

如果当前项目**没有**用 workspace 规范，想用本规范改造：

1. 加载 `SKILL.md`，按 `init/new-project.md`（新建）或 `init/migrate-project.md`（已有项目）流程初始化
2. **关键概念速查**：

   | 概念 | 含义 |
   |------|------|
   | workspace 根分支 | 仓库根的归属分支，**只跟踪 2 个元数据文件**（README + .gitignore） |
   | 物理平铺 | 所有 worktree（code/ BA/ Deploy/ feature-xxx/）在仓库根平铺，**无中间目录层** |
   | 白名单防御 | workspace .gitignore 用 `!README.md !.gitignore * !*/` + `/*/` 双层防御 |
   | 无父独立分支 | workspace / demand / deploy 是 orphan 分支，各管各的 .gitignore |
   | 角色协同 | BA 主控，Dev/QA/Deploy 子 agent 在各自 worktree 工作 |

3. 复制 `templates/root-gitignore.tpl` 到消费方项目仓库根作为 `.gitignore`
4. 按 `init/` 章节创建 workspace 分支 + worktree

## 反馈

- **仓库**：https://github.com/myg133/agent-workspace
- **Issue**：https://github.com/myg133/agent-workspace/issues

## 版本

- 当前规范：agent-workspace（统一版）
