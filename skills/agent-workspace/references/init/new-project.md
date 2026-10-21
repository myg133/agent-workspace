# 新项目初始化

目标：一个只有 README 的裸仓库 → 可派单的 workspace（`code/` `BA/` `Deploy/` 就位，分支齐全）。

## 方式 A：一条命令（推荐）

```bash
python <skill-path>/scripts/aw.py init my-project \
  --name "My Project" \
  --remote git@github.com:org/my-project.git
```

脚本做的事（幂等，可重复执行）：

| 步骤 | 动作 |
|------|------|
| 1 | `git init` + 建立 `workspace` orphan 分支 + 2 个文件 + 首次 commit |
| 2 | 建立 `main` / `develop` / `demand` / `deploy` 分支 |
| 3 | 用 `git worktree add` 建 `code/` `BA/` `Deploy/` |
| 4 | 从模板落 `BA/` 的 bootstrap 文件（README、registry、rules）与 `.local/` |
| 5 | 配 `origin`（如给了 `--remote`）并设置本地 `push.default` |
| 6 | 自检：`git ls-files` 必须恰好 2 行 |

执行完跑一次：

```bash
cd my-project && python <skill-path>/scripts/aw.py verify
```

## 方式 B：手工（无 Python 环境时）

> **铁律**：`git checkout --orphan` 之后**用 `git reset` 清 index，绝不用 `git rm -rf .`**。
> 后者会把工作区文件一起删掉（实测：目录只剩 `.git`）。

### Step 1 仓库 + workspace 分支

```bash
mkdir my-project && cd my-project
git init
git commit --allow-empty -m "[Init] workspace root"
git branch -m workspace
```

### Step 2 根容器（只 2 个文件）

```bash
cp <skill-path>/assets/templates/root-readme.md.tpl README.md
cp <skill-path>/assets/templates/root-gitignore.tpl .gitignore
# 编辑 README.md 顶部占位
git add README.md .gitignore
git commit -m "[Workspace] 初始化导航 + 双层防御 .gitignore"
```

验证：`git ls-files` 只有 `.gitignore`、`README.md` 两行。

### Step 3 main / develop / demand / deploy

```bash
# main：生产发布标记（orphan，干净起点）
git checkout --orphan main
git reset                       # 只清 index，文件留在磁盘
printf '# %s\n' "My Project" > README.md
git add README.md
git commit -m "[Init] main branch placeholder"

# develop：从 main 派生
git checkout -b develop main

# demand：需求管理（orphan）
git checkout workspace
git checkout --orphan demand
git reset
mkdir -p demands backlog sprint decisions dispatch
printf '# 需求管理\n' > README.md
git add README.md
git commit -m "[Init] 需求管理分支"

# deploy：部署配置（orphan）
git checkout workspace
git checkout --orphan deploy
git reset
mkdir -p apps environments releases scripts
printf '# 部署配置\n' > README.md
git add README.md
git commit -m "[Init] 部署分支"

git checkout workspace
```

### Step 4 平铺 worktree

```bash
git worktree add code develop
git worktree add BA demand
git worktree add Deploy deploy
git worktree list
```

### Step 5 bootstrap 文件（否则 BA 启动就缺文件）

空目录 git 不跟踪。`BA/` 必须落真实文件：

```bash
cp <skill-path>/assets/templates/ba-readme.md.tpl        BA/README.md
cp <skill-path>/assets/templates/agent-registry.md.tpl   BA/dispatch/agent-registry.md
cp <skill-path>/assets/templates/req-registry.md.tpl     BA/dispatch/req-registry.md
cp <skill-path>/assets/templates/dispatch-rules.md.tpl   BA/dispatch/rules.md
cp <skill-path>/assets/templates/cleanup-log.md.tpl      BA/dispatch/cleanup-log.md
cp <skill-path>/assets/templates/deploy-readme.md.tpl    Deploy/README.md
```

在各 worktree 写入 `.local/` 与 `.gitignore`：

```bash
for d in code BA Deploy; do
  mkdir -p "$d/.local"/{discussions,analysis,drafts,references}
  grep -qxF '.local/' "$d/.gitignore" 2>/dev/null || echo '.local/' >> "$d/.gitignore"
done
```

按分支分别提交（三个 worktree 各自 commit）。

### Step 6 远程

```bash
git remote add origin <url>
git push -u origin workspace main develop demand deploy
# 在 GitHub/GitLab 把默认分支设为 workspace
```

## 验证清单

- [ ] `git ls-files`（在根）恰好 `.gitignore` + `README.md`
- [ ] `git worktree list` 四个条目，路径都在根下一层
- [ ] `code/`→develop，`BA/`→demand，`Deploy/`→deploy
- [ ] `BA/dispatch/` 下 4 个文件真的存在（不是空目录）
- [ ] `git add -A --dry-run` 在根不产生新条目
- [ ] `python <skill-path>/scripts/aw.py verify` 全绿
- [ ] 五个分支已推送，远程默认分支 = workspace

## 后续：接需求

```bash
# 在仓库根（推荐）
git worktree add feature-REQ-001 -b feature/REQ-001 develop

# 或在 BA/ 里（../ 回到仓库根）
cd BA && git worktree add ../feature-REQ-001 -b feature/REQ-001 develop
```
