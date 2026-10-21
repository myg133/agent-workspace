# 已有项目迁移

把一个**已经在用**的 git 仓库原地转成 workspace 工作流。

**核心原则**：保历史、不动 commit hash、不新增业务分支的提交。
**禁止**：`git filter-branch`、`git rebase -i` 改写历史。

## 0. 前置条件（不满足不要开始）

```bash
git status --porcelain --untracked-files=no     # 必须为空（先 commit 或 stash）
git worktree list                                # 只应有 1 个条目（主 worktree）
git clone --mirror . ../backup-$(date +%s).git   # 兜底备份，必须做
```

> 有未提交的**已跟踪**改动时强行迁移 = 这些改动会被 develop 的已提交版本覆盖。先 commit。

## 1. 记录现状

```bash
MAIN=$(git rev-parse --abbrev-ref HEAD)   # 通常是 develop / main / master
git ls-tree -r --name-only "$MAIN" > /tmp/tracked.txt      # 会被 develop 管住的文件
git ls-files --others --exclude-standard > /tmp/untracked.txt  # 本地独有文件
```

## 2. 建 workspace 根容器（不动工作区）

```bash
git checkout --orphan workspace
git reset                                  # 只清 index；文件全部留在磁盘
```

此时 `git status` 会显示所有文件为 untracked —— 正常。

## 3. 写 2 个根文件并提交

```bash
cp <skill-path>/assets/templates/root-gitignore.tpl .gitignore
cp <skill-path>/assets/templates/root-readme.md.tpl README.md     # 再改占位
git add README.md .gitignore
git commit -m "[Workspace] 迁移：初始化根容器"
```

## 4. 把根目录腾空（关键步骤）

```bash
# 4.1 本地未跟踪文件挪到仓库外（.env、node_modules、本地配置 …）
mkdir -p ../aside
tar -cf - -T /tmp/untracked.txt | tar -xf - -C ../aside

# 4.2 develop 已跟踪的文件从根上删掉（README/.gitignore 除外，它们是根容器的）
grep -v -x -e README.md -e .gitignore /tmp/tracked.txt | xargs -r rm -f

# 4.3 清理空目录
find . -mindepth 1 -type d -empty -not -path './.git*' -delete
```

现在根目录只剩 `.git` `.gitignore` `README.md`。

## 5. 把 develop 挂到 code/

```bash
git worktree add code "$MAIN"     # 因为 code/ 不存在，一定成功
tar -cf - -C ../aside . | tar -xf - -C code/   # 本地文件放回 code/
rm -rf ../aside
```

`code/` 里现在有 develop 的**全部已跟踪文件** + 你的本地文件。

## 6. 建 demand / deploy 分支与 worktree

```bash
git checkout --orphan demand
git reset
mkdir -p demands backlog sprint decisions dispatch
printf '# 需求管理\n' > README.md
git add README.md && git commit -m "[Init] 需求管理分支"

git checkout workspace
git checkout --orphan deploy
git reset
mkdir -p apps environments releases scripts
printf '# 部署配置\n' > README.md
git add README.md && git commit -m "[Init] 部署分支"

git checkout workspace
git worktree add BA demand
git worktree add Deploy deploy
```

再按 `new-project.md` 的 Step 5 落 bootstrap 文件。

## 7. 远程默认分支与 CI

1. GitHub/GitLab → Settings → Branches → Default branch 改为 `workspace`。
2. CI 脚本里显式 checkout `develop`（不要依赖默认分支）：

```yaml
- uses: actions/checkout@v4
  with:
    ref: develop
```

3. 通知所有协作者重新 clone（旧 clone 里没有 worktree 拓扑）。

## 8. 验证

```bash
git ls-files                     # 恰好 .gitignore + README.md
git worktree list                # 根 + code + BA + Deploy
ls code | head                   # 原项目文件都在
git -C code status --porcelain   # 只有你自己的本地未跟踪文件
python <skill-path>/scripts/aw.py verify
```

## 9. 回滚

```bash
cd <repo-root>
git worktree remove code BA Deploy --force
git checkout "$MAIN"
git branch -D workspace demand deploy
```

历史没被改写，所以 develop 分支始终可用；`../backup-*.git` 是最后兜底。

## 常见错误

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| `git rm -rf .` 代替 `git reset` | **删光工作区文件** | `git reset` |
| 先把代码 `mv` 进 `code/` 再 `worktree add code develop` | `fatal: 'code' already exists`；即便成功也是 `code/code/src` | 先腾空根目录，让 worktree add 把文件"变"进去 |
| 迁移后根目录还留着 `src/` | workspace 分支被污染 | 按第 4 步删掉已跟踪文件 |
| 没备份就动手 | 无法回退 | `git clone --mirror` |
| 用 `--force` 跳过"工作区不干净"检查 | 丢掉未提交改动 | 先 commit |
