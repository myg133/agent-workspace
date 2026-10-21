# 目录、分支与命名

## 1. 物理布局：workspace 根容器 + 平铺 worktree

```text
<repo-root>/                     # workspace 分支的 worktree（主 worktree）
├── README.md                    # workspace 分支跟踪
├── .gitignore                   # workspace 分支跟踪（双层防御）
├── .git/
│
├── code/                        # [worktree] develop  — CI 主工作区
├── BA/                          # [worktree] demand   — 需求管理
├── Deploy/                      # [worktree] deploy   — 部署配置
├── feature-REQ-001/             # [worktree] feature/REQ-001 — 按需创建
├── hotfix-JIRA-123/             # [worktree] hotfix/JIRA-123 — 按需创建
└── .local/                      # 本地暂存（可选，不跟踪）
```

**硬约束**：

1. `workspace` 分支只跟踪 `README.md` + `.gitignore`（`git ls-files` 必须恰好 2 行）。
2. 所有 worktree 必须**直接**位于 `<repo-root>/` 下一层，禁止 `workspaces/code/` 这类中间层，禁止 `feature-xxx/code/` 这类二级嵌套。
3. 每个 worktree 自己的 `.gitignore` 由**它所在的分支**跟踪，workspace 一概不管。

## 2. 分支模型

| 分支 | 类型 | 归属 worktree | 谁写 | 内容 |
|------|------|---------------|------|------|
| `workspace` | orphan | `<repo-root>/` | BA（极少） | 仅 README + .gitignore |
| `main` | orphan | 无 | 发布管理员 | 生产发布标记 + tag |
| `develop` | 普通（源自 main） | `code/` | 仅通过 PR 合并 | 业务源码、CI 配置 |
| `demand` | orphan | `BA/` | BA | 需求、迭代、调度 |
| `deploy` | orphan | `Deploy/` | Deploy / CD | Kustomize、Application、Ingress |
| `feature/REQ-xxx` | 普通（源自 develop） | `feature-REQ-xxx/` | Dev | 单需求开发 |
| `release/vX.Y.Z` | 普通（源自 develop） | 无（临时） | 发布管理员 | 冻结回归 |
| `hotfix/xxx` | 普通（源自 main） | `hotfix-xxx/` | Dev | 紧急修复 |

`workspace` / `main` / `demand` / `deploy` 是**互相无父的 orphan 分支**，各自拥有完整的根目录与 `.gitignore`。

## 3. 命名规范

| 对象 | 规则 | 示例 |
|------|------|------|
| 需求编号 | `REQ-{三位数字}` | `REQ-001` |
| 需求目录 | `REQ-xxx-{slug}` | `REQ-001-login` |
| 功能分支 | `feature/REQ-xxx` | `feature/REQ-001` |
| 功能 worktree | `feature-REQ-xxx` | `feature-REQ-001` |
| 修复分支 | `hotfix/{ticket}` | `hotfix/JIRA-123` |
| 修复 worktree | `hotfix-{ticket}` | `hotfix-JIRA-123` |
| Commit | `[{区域}] {描述} (关联: {REQ}) [session: {id}]` | 见下 |

```
[BA] 更新 REQ-003 状态 (关联: REQ-003) [session: ba-mbp-20261021143022-a1b2]
[Dev] 实现邮箱校验 (关联: REQ-003)
[QA] 补充登录场景测试用例 (关联: REQ-003)
[Deploy] 更新 staging 镜像 tag (release: v1.2.0)
[Workspace] 更新导航 README
```

**只有 `demand` 分支的 commit 强制携带 session ID**，其余分支不强制。

## 4. worktree 生命周期

创建（在 `<repo-root>` 或 `BA/` 中执行）：

```bash
git worktree add feature-REQ-001 -b feature/REQ-001 develop    # 在仓库根
git worktree add ../feature-REQ-001 -b feature/REQ-001 develop # 在 BA/ 中
```

回收：见 `references/lifecycle/cleanup.md`。**1 个 worktree 只服务 1 个需求，禁止跨需求复用。**

## 5. `.local/` 本地暂存

每个 worktree 可有 `.local/`，由该 worktree 的 `.gitignore` 忽略：

```text
.local/
├── discussions/   # 方案讨论
├── analysis/      # 探查报告
├── drafts/        # 未定稿文档
└── references/    # 临时资料
```

定稿后**晋升**到 Git 跟踪目录（复制 → `git add` → commit → 删除草稿）。纯中间产物不必晋升。
