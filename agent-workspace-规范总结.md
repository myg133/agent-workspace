# Agent Workspace 组织规范

## 这是什么

一套基于 Git Worktree 的多 Agent 协作开发管理规范。通过**目录隔离 + 子 Agent 上下文隔离 + Git 状态持久化**，解决单 Agent 开发中的上下文污染、目录混乱、状态丢失等问题。

## 核心概念

### 目录平面

```
project-root/
├── .git/                     # 中央仓库
├── BA/                       # [worktree] demand 分支 - 需求管理
├── code/                     # [worktree] develop 分支 - CI 只读
├── feature-REQ-xxx/          # [worktree] feature/REQ-xxx 分支 - 开发
├── Deploy/                   # [worktree] deploy 分支 - 部署配置
└── hotfix-xxx/               # [worktree] hotfix/xxx 分支 - 紧急修复
```

### 分支策略

| 分支 | 用途 | 写入者 |
|------|------|--------|
| `develop` | 主开发，CI 构建 | 合并不直接写 |
| `demand` | 需求管理 | BA Agent |
| `feature/REQ-xxx` | 需求开发 | Dev Agent |
| `deploy` | 部署配置（独立分支，不与 main 合并） | Deploy Agent |
| `main` | 生产发布标记 | 仅从 release 合并 |

### 命名规范

- 需求编号：`REQ-{三位数字}`，如 `REQ-001`
- 分支名：`feature/REQ-001`
- Worktree 目录：`feature-REQ-001`
- Commit Message：`[{区域}] {描述} (关联: {需求ID})`
- 镜像 Tag：默认 `{GIT_SHA}`，发布用 `{GIT_TAG}`

## 角色职责

### BA Agent（主 Agent）

工作区：`BA/` 目录（demand 分支）

职责：
- 与用户讨论需求，确认方案
- 在 `BA/demands/REQ-xxx/` 中维护需求文档和验收标准
- 创建 feature worktree，分配任务
- 创建子 Agent（QA、Dev、Deploy）执行具体任务
- 定期巡检 worktree，执行兜底清理
- 状态管理：所有变更通过 Git 持久化

### QA Agent（子 Agent）

工作区：
- Pre-merge 阶段：`feature-REQ-xxx/` 目录
- Post-merge 阶段：staging 环境

职责：
- 从需求文档生成测试用例，存入 `BA/demands/REQ-xxx/test-cases/`
- Pre-merge 验证：在 feature worktree 中做代码级验证（追溯性审查、代码审查、运行测试）
- Post-merge 验证：在 staging 环境中做运行时验证（e2e 测试、回归测试）

### Dev Agent（子 Agent）

工作区：`feature-REQ-xxx/` 目录（feature/REQ-xxx 分支）

职责：
- 读取需求文档和测试用例
- 编码实现 + 编写测试
- 自验证（追溯性检查 + 运行测试 + 质量检查）
- 创建 PR 到 develop 分支
- PR 合并后自清理 worktree 和分支

### Deploy Agent（子 Agent）

工作区：`Deploy/` 目录（deploy 分支）

职责：
- 从 code/ 读取 CI 信息，创建 helm chart 初始内容
- 更新镜像 tag，提交 deploy 分支触发 CD
- 管理 staging/production 环境配置（目录 + .env 混合）
- 执行回滚（git revert 部署 commit，重新触发 CD）

## 完整工作流

```
1. 用户提出需求
2. BA Agent 与用户讨论 -> 确认方案 -> 创建需求文档
3. BA Agent 创建 QA 子 Agent -> 生成测试用例
4. BA Agent 创建 Dev 子 Agent -> 开发 + 自验证
5. BA Agent 创建 QA 子 Agent -> Pre-merge 验证
6. Dev 创建 PR -> 合并到 develop -> 自清理 worktree
7. develop 自动部署到 staging
8. BA Agent 创建 QA 子 Agent -> Post-merge 验证
9. BA Agent 创建 Deploy 子 Agent -> 部署到 production
10. git push -> 释放容器（需求完成）
```

## 验证门禁

- **Pre-merge 门禁**：QA 验证通过 → 允许合并到 develop
- **Post-merge 门禁**：QA 验证通过 → 允许部署到 production

## 状态管理

Git 仓库是唯一状态源。所有 Agent 的状态通过 `BA/demands/REQ-xxx/` 下的文件持久化。

需求状态流转：
```
草稿 -> 已评审 -> 已就绪 -> 进行中 -> 待验证 -> 已验证 -> 已完成
进行中 -> 已取消
待验证 -> 已退回 -> 进行中
```

## Worktree 回收

- 正常合并后：Dev Agent 自清理（`git worktree remove` + 删除分支）
- 需求取消：BA Agent 强制清理（`git worktree remove --force`）
- 定期巡检：BA Agent 兜底清理
- 安全检查：删除前确认分支已合并、无未提交变更、无未推送 commit

## 架构原则

- **一个需求 = 一个容器**：容器生命周期等于需求完整生命周期
- **一个 Runtime = 子 Agent 池**：主 Agent 通过 agent 工具创建子 Agent，同进程零额外开销
- **Git 即状态**：启动 git pull 恢复，关闭前 git push 持久化
- **子 Agent 上下文隔离**：每个子 Agent 有独立上下文窗口，不污染主 Agent
- **Deploy 分支只做部署配置**：不做构建，不包含源代码

## 初始化

### 新项目
```bash
git init
git checkout -b develop
git checkout --orphan demand    # 创建独立需求管理分支
git checkout --orphan deploy    # 创建独立部署分支
git checkout develop
git worktree add code develop
git worktree add BA demand
git worktree add Deploy deploy
```

### 已有项目迁移
```bash
git checkout --orphan demand    # 创建独立需求管理分支
git checkout --orphan deploy    # 创建独立部署分支
git checkout develop
git worktree add code develop   # 将代码移到 code/ 目录
git worktree add BA demand
git worktree add Deploy deploy
```

## 模板

### 需求文档 (BA/demands/REQ-xxx/demand.md)
```markdown
# 需求：{名称}
- 需求编号: REQ-{xxx}
- 优先级: {P0/P1/P2/P3}
- 状态: {草稿/已评审/进行中/已完成}

## 需求描述
{背景和动机}

## 功能要求
1. {功能点1}
2. {功能点2}

## 非功能要求
- 性能：{响应时间}
- 安全：{安全要求}
```

### 验收标准 (BA/demands/REQ-xxx/acceptance.md)
```markdown
### AC-{001}: {验收项标题}
- 前置条件: {前置条件}
- 测试步骤: 1. {步骤1} 2. {步骤2}
- 预期结果: {预期结果}
- 类型: {功能/性能/安全}
```

### Commit Message
```
[Dev] 实现邮箱登录校验 (关联: REQ-001)
[QA] 添加登录模块测试用例 (关联: REQ-001)
[Deploy] 部署 v1.0.0 到 staging (image: myapp:a1b2c3d)
```

## 注意事项

- `code/` 目录是 CI 只读的，Agent 不要直接修改
- `deploy` 分支独立演进，不与 `main` 或 `develop` 合并
- 删除 worktree 前必须检查分支状态和未提交变更
- 子 Agent 用完即回收，不保留跨任务的上下文
- 所有变更通过 Git 提交持久化，容器是无状态的