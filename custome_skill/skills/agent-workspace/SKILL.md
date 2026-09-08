---
name: agent-workspace
description: 定义 workspace 的目录结构、分支策略、命名规范、worktree 生命周期管理和初始化流程。所有在此 workspace 中工作的 Agent 必须先加载此 skill。
metadata:
  short-description: Workspace 组织规范核心
---

# Agent Workspace 组织规范

## 适用角色

所有在此 workspace 中工作的 Agent（BA、Dev、QA、Deploy）**必须**同时加载此 skill。

## 目录结构

```
project-root/
├── .git/                          # 中央仓库（裸仓库或标准仓库）
│
├── BA/                            # [worktree] demand 分支 - 需求管理
│
├── code/                          # [worktree] develop 分支 - CI 只读
│
├── feature-REQ-xxx/               # [worktree] feature/REQ-xxx 分支 - 开发
│
├── Deploy/                        # [worktree] deploy 分支 - 部署配置
│
├── hotfix-xxx/                    # [worktree] hotfix/xxx 分支 - 紧急修复
│
└── .gitignore                     # 统一忽略规则
```

### 目录说明

| 目录 | 分支源 | 使用者 | 读写权限 |
|------|--------|--------|---------|
| `BA/` | `demand` | BA Agent | 读写 |
| `code/` | `develop` | CI 只读，Agent 不写入 | 只读 |
| `feature-REQ-xxx/` | `develop` 派生 | Dev Agent | 读写 |
| `Deploy/` | `deploy` | Deploy Agent | 读写 |
| `hotfix-xxx/` | `main` 派生 | Dev Agent | 读写 |

## 分支策略

### 分支定义

| 分支 | 用途 | 谁写入 | 基分支 |
|------|------|--------|--------|
| `develop` | 主开发分支，CI 构建 | 合并不直接写 | — |
| `demand` | 需求管理 | BA Agent | `develop` 或独立 |
| `feature/REQ-xxx` | 需求开发 | Dev Agent | `develop` |
| `deploy` | 部署配置 | Deploy Agent / CI | 独立分支，不与 main 合并 |
| `main` | 生产发布标记 | 仅从 release 合并 | — |
| `release/vx.y.z` | 预发布 | 发布管理员 | `develop` |
| `hotfix/xxx` | 紧急修复 | Dev Agent | `main` |

### 分支关系

```
develop ← feature/REQ-001   (PR 合并)
develop ← feature/REQ-002   (PR 合并)
develop → release/v1.0.0 → main
                            main → deploy (镜像 tag 信号)
                            deploy 独立演进，不 merge 回 main
```

## 命名规范

### 需求编号

```
REQ-{三位数字}
示例：REQ-001, REQ-042, REQ-123
```

### 分支名

```
feature/REQ-{三位数字}
hotfix/{描述性标识}
release/v{主版本}.{次版本}.{修订号}
```

### Worktree 目录名

```
feature-REQ-{三位数字}
hotfix-{描述性标识}
```

### Commit Message 格式

```
[{区域}] {描述} (关联: {需求ID})

区域：BA | Dev | QA | Deploy | CI
示例：
[Dev] 实现邮箱登录校验 (关联: REQ-001)
[QA] 添加登录模块测试用例 (关联: REQ-001)
[Deploy] 部署 v1.0.0 到 staging (image: myapp:a1b2c3d)
```

### 镜像 Tag

```
默认：{GIT_SHA}（develop 分支的 commit SHA）
发布：{GIT_TAG}（如 v1.0.0）
特殊：用户指定
```

## 工作区定位规则

Agent 在启动时，必须根据自身角色定位到对应的工作区：

```
BA Agent    → 工作区是 BA/ 目录
Dev Agent   → 工作区是 feature-REQ-xxx/ 目录（由 BA Agent 分配）
QA Agent    → 工作区是 feature-REQ-xxx/ 目录（pre-merge）
                或 code/ 目录（post-merge，从 staging 环境验证）
Deploy Agent → 工作区是 Deploy/ 目录
```

## 初始化

新项目或已有项目的初始化流程见 `init/` 目录。

## 生命周期管理

worktree 的创建、验证、回收机制见 `lifecycle/` 目录。

## 模板

通用模板文件见 `templates/` 目录。