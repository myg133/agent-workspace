# 已有项目迁移流程

## 流程

### Step 1: 确认分支结构

```bash
git branch -a
# 确认主开发分支名称（develop 或 master）
```

### Step 2: 创建需求管理和部署分支

```bash
# demand 分支
git checkout --orphan demand
git rm -rf .
echo "# 需求管理分支" > README.md
mkdir -p demands backlog sprint decisions dispatch
git add README.md
git commit -m "[Init] 初始化需求管理分支"
git push origin demand

# deploy 分支
git checkout --orphan deploy
git rm -rf .
echo "# 部署配置分支" > README.md
mkdir -p apps environments releases scripts
git add README.md
git commit -m "[Init] 初始化部署分支"
git push origin deploy
```

### Step 3: 创建 worktree

```bash
git checkout develop  # 或 master
git worktree add code develop
git worktree add BA demand
git worktree add Deploy deploy
```

### Step 4: 迁移代码

如果项目根目录原本包含代码，将代码文件移到 `code/` 目录中。

### Step 5: 更新 CI 配置

确保 CI 流水线路径指向 `code/` 目录。

### Step 6: 验证

```bash
git worktree list
```

## 风险提示

- 迁移前确保所有团队成员已提交变更
- 代码路径变化后需更新 IDE 配置和 CI 路径
- 建议在测试分支上验证流程