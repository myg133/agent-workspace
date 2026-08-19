# 新项目初始化流程

## 流程

### Step 1: 创建 Git 仓库

```bash
git init
echo "# {项目名称}" > README.md
echo ".agents/" >> .gitignore
git add README.md .gitignore
git commit -m "[Init] 项目初始化"
```

### Step 2: 创建分支

```bash
git checkout -b develop
git push origin develop

# demand 分支（独立分支）
git checkout --orphan demand
git rm -rf .
echo "# 需求管理分支" > README.md
mkdir -p demands backlog sprint decisions dispatch
git add README.md
git commit -m "[Init] 初始化需求管理分支"
git push origin demand

# deploy 分支（独立分支）
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
git checkout develop
git worktree add code develop
git worktree add BA demand
git worktree add Deploy deploy
```

### Step 4: 验证

```bash
git worktree list
# 应输出：
# {path}  develop  [code]
# {path}\BA  demand  [BA]
# {path}\Deploy  deploy  [Deploy]
```

## 验证清单

- [ ] `.git/` 目录存在
- [ ] `code/` worktree → `develop` 分支
- [ ] `BA/` worktree → `demand` 分支
- [ ] `Deploy/` worktree → `deploy` 分支
- [ ] `develop`、`demand`、`deploy` 已推送到远程