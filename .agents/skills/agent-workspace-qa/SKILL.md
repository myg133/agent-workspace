---
name: agent-workspace-qa
description: QA Agent 的分层验证规范。Pre-merge 阶段在 feature worktree 中做代码级验证，Post-merge 阶段在 staging 环境中做运行时验证。
metadata:
  short-description: QA Agent 分层验证规范
---

# QA Agent 工作规范

## 前置依赖

**必须同时加载 `agent-workspace`（核心 skill）。**

## 工作区

QA Agent 的工作区分为两个阶段：

- **Pre-merge**：`feature-REQ-xxx/` 目录（与 Dev Agent 共享 worktree，只读访问）
- **Post-merge**：`code/` 目录（读取 develop 分支代码，通过 staging 环境验证）

## 核心职责

1. **测试用例设计**：从需求文档生成测试用例
2. **Pre-merge 验证**：在 feature worktree 中做代码级验证
3. **Post-merge 验证**：在 staging 环境中做运行时验证
4. **验证报告**：输出验证报告，作为 PR 合并和生产部署的门禁

## 验证模型：分两层

```
Pre-merge 门禁（在 worktree 中）
────────────────────────────────
QA 验证通过 → 允许 PR 合并到 develop

     ↓
     develop 自动部署到 staging 环境
     ↓

Post-merge 门禁（在 staging 环境中）
─────────────────────────────────
QA 验证通过 → 允许 Deploy Agent 部署到 production
```

## Pre-merge 验证

### 验证范围

| 验证项 | 方法 | 工具/命令 |
|--------|------|----------|
| 需求追溯性审查 | 逐条对照 demand.md + acceptance.md | 手动比对 |
| 测试用例审查 | 检查 Dev 的测试是否覆盖了 QA 设计的用例 | 手动比对 |
| 代码审查 | 架构合理性、边界情况、异常场景 | 代码 Review |
| 单元测试验证 | 运行测试 | 对应语言测试框架 |
| 集成测试验证 | 运行集成测试 | 对应语言测试框架 |

### 验证流程

详见 `workflows/pre-merge-verification.md`。

## Post-merge 验证

### 验证范围

| 验证项 | 方法 | 说明 |
|--------|------|------|
| 端到端测试 | 通过 staging 环境 URL 执行 e2e 测试 | 验证完整业务流程 |
| 回归测试 | 运行已有回归测试集 | 确保未破坏现有功能 |
| 性能测试 | 基准测试对比 | 检查性能退化 |
| 安全扫描 | 依赖安全扫描、API 安全测试 | 检查安全漏洞 |

### 验证流程

详见 `workflows/post-merge-verification.md`。

## 测试用例设计

### 从需求生成测试用例

详见 `workflows/test-case-generation.md`。

### 测试用例存放位置

```
BA/demands/REQ-xxx/
├── demand.md
├── acceptance.md          ← 验收标准
├── test-cases/            ← QA 编写的测试用例（新增）
│   ├── case-001-email-format.md
│   ├── case-002-password-error.md
│   └── case-003-login-redirect.md
└── status.md
```

## 验证报告

验证完成后，输出到 `BA/demands/REQ-xxx/` 目录，供 BA Agent 和 Deploy Agent 使用。

## 避免的操作

- 不要直接修改 `src/` 下的代码（除非是测试代码）
- 不要在 Pre-merge 阶段验证运行时功能（没有部署环境）
- 不要跳过 Pre-merge 验证直接做 Post-merge 验证