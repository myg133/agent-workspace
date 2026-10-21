# workspace 分支的 .gitignore（双层防御）

## 1. 完整内容

```gitignore
# 1. 忽略一切
*
# 2. 保留目录遍历，让下面的白名单生效
!*/
# 3. 白名单：只跟踪这两个文件
!.gitignore
!README.md
# 4. 屏蔽所有第一层子目录（worktree 都在第一层）
/*/
```

模板：`assets/templates/root-gitignore.tpl`

## 2. 每一行在解决什么

| 行 | 作用 | 去掉会怎样 |
|----|------|-----------|
| `*` | 忽略所有文件 | 业务文件全部可见 |
| `!*/` | 让 git 继续遍历目录（否则白名单永远匹配不到） | `README.md` 也被忽略 |
| `!.gitignore` `!README.md` | 只放行 2 个文件 | 根容器为空 |
| `/*/` | 不进入任何一层子目录 | worktree 目录以 gitlink 形式出现在 `git status`，`git add .` 可能写入 160000 条目 |

**关键**：git 无法"忽略目录但放行目录里的文件"。`/*/` 一旦生效，`code/` 内部任何文件都不可能被 workspace 分支跟踪 —— 这正是我们要的。

## 3. 验证方法（每次改动后跑一遍）

```bash
cd <repo-root>
git ls-files                      # 必须恰好两行：.gitignore / README.md
git add -A --dry-run              # 必须无新增条目
git status --porcelain            # 必须为空
```

`python skills/agent-workspace/scripts/aw.py verify` 已内置这三条检查。

## 4. 常见误解

| 说法 | 事实 |
|------|------|
| "worktree 目录是 embedded git repo，git 会自动保护" | 不会。`git add .` 会把它按 gitlink（mode 160000）暂存，产生脏历史 |
| "靠 `!*/` 就够了" | 不够。它让 git 进入目录，正是问题来源 |
| "workspace 分支要管所有 worktree 的 ignore" | 不管。各 worktree 的 `.gitignore` 由各自分支跟踪 |
| "根目录可以有 docs/ 放共享文档" | 不行。要么放 `BA/`，要么另开 orphan 分支 |
