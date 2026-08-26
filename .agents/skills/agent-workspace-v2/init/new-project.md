# 新项目初始化流程

> 本流程使用 **`workspace` 分支**作为仓库根容器，所有 worktree **在仓库根平铺**（无中间目录层）。
> 不再使用"仓库根 = develop worktree"或"worktree 嵌套"的老设计。

## 流程

### Step 1: 创建 Git 仓库与 workspace 分支

```bash
mkdir my-project && cd my-project
git init
# 立即创建第一个空 commit，让 workspace 分支有合法根
git commit --allow-empty -m "[Init] workspace root"
# 把默认分支改名为 workspace
git branch -m workspace
```

**验证**：

```bash
git branch
# 输出：* workspace

git ls-files
# 应输出为空（空 commit 没有任何文件）
```

### Step 2: 写 workspace 根文档

**只跟踪 `README.md`，不写 `.gitignore`**（`.gitignore` 是本地文件，不进 workspace 分支）。

```bash
# 复制模板
cp <skill-path>/templates/root-readme.md.tpl README.md
# 编辑 README.md 顶部占位（项目名、一句话说明等）

# 注意：不要把 .gitignore 加入 git
# .gitignore 由各 agent 后续按需在自己 worktree 里创建
```

```bash
git add README.md
git commit -m "[Workspace] 初始化导航"
```

**验证**：

```bash
git ls-files
# 应只输出：README.md
```

### Step 3: 创建 develop / demand / deploy 分支

```bash
# 创建空分支（用 --orphan，干净起点）
git checkout --orphan develop
git rm -rf . 2>/dev/null || true
echo "# {项目名称} - develop" > README.md
git add README.md
git commit -m "[Init] develop branch placeholder"

git checkout workspace

git checkout --orphan demand
git rm -rf . 2>/dev/null || true
mkdir -p demands backlog sprint decisions dispatch
echo "# 需求管理分支" > README.md
git add README.md
git commit -m "[Init] 初始化需求管理分支"

git checkout workspace

git checkout --orphan deploy
git rm -rf . 2>/dev/null || true
mkdir -p apps environments releases scripts
echo "# 部署配置分支" > README.md
git add README.md
git commit -m "[Init] 初始化部署分支"

git checkout workspace
```

### Step 4: 在仓库根平铺创建 worktree

```bash
# 当前在 workspace/，worktree 直接在仓库根平铺
git worktree add code develop
git worktree add BA demand
git worktree add Deploy deploy
```

**验证**：

```bash
git worktree list
# 应输出（路径可能因 OS 不同）：
# <repo-root>      workspace  [<repo-root>]
# <repo-root>/code       develop    [<repo-root>/code]
# <repo-root>/BA         demand     [<repo-root>/BA]
# <repo-root>/Deploy     deploy     [<repo-root>/Deploy]

ls <repo-root>
# 应看到：README.md  .git/  code/  BA/  Deploy/
```

### Step 5: 推送到远程

```bash
git remote add origin <url>
git push -u origin workspace develop demand deploy
# 远程默认分支应设为 workspace（在 GitHub/GitLab settings 改）
```

## 验证清单

- [ ] `git branch` 显示 `workspace` 为当前分支
- [ ] 仓库根 `git ls-files` **只**输出 `README.md`
- [ ] 仓库根有 `code/`、`BA/`、`Deploy/` 三个 worktree 目录
- [ ] `code/` worktree → `develop` 分支
- [ ] `BA/` worktree → `demand` 分支
- [ ] `Deploy/` worktree → `deploy` 分支
- [ ] `workspace`、`develop`、`demand`、`deploy` 已推送到远程
- [ ] 远程默认分支 = `workspace`

## 后续创建 feature worktree

需求来了，从仓库根或从 `BA/`、`code/` 出发：

```bash
# 方式 1：在仓库根跑
git worktree add feature-REQ-001 -b feature/REQ-001 develop

# 方式 2：在 BA/ 里跑（用 ../ 回到仓库根，再下钻）
cd BA
git worktree add ../feature-REQ-001 -b feature/REQ-001 develop
```

新 worktree 跟 `code/` `BA/` 在仓库根平铺，**没有中间目录层**。
