# 已有项目迁移流程

> 把一个**已有 git 仓库**（有 commit、tag、可能已发布）原地转成 `workspace` 工作流。
> **核心原则：保历史、不动 commit hash、新建 workspace 分支作为新默认**。
> 禁止使用 `git filter-branch` / `git rebase -i` 改写历史。

## 适用场景

- 已有 `develop`（或 `master`/`main`）分支和代码
- 可能有 tag、release、别人 fork
- 想要物理平铺的 worktree 结构（`code/`、`BA/`、`Deploy/` 都在仓库根）
- 现状可能是：仓库根 = 主 worktree（一般是 develop），worktree 嵌套在仓库根内

## 流程

### Step 0: 备份

```bash
# 完整镜像备份（含所有引用对象）
git clone --mirror <url> backup.git

# 验证备份可独立使用
cd backup.git && git fsck && cd ..
```

### Step 1: 确认当前分支结构

```bash
git branch -a
# 记录主开发分支名称（develop / master / main）
git worktree list
# 记录现有 worktree 状态
```

### Step 2: 创建 workspace 分支

```bash
# 在仓库根跑
git checkout --orphan workspace
git rm -rf . 2>/dev/null || true
git commit --allow-empty --allow-empty-message -m "[Init] workspace root"
```

> `--orphan` 切到新分支，但工作区文件还在。`git rm -rf .` 仅清跟踪，不删工作区文件。
> 接下来需要把工作区文件搬到 `code/` 子目录（因为原本属于 develop 分支）。

### Step 3: 把当前工作区文件搬到 code/

```bash
# 此时在 workspace/ 工作区，文件还没动
# 但我们要建一个 code/ 子目录，把 develop 的工作文件全放进去

mkdir code
# 用 shell 把所有非 .git / workspace 自身文件移到 code/
# PowerShell（Windows）：
Get-ChildItem -Force | Where-Object { $_.Name -ne '.git' -and $_.Name -ne 'code' } | Move-Item -Destination .\code\

# Bash（Linux/macOS）：
# shopt -s dotglob
# mv !(code|.git) code/   # 需要 extglob
```

**关键**：搬完后的目录结构：

```
<repo-root>/
├── .git/
├── README.md                    # workspace 的 README（待写）
├── .gitignore                   # 本地文件
└── code/                        # develop 原本的所有文件都在这里
    ├── src/
    ├── tests/
    ├── package.json
    └── ...
```

> 如果原项目 worktree 是嵌套结构（如 `code/feature-xxx/`），需要先把嵌套目录拍平：
> 把 `code/feature-xxx/` 里的内容合并到 `code/` 一层。

### Step 4: 写 workspace 的 README + 白名单 .gitignore

```bash
# 用模板
cp <skill-path>/templates/root-readme.md.tpl README.md
cp <skill-path>/templates/root-gitignore.tpl .gitignore
# 编辑 README.md 顶部占位
git add README.md .gitignore
git commit -m "[Workspace] 初始化导航 + 白名单 .gitignore"
```

**验证**：

```bash
git ls-files
# 应只输出：
# .gitignore
# README.md
```

### Step 5: 把 develop 重新挂到 code/

```bash
# 现在 code/ 在工作区，但 git 还没把它识别为 develop 分支
# 需要把 code/ 的文件 commit 到 develop 分支
# 切换分支会改变工作区——用 stash 保存

git stash -u  # 保存所有未跟踪内容（含 code/ 目录）
git checkout develop
git stash pop  # code/ 回到工作区
git add code/
git commit -m "[Migrate] 迁移到 workspace 工作流 (关联: 基础设施)"

# 现在可以正常用 worktree
git checkout workspace
git worktree add code develop
```

> **Step 5 是迁移中最 tricky 的**。备选方案：如果接受一个"迁移 commit"，直接走上面流程；
> 如果完全不想加 commit，可以用 `git read-tree` 等更底层命令，但操作复杂，**不推荐**。

### Step 6: 创建 BA / Deploy 分支并登记 worktree

```bash
git checkout --orphan demand
git rm -rf . 2>/dev/null || true
mkdir -p demands backlog sprint decisions dispatch
echo "# 需求管理" > README.md
git add README.md
git commit -m "[Init] 需求管理分支"

git checkout workspace

git checkout --orphan deploy
git rm -rf . 2>/dev/null || true
mkdir -p apps environments releases scripts
echo "# 部署配置" > README.md
git add README.md
git commit -m "[Init] 部署分支"

git checkout workspace

git worktree add BA demand
git worktree add Deploy deploy
```

### Step 7: 改远程默认分支

**在 GitHub / GitLab settings 操作**（不是 git 命令）：

1. 进入仓库 Settings → Branches
2. Default branch: 选择 `workspace`
3. 确认切换

### Step 8: 改 CI / CD 工作流

CI 配置文件一般在 `code/` 目录下（develop 分支）。需要确认：

```yaml
# code/.github/workflows/ci.yml
on:
  push:
    branches: [develop, main]   # 不再需要 workspace
  pull_request:
    branches: [develop, main]

jobs:
  build:
    runs-on: ubuntu-latest
    # CI 在 GitHub Actions 上 checkout develop 分支
    # 工作目录是 develop 分支的根（即 code/ worktree 的内容）
    # 所以脚本里的路径仍是 src/ tests/，不需要改
    steps:
      - uses: actions/checkout@v4
        with:
          ref: develop
      - run: pnpm install
      - run: pnpm test
```

### Step 9: 验证

```bash
git worktree list
# <repo-root>      workspace  [<repo-root>]
# <repo-root>/code       develop    [<repo-root>/code]
# <repo-root>/BA         demand     [<repo-root>/BA]
# <repo-root>/Deploy     deploy     [<repo-root>/Deploy]

ls <repo-root>
# README.md  .git/  code/  BA/  Deploy/   （无 .gitignore，因为不跟踪）

cd <repo-root>/code
ls
# 应看到原项目的所有文件：src/ tests/ package.json ...
git log --oneline -5
# 应看到原 develop 分支历史 + 可能的 [Migrate] commit

cd <repo-root>
git ls-files
# 应只输出：
# .gitignore
# README.md
```

## 风险提示

- 迁移前**必须**确保所有团队成员已提交变更
- 迁移后**必须**通知所有成员重新 clone（worktree 路径变了，旧的 worktree 失效）
- 代码路径变化后需更新 IDE 配置和 CI 路径
- 远程默认分支切换**必须**先在 GitHub/GitLab 备份 develop 分支
- 建议在测试分支上先验证整个流程

## 回滚

如果迁移出问题：

```bash
# 1. 恢复远程默认分支 → develop（在 GitHub/GitLab settings）
# 2. 通知所有成员回退：
#    - 删除本地 workspace 分支
#    - git worktree remove code BA Deploy
#    - 重新 git pull origin develop
# 3. 备份仓库 (backup.git) 始终可作最后兜底
```
