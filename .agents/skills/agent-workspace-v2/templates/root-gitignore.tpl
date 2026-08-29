# workspace 分支 .gitignore —— 白名单防御 + /*/ 子目录屏蔽（双层防御）
#
# 设计目标：即使误操作 `git add .`，workspace 分支也只会跟踪这 2 个元数据文件：
#   - README.md   （项目导航）
#   - .gitignore  （本文件自身）
#
# 工作原理（git 白名单标准做法 + /*/ 屏蔽）：
#   1. `*`        忽略一切（文件 + 目录名）
#   2. `!*/`      不忽略目录（让下面的文件白名单能被"找回来"）
#   3. `!.gitignore`  例外：本文件自身必须被跟踪
#   4. `!README.md`   例外：项目导航必须被跟踪
#   5. `/*/`      **关键**：忽略所有第一层子目录（worktree 目录都在第一层）
#                防止 git add . 进入 worktree 把内部文件 add 进来
#                也防止 worktree 目录的 .git file 干扰 git 状态
#
# 为什么需要第 5 步：
#   worktree 目录（code/ BA/ Deploy/ feature-xxx/ hotfix-xxx/）是 embedded git repos，
#   内部有 .git file 指向 .git/worktrees/<name>/。如果只靠白名单（第 1-4 步），
#   !*/ 会让 git 遍历这些目录，可能误 add 或显示 untracked。
#   /*/ 显式忽略所有第一层子目录，从源头阻止任何 worktree 内部文件进入 workspace 分支。
#
# 其他 worktree 各自管各自的 .gitignore（code/.gitignore 由 develop 跟踪，等等），
# workspace 分支一概不管。
#
# 几个关键分支（workspace / demand / deploy）是互相无父的独立分支（orphan），
# 各自完整地管理自己的 .gitignore，互不依赖。

# 1. 忽略所有
*

# 2. 不忽略目录（让白名单生效）
!*/

# 3. 显式白名单：workspace 分支只跟踪这两个文件
!.gitignore
!README.md

# 4. 忽略所有第一层子目录（worktree 都在第一层）
/*/
