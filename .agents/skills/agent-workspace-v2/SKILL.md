---
name: agent-workspace-v2
description: 统一的 workspace 组织规范，包含目录结构、分支策略、命名规范、各角色工作流、初始化流程和生命周期管理。主 BA Agent 读取此文件后，按角色截取对应部分注入子 agent 的 prompt。
metadata:
  short-description: Workspace 组织规范（合并版）
---

# Agent Workspace 组织规范（v2）

## 目录

- [第一部分：全局规范](#第一部分全局规范)（所有 Agent 必须遵守）
- [第二部分：BA Agent 工作流](#第二部分ba-agent-工作流)
- [第三部分：Dev Agent 工作流](#第三部分dev-agent-工作流)
- [第四部分：QA Agent 工作流](#第四部分qa-agent-工作流)
- [第五部分：Deploy Agent 工作流](#第五部分deploy-agent-工作流)

---

# 第一部分：全局规范

## 目录结构

```
project-root/
├── .git/                          # 中央仓库
├── BA/                            # [worktree] demand 分支 - 需求管理
├── code/                          # [worktree] develop 分支 - CI 只读
├── feature-REQ-xxx/               # [worktree] feature/REQ-xxx 分支 - 开发
├── Deploy/                        # [worktree] deploy 分支 - 部署配置
├── hotfix-xxx/                    # [worktree] hotfix/xxx 分支 - 紧急修复
└── .gitignore
```

## 分支策略

| 分支 | 用途 | 谁写入 | 基分支 |
|------|------|--------|--------|
| `develop` | 主开发分支，CI 构建 | 合并不直接写 | — |
| `demand` | 需求管理 | BA Agent | `develop` 或独立 |
| `feature/REQ-xxx` | 需求开发 | Dev Agent | `develop` |
| `deploy` | 部署配置 | Deploy Agent / CI | 独立分支，不与 main 合并 |
| `main` | 生产发布标记 | 仅从 release 合并 | — |
| `release/vx.y.z` | 预发布 | 发布管理员 | `develop` |
| `hotfix/xxx` | 紧急修复 | Dev Agent | `main` |

## 命名规范

- **需求编号**: `REQ-{三位数字}`，如 `REQ-001`
- **分支名**: `feature/REQ-001`, `hotfix/JIRA-123`
- **Worktree 目录**: `feature-REQ-001`, `hotfix-JIRA-123`
- **Commit Message**: `[{区域}] {描述} (关联: {需求ID})`
- **镜像 Tag**: 默认 `{GIT_SHA}`，发布用 `{GIT_TAG}`，特殊可用户指定

## 工作区定位规则

| Agent | 工作区 |
|-------|--------|
| BA Agent | `BA/` 目录 |
| Dev Agent | `feature-REQ-xxx/` 目录（由 BA Agent 分配） |
| QA Agent（Pre-merge） | `feature-REQ-xxx/` 目录 |
| QA Agent（Post-merge） | `code/` 目录 + staging 环境 |
| Deploy Agent | `Deploy/` 目录 |

---

# 第二部分：BA Agent 工作流

## 前置依赖

你位于 `BA/` 目录（`demand` 分支的 worktree）。所有变更通过 Git 持久化。

## 核心职责

1. 需求管理：创建/维护需求文档
2. 迭代管理：维护迭代计划
3. 调度管理：维护 Agent 注册表
4. 状态跟踪：更新需求状态
5. Worktree 管理：创建/回收 worktree
6. 验证审批：确认验证结果

## BA/ 目录结构

```
BA/
├── README.md
├── demands/
│   ├── REQ-001-xxx/
│   │   ├── demand.md              # 需求描述
│   │   ├── acceptance.md          # 验收标准
│   │   ├── design-summary.md      # 设计概要
│   │   ├── status.md              # 当前状态
│   │   └── test-cases/            # 测试用例（QA 创建）
│   ├── REQ-002-xxx/
│   └── _template/
├── backlog/
│   ├── inbox/                     # 未梳理的原始想法
│   └── refined/                   # 已梳理待排期
├── sprint/
│   ├── current.md                 # 当前迭代计划
│   └── retrospective.md
├── decisions/                     # 架构决策记录 (ADR)
├── dispatch/
│   ├── rules.md                   # 调度规则
│   ├── registry.md                # Agent 注册表
│   ├── verification-queue.md      # 待验证队列
│   └── cleanup-log.md             # 回收日志
└── .ba/                           # 私有工作目录
```

## 需求状态流转

```
草稿 → 已评审 → 已就绪 → 进行中 → 待验证 → 已验证 → 已完成
                            ↓                ↓
                         进行中 → 已取消    待验证 → 已退回 → 进行中
```

## 分配需求流程

```
1. 确认需求状态为"已就绪"
2. 从 dispatch/rules.md 查找可用的 Dev Agent
3. 创建 feature worktree：
   git worktree add feature-REQ-xxx feature/REQ-xxx
4. 在 .feature/manifest.json 中记录分配信息
5. 更新需求状态为"进行中"
6. 创建 QA 子 agent 生成测试用例
7. 创建 Dev 子 agent 进行开发
```

## 创建子 agent 的方式

使用 `agent` 工具创建子 agent。将 skill 文件中对应角色的工作流作为 prompt 注入：

```python
# 创建 QA 子 agent（生成测试用例）
agent(
    action="start",
    type="verifier",
    prompt=f"""
    你是一个 QA Agent。以下是你的工作规范：
    
    {读取 agent-workspace-v2 中 QA Agent 工作流部分}
    
    当前任务：为 REQ-xxx 生成测试用例
    工作区：BA/demands/REQ-xxx/
    """
)

# 创建 Dev 子 agent
agent(
    action="start",
    type="builder",
    write_roots=["feature-REQ-xxx"],
    prompt=f"""
    你是一个 Dev Agent。以下是你的工作规范：
    
    {读取 agent-workspace-v2 中 Dev Agent 工作流部分}
    
    当前任务：实现 REQ-xxx
    工作区：feature-REQ-xxx/
    """
)
```

## 巡检兜底

每次启动时执行一次 worktree 巡检：
1. 扫描所有 `feature-*` 和 `hotfix-*` worktree
2. 检查分支状态
3. 已合并但未清理的 → 执行清理
4. 记录到 `BA/dispatch/cleanup-log.md`

---

# 第三部分：Dev Agent 工作流

## 前置依赖

你位于 `feature-REQ-xxx/` 目录（`feature/REQ-xxx` 分支的 worktree），由 BA Agent 分配。

## 核心职责

1. 读取需求：从 `BA/demands/REQ-xxx/` 读取需求文档
2. 开发实现：在 worktree 中编码
3. 编写测试：编写单元测试、集成测试
4. 自验证：运行验证流程
5. 提交 PR：创建 Pull Request 到 develop
6. 自清理：PR 合并后自动清理 worktree

## 开发流程

### Step 1: 接收任务

```
1. 确认工作区为 feature-REQ-xxx/
2. 读取 .feature/manifest.json 确认需求编号
3. 读取 BA/demands/REQ-xxx/ 下的需求文档和测试用例
4. 更新 .feature/status.md → "开发中"
```

### Step 2: 开发实现

```
1. 在 src/ 中编写代码
2. 在 tests/ 中编写对应的测试
3. 更新 CHANGELOG.md
4. 定期提交：
   git commit -m "[Dev] 实现xxx功能 (关联: REQ-xxx)"
```

### Step 3: 自验证

```
1. 追溯性检查
   - 逐条对照 BA/demands/REQ-xxx/acceptance.md
   - 检查代码是否覆盖所有验收标准
   - 输出到 .feature/traceability.md

2. 运行测试
   - 单元测试 → 全部通过
   - 集成测试 → 全部通过

3. 质量检查
   - Lint 通过
   - 无 TODO/FIXME/调试代码残留
   - 文档已同步更新
   - CHANGELOG 已更新

4. 生成验证报告到 .feature/verification-report.md
```

### Step 4: 提交验证

```
1. 更新 BA/demands/REQ-xxx/status.md → "待验证"
2. 通知 BA Agent 和 QA Agent
```

### Step 5: 等待验证结果

```
通过 → 更新 status → "已验证" → 创建 PR
不通过 → 更新 status → "已退回" → 修改后重新提交
```

### Step 6: 创建 PR 与清理

```
1. 推送 feature 分支到远程
2. 创建 PR 到 develop
3. PR 合并后：
   - git worktree remove feature-REQ-xxx
   - git branch -d feature/REQ-xxx
   - git push origin --delete feature/REQ-xxx
4. 通知 BA Agent 清理完成
```

---

# 第四部分：QA Agent 工作流

## 前置依赖

QA Agent 分两个阶段工作：
- **Pre-merge**：在 `feature-REQ-xxx/` 目录中做代码级验证
- **Post-merge**：在 `code/` 目录 + staging 环境做运行时验证

## 核心职责

1. 测试用例设计：从需求文档生成测试用例
2. Pre-merge 验证：在 feature worktree 中做代码级验证
3. Post-merge 验证：在 staging 环境中做运行时验证

## 阶段一：Pre-merge 验证

### 验证范围

| 验证项 | 方法 |
|--------|------|
| 需求追溯性审查 | 逐条对照 demand.md + acceptance.md |
| 测试用例审查 | 检查 Dev 的测试是否覆盖了 QA 设计的用例 |
| 代码审查 | 架构合理性、边界情况、异常场景 |
| 单元测试验证 | 运行测试框架 |
| 集成测试验证 | 运行集成测试 |

### 验证流程

```
1. 进入 feature worktree
2. 读取 BA/demands/REQ-xxx/ 需求文档
3. 逐条检查需求实现
4. 检查测试用例覆盖
5. 执行代码审查（使用下面的审查清单）
6. 运行测试验证
7. 生成验证报告
8. 更新需求状态：
   → 通过：status.md → "已验证"
   → 不通过：status.md → "已退回"（附退回原因）
```

### 代码审查清单

```
架构与设计：
□ 代码组织符合项目结构
□ 没有引入不必要的依赖
□ 接口设计合理

功能正确性：
□ 实现了所有功能点
□ 边界情况已处理（空值、非法输入、上限、下限）
□ 异常场景已考虑

安全性：
□ 用户输入已校验
□ 敏感信息未硬编码
□ 权限检查已实现

代码质量：
□ 没有 TODO/FIXME 遗留
□ 没有注释掉的代码
□ 没有调试代码（console.log、debugger）
□ Lint 通过

测试：
□ 新增代码有对应的测试
□ 测试覆盖了正常路径和异常路径
```

## 阶段二：Post-merge 验证

### 触发条件

PR 已合并到 `develop`，且已自动部署到 `staging` 环境。

### 验证范围

| 验证项 | 方法 |
|--------|------|
| 端到端测试 | 通过 staging 环境 URL 执行 e2e 测试 |
| 回归测试 | 运行已有回归测试集 |
| 性能测试 | 基准测试对比（可选） |
| 安全扫描 | 依赖安全扫描、API 安全测试（可选） |

### 验证流程

```
1. 确认 staging 环境已部署最新版本
2. 执行 e2e 测试
3. 执行回归测试
4. 执行性能测试（可选）
5. 执行安全扫描（可选）
6. 更新需求状态：
   → 通过：status.md → "已完成"（生产部署就绪）
   → 不通过：status.md → "staging 验证不通过"
```

## 测试用例设计

从需求文档生成测试用例，存放在 `BA/demands/REQ-xxx/test-cases/`：

```
对每个验收标准，分解测试场景：

AC-01: 邮箱格式校验
├── TC-001: 输入有效邮箱 → 通过
├── TC-002: 输入无@符号的邮箱 → 拒绝
├── TC-003: 输入空邮箱 → 拒绝
└── ...

每个用例包含：
- 用例编号、关联的验收标准、前置条件
- 测试步骤、预期结果、优先级
```

---

# 第五部分：Deploy Agent 工作流

## 核心原则

**Deploy 分支只做"部署配置"，不做"构建"。**

```
CI 的职责：                    Deploy 的职责：
代码 checkout → 构建镜像       helm chart → k8s manifests
→ 打镜像 tag → 推镜像仓库      → 环境配置 → rollout
```

## 工作区

你位于 `Deploy/` 目录（`deploy` 分支的 worktree）。

## Deploy/ 目录结构

```
Deploy/
├── apps/
│   ├── api-gateway/helm/
│   │   ├── Chart.yaml
│   │   ├── templates/
│   │   ├── values.yaml
│   │   ├── environments/
│   │   │   ├── .env.staging
│   │   │   └── .env.production
│   │   └── deploy.sh
│   └── user-service/helm/
├── environments/
│   ├── staging/
│   └── production/
├── releases/                    # 发布快照
├── scripts/
│   ├── deploy.sh
│   ├── rollback.sh
│   └── healthcheck.sh
└── .deploy/                     # 私有工作目录
```

## 镜像 Tag 策略

```
默认：develop 分支的最新 commit SHA
发布：Git Tag（如 v1.0.0）
特殊：用户指定
```

## 部署流程

```
1. 确认部署目标（环境、应用、镜像 tag）
2. 更新对应环境的 .env 文件中的 IMAGE_TAG
3. git commit + push → 触发 CD
4. 监控 CD 流水线
5. 执行健康检查
6. 记录发布
```

## 回滚流程

回滚本质上是一个新的部署操作：

```
1. 确认要回滚的版本
2. git revert 上一个部署 commit
3. 调整 .env 中的镜像 tag 为旧版本
4. git commit + push → 触发 CD 回滚
5. 确认回滚成功
6. 记录回滚原因
```

## 环境管理

使用 **目录 + .env 文件**混合管理：

```
apps/api-gateway/helm/
├── values.yaml                     # 公共默认值（嵌套结构，如资源限制、探针）
└── environments/
    ├── .env.staging                # 环境差异变量（replica、tag、域名）
    └── .env.production
```

---

# 附录：模板

## 需求文档模板 (demand.md)

```markdown
# 需求：{需求名称}

## 基本信息
- 需求编号: REQ-{xxx}
- 优先级: {P0/P1/P2/P3}
- 状态: {草稿/已评审/进行中/已完成}

## 需求描述
{背景和动机}

## 用户故事
作为一个 {角色}，我想要 {功能}，以便于 {价值}

## 功能要求
1. {功能点1}
2. {功能点2}
3. {功能点3}

## 非功能要求
- 性能：{响应时间、吞吐量}
- 安全：{安全要求}
```

## 验收标准模板 (acceptance.md)

```markdown
# 验收标准：{需求名称}

### AC-{001}: {验收项标题}
- 前置条件: {前置条件}
- 测试步骤: 1. {步骤1} 2. {步骤2}
- 预期结果: {预期结果}
- 类型: {功能/性能/安全}
```

## 验证报告模板 (verification-report.md)

```markdown
# 验证报告

## 基本信息
- 需求编号: REQ-{xxx}
- 验证阶段: {Pre-merge / Post-merge}
- 验证 Agent: {agent-name}

## 追溯性检查
| 需求项 | 状态 | 对应代码位置 |
|--------|------|-------------|

## 测试结果
- 单元测试: {通过数}/{总数}
- 集成测试: {通过数}/{总数}

## 结论
- [ ] 可提交 PR / 可部署生产
- [ ] 需修改后重新验证
```

## Sprint 计划模板 (sprint-current.md)

```markdown
# 当前迭代计划

## 迭代信息
- 迭代编号: Sprint {数字}
- 时间范围: {开始日期} → {结束日期}

## 需求列表
| 需求编号 | 名称 | 优先级 | 状态 | 负责人 | Worktree |
|---------|------|--------|------|--------|----------|
| REQ-001 | xxx | P0 | 进行中 | dev-agent-01 | feature-REQ-001 |

## 进度
- 总需求: {总数} | 已完成: {已完成} | 进行中: {进行中} | 待开始: {待开始}
```