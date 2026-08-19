---
name: agent-workspace-dev
description: Dev Agent 的开发流程、自验证、PR 提交和 worktree 自清理规范。负责在 feature worktree 中实现需求并完成验证门。
metadata:
  short-description: Dev Agent 开发规范
---

# Dev Agent 工作规范

## 前置依赖

**必须同时加载 `agent-workspace`（核心 skill）。**

## 工作区

你的工作区是 `feature-REQ-xxx/` 目录（`feature/REQ-xxx` 分支的 worktree），由 BA Agent 分配。

## 核心职责

1. **读取需求**：从 `BA/demands/REQ-xxx/` 读取需求文档和验收标准
2. **开发实现**：在 worktree 中编码
3. **编写测试**：编写单元测试、集成测试
4. **自验证**：运行验证流程，确保需求覆盖
5. **提交 PR**：创建 Pull Request 到 develop 分支
6. **自清理**：PR 合并后自动清理 worktree

## feature-REQ-xxx/ 目录结构

```
feature-REQ-xxx/
├── .feature/                      # Agent 元数据目录（不提交）
│   ├── manifest.json              # 关联信息
│   ├── status.md                  # 当前进度
│   ├── tasklist.md                # 任务分解清单
│   ├── traceability.md            # 追溯性矩阵
│   ├── verification-report.md     # 验证报告
│   └── agent-log/                 # 操作日志
├── src/                           # 变更代码（与 code/src/ 同构）
├── tests/                         # 变更测试
├── docs/                          # 变更文档
├── CHANGELOG.md                   # 本需求的变更记录
├── REQ-LINK.md                    # 指向 BA 需求的链接
└── README.md                      # 开发说明
```

## 开发流程

### Step 1: 接收任务

```
1. 确认工作区为 feature-REQ-xxx/
2. 读取 .feature/manifest.json 确认需求编号
3. 读取 REQ-LINK.md 或直接读取 BA/demands/REQ-xxx/
   - demand.md：理解需求描述
   - acceptance.md：理解验收标准
4. 更新 .feature/status.md → "开发中"
5. 在 .feature/tasklist.md 中分解开发任务
```

### Step 2: 开发实现

```
1. 在 src/ 中编写代码
2. 遵循 code/ 中已有的代码风格和架构约定
3. 在 tests/ 中编写对应的测试
4. 在 docs/ 中更新相关文档
5. 更新 CHANGELOG.md
6. 定期提交 commit：
   git commit -m "[Dev] 实现xxx功能 (关联: REQ-xxx)"
```

### Step 3: 自验证

详见 `workflows/verify-before-pr.md`。

### Step 4: 提交验证请求

```
1. 将 .feature/verification-report.md 提交到 feature 分支
2. 更新 BA/demands/REQ-xxx/status.md → "待验证"
3. 通知 BA Agent 和 QA Agent 进行验证
```

### Step 5: 等待验证结果

```
1. 等待 QA Agent 验证
2. 如果验证通过 → 状态更新为"已验证" → 进入 Step 6
3. 如果验证不通过 → 状态更新为"已退回" → 回到 Step 2 修改
```

### Step 6: 创建 PR

```
1. 推送 feature 分支到远程
   git push origin feature/REQ-xxx
2. 创建 PR 到 develop 分支
   - PR 标题：[REQ-xxx] {需求名称}
   - PR 描述：包含验证报告摘要、变更摘要
3. 等待 PR 合并
```

### Step 7: 合并后自清理

```
1. 确认 PR 已合并到 develop
2. 删除本地 worktree
   git worktree remove feature-REQ-xxx
3. 删除本地和远程分支
   git branch -d feature/REQ-xxx
   git push origin --delete feature/REQ-xxx
4. 通知 BA Agent：REQ-xxx 已完成，worktree 已清理
```

## Commit Message 规范

```
[{区域}] {描述} (关联: {需求ID})

示例：
[Dev] 实现邮箱登录校验 (关联: REQ-001)
[Dev] 添加登录单元测试 (关联: REQ-001)
[Dev] 更新登录设计文档 (关联: REQ-001)
```

## 避免的操作

- 不要直接修改 `code/` 目录下的内容（它是 CI 只读的）
- 不要修改 `BA/` 目录下的需求文档（除非是更新状态）
- 不要在 feature worktree 中开发不相关的变更
- 不要跳过验证步骤直接创建 PR