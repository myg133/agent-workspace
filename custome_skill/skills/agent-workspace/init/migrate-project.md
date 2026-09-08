# 已有项目迁移流程

## 前置条件

- 项目已有 Git 仓库，且已有 `develop` 或等效的主开发分支
- 所有分支已推送到远程
- 当前工作区无未提交的变更

## 流程

### Step 1: 确认当前分支结构

```bash
git branch -a
```

确认：
- 主开发分支名称（通常是 `develop` 或 `master`）
- 是否已有 feature 分支
- 远程仓库地址

### Step 2: 创建 demand 分支

```bash
# 从 develop 创建独立分支（无共同祖先）
git checkout --orphan demand
git rm -rf .
echo "# 需求管理分支" > README.md
mkdir -p demands backlog sprint decisions dispatch
git add README.md
git commit -m "[Init] 初始化需求管理分支"
git push origin demand
```

### Step 3: 创建 deploy 分支

```bash
git checkout --orphan deploy
git rm -rf .
echo "# 部署配置分支" > README.md
mkdir -p apps environments releases scripts
git add README.md
git commit -m "[Init] 初始化部署分支"
git push origin deploy
```

### Step 4: 切回主开发分支，创建 code/ worktree

```bash
git checkout develop   # 或 master
git worktree add code develop
```

### Step 5: 创建 BA/ worktree

```bash
git worktree add BA demand
```

### Step 6: 创建 Deploy/ worktree

```bash
git worktree add Deploy deploy
```

### Step 7: 迁移已有代码

将现有代码文件移动到 `code/` 目录中（如果项目根目录原本包含代码）：

```bash
# 如果项目根目录原本是代码目录，现在移到 code/ 下
# 注意：不要移动 .git/ 目录
# 示例：将 src/、tests/ 等移到 code/ 下
```

如果现有代码直接在根目录，则迁移后根目录结构应为：

```
.git/
.gitignore
BA/          (worktree)
code/        (worktree) ← 包含所有源代码
Deploy/      (worktree)
```

### Step 8: 更新 CI 配置

检查 CI 配置（如 `.github/workflows/`），确保流水线路径指向 `code/` 目录，或者将 CI 配置移到 `code/` 目录下。

### Step 9: 验证

```bash
git worktree list
# 应输出：
# D:\path\to\project  develop  [code]
# D:\path\to\project\BA  demand  [BA]
# D:\path\to\project\Deploy  deploy  [Deploy]
```

### Step 10: 推送并通知团队

```bash
git push origin --all
```

通知所有团队成员 clone 仓库后执行 `git worktree` 相关操作。

## 风险提示

- 迁移已有项目时，确保所有团队成员已提交并推送他们的变更
- `code/` worktree 创建后，原有根目录的代码路径会变化，需要更新 IDE 配置、CI 路径等
- 如果项目有大量分支，考虑逐步迁移，不要一次性切换所有分支
- 迁移前建议在测试分支上验证流程

## 验证清单

- [ ] 所有分支已推送到远程
- [ ] `code/` worktree 创建成功，内容与原有 develop 分支一致
- [ ] `BA/` worktree 创建成功
- [ ] `Deploy/` worktree 创建成功
- [ ] CI 配置已更新，指向 `code/` 目录
- [ ] 团队成员已通知
- [ ] 现有 feature 分支可以正常合并到 `code/` worktree 的 develop 分支