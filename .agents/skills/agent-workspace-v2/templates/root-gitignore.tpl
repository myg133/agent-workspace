# workspace 分支 .gitignore —— 白名单防御机制
#
# 设计目标：即使误操作 `git add .`，workspace 分支也只会跟踪这两个文件：
#   - README.md   （项目导航）
#   - .gitignore  （本文件自身）
#
# 工作原理（git 白名单标准做法）：
#   1. `*`        忽略一切（文件 + 目录名）
#   2. `!*/`      不忽略目录（让下面的文件白名单能被"找回来"）
#   3. `!.gitignore`  例外：本文件自身必须被跟踪
#   4. `!README.md`   例外：项目导航必须被跟踪
#
# 其他 worktree（code/、BA/、Deploy/、feature-xxx/、hotfix-xxx/）的内容**一概不管**，
# 它们由各自 worktree 内的 .gitignore 在对应工作分支下管理。
#
# 几个关键分支（workspace / demand / deploy）是互相无父的独立分支（orphan），
# 各自完整地管理自己的 .gitignore，互不依赖。

# 1. 忽略所有
*

# 2. 不忽略目录（让文件白名单生效）
!*/

# 3. 显式白名单：workspace 分支只跟踪这两个文件
!.gitignore
!README.md
