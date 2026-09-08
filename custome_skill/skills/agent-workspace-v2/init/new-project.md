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

### Step 2: 写 workspace 根文档（README + 双层防御 .gitignore）

**workspace 分支只跟踪两个文件**：`README.md` + `.gitignore`。
`.gitignore` 使用**双层防御机制**：
- **白名单层**：`*` 全忽略 + `!*/` 保留目录遍历 + 白名单 `!.gitignore` + `!README.md`
- **`/*/` 屏蔽层**：忽略所有第一层子目录（worktree 都在第一层，防止 git 遍历 worktree）

即使误操作 `git add .`，也只会 add 这两个文件，worktree 完全不被影响。

```bash
# 复制模板
cp <skill-path>/templates/root-readme.md.tpl README.md
cp <skill-path>/templates/root-gitignore.tpl .gitignore
# 编辑 README.md 顶部占位（项目名、一句话说明等）
# .gitignore 一般不用改
```

```bash
git add README.md .gitignore
git commit -m "[Workspace] 初始化导航 + 双层防御 .gitignore"
```

**验证**：

```bash
git ls-files
# 应只输出：
# .gitignore
# README.md

# 防御性测试：即使误操作 git add . 也只 add 这两个文件
git add .
git status --short
# 应为空（没有新文件需要 add，白名单只放过这两个）
# 关键：worktree 目录（code/ BA/ Deploy/）也不会显示为 untracked，
# 因为 /*/ 屏蔽了所有第一层子目录
```

### Step 3: 创建 main / develop / demand / deploy 分支

```bash
# main 为生产分支（orphan 独立，干净起点）
git checkout --orphan main
git rm -rf . 2>/dev/null || true
echo "# {项目名称}" > README.md
git add README.md
git commit -m "[Init] main branch placeholder"

# develop 从 main 派生，共享历史
git checkout -b develop main

# demand 和 deploy 为 orphan 独立分支（管理与代码隔离）
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
git push -u origin workspace main develop demand deploy
# 远程默认分支应设为 workspace（在 GitHub/GitLab settings 改）
```

## 验证清单

- [ ] `git branch` 显示 `workspace` 为当前分支
- [ ] 仓库根 `git ls-files` **只**输出 `.gitignore` 和 `README.md`
- [ ] 仓库根有 `code/`、`BA/`、`Deploy/` 三个 worktree 目录
- [ ] `code/` worktree → `develop` 分支
- [ ] `BA/` worktree → `demand` 分支
- [ ] `Deploy/` worktree → `deploy` 分支
- [ ] `workspace`、`main`、`develop`、`demand`、`deploy` 已推送到远程
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
