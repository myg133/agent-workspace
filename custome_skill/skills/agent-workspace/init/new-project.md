# 新项目初始化流程

## 前置条件

- Git 已安装
- 项目目录已创建，当前位于项目根目录
- 用户已确认项目名称和默认分支策略

## 流程

### Step 1: 创建 Git 仓库

```bash
git init
echo "# 项目名称" > README.md
echo ".agents/" >> .gitignore
git add README.md .gitignore
git commit -m "[Init] 项目初始化"
```

### Step 2: 创建 develop 分支

```bash
git checkout -b develop
git push origin develop
```

### Step 3: 创建 demand 分支（独立分支，无共同祖先）

```bash
git checkout --orphan demand
git rm -rf .
echo "# 需求管理分支" > README.md
mkdir -p demands backlog sprint decisions dispatch
git add README.md
git commit -m "[Init] 初始化需求管理分支"
git push origin demand
```

### Step 4: 创建 deploy 分支（独立分支）

```bash
git checkout --orphan deploy
git rm -rf .
echo "# 部署配置分支" > README.md
mkdir -p apps environments releases scripts
git add README.md
git commit -m "[Init] 初始化部署分支"
git push origin deploy
```

### Step 5: 切回 develop 分支，创建 code/ worktree

```bash
git checkout develop
git worktree add code develop
```

### Step 6: 创建 BA/ worktree

```bash
git worktree add BA demand
```

### Step 7: 创建 Deploy/ worktree

```bash
git worktree add Deploy deploy
```

### Step 8: 验证目录结构

```bash
ls -la
# 应包含：.git/ BA/ code/ Deploy/
```

### Step 9: 设置 CI 流水线

在 `code/` 目录中配置 CI 流水线（如 `.github/workflows/ci.yml`），确保 CI 只监听 `develop` 分支的变更。

### Step 10: 提交初始状态

```bash
git add .
git commit -m "[Init] 完成 workspace 初始化"
git push origin develop
```

## 验证清单

- [ ] `.git/` 目录存在
- [ ] `code/` worktree 存在且指向 `develop` 分支
- [ ] `BA/` worktree 存在且指向 `demand` 分支
- [ ] `Deploy/` worktree 存在且指向 `deploy` 分支
- [ ] `develop`、`demand`、`deploy` 分支已推送到远程
- [ ] `.gitignore` 已配置
- [ ] `code/` 目录兼容现有开发工具链