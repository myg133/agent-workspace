# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/)。

## [1.4.0] - 2026-10-21

### 新增：升级检查（只读）

已运行项目升级到新版 skill 时，先看清要动什么。

- `aw.py upgrade [--json] [--idle-hours N]`：输出三段清单
  - **需要补**：BA/dispatch 的 4 个登记表、Deploy/README、feature 的 manifest
  - **需要清**：中间层 `workspaces/`、嵌套 worktree、已合并僵尸、失效登记、根分支污染、项目内 vendor 的旧 skill
  - **需要改**：根 `.gitignore` 的 `/*/`、各 worktree 的 `.local/`、旧文件名引用（`worktree-audit.md` 等）
- 附「不要动」护栏：不重建仓库、不 rebase、不改分支名。
- 僵尸 worktree 判定加入 `--idle-hours`（默认 1 小时），避免刚建的分支被误报。
- 新增 `references/lifecycle/upgrade.md`，含目录层面的「哪些要动 / 哪些不要动」对照表。

### 说明

1.x 内目录拓扑不变：升级是**补文件 + 改引用**，不是迁移。回滚只需删掉本次新增的文件。

## [1.3.0] - 2026-10-21

### 新增：任务认领（WIP=1）

同机多 BA 共享一个仓库时，解决"一个 BA 领了多个任务"。

- `aw.py claim whoami / next / take / release / list / doctor`
- `aw.py queue add / list / sync`（`sync` 从 `BA/demands/*/status.md` 扫"已就绪"）
- 身份：`AW_AGENT_ID`（稳定槽位）+ `AW_SESSION_ID` / `DSH_SESSION_ID`（本次启动）
- 互斥：`msvcrt.locking`（Windows）/ `fcntl.flock`（POSIX），进程退出自动释放
- 状态：`.aw/` 下**一个任务一个文件**，取代共享 Markdown 表的读-改-写竞态
- worktree 由认领创建（失败回滚），禁止手工 `git worktree add` 绕过
- 认领时把 `.feature/manifest.json` 提交到 feature 分支，记录"谁领的"
- `doctor --repair`：多领、死会话、缺 worktree 自动归档并退回队列

### 变更

- `req-registry.md` / `agent-registry.md` 降级为**只读快照**，认领真相在 `.aw/claims/`。
- SKILL 硬约束新增：认领是 worktree 唯一入口；一个 agent 只能持 1 个认领。
- `global/concurrency.md` 重写为"身份 + 锁 + WIP + doctor"，并补充共享工作区的 git 纪律
  （禁止 `git add -A`、commit 带 pathspec、index.lock 重试）。

## [1.2.1] - 2026-10-21

### 修复（Windows）

- **中文输出乱码**：启动时 `SetConsoleOutputCP(65001)` + stdout/stderr 统一 UTF-8。
  此前只设了 stdout，`cmd.exe`（cp936）下错误信息是乱码。
- **中文文件名迁移失败**：所有 git 调用加 `-c core.quotepath=false`。
  之前 `git ls-tree` 返回 `"\344\270\255..."` 形式的转义路径，导致"删不掉旧文件、搬不走进度"，
  迁移后根目录残留、`code/` 为空。
- **路径解析回归**：MSYS 返回的 `/c/...` 被 `pathlib` 判为非绝对路径，拼成 `C:\c\...`。
  现统一先做盘符映射再判断；顺手修了 `repo_root()` 对相对路径的回退。
- 子模块（gitlink）在迁移时用 `rmtree` 删除，不再抛 `IsADirectoryError`。
- `OSError` 统一转成可读提示（占用 / 不可写），不再甩 traceback。

### 新增（Windows 支持）

- `scripts/aw.cmd` 与 `scripts/aw.ps1` 启动器，自动在 `py` / `python` 之间选择。
- `references/global/platform-notes.md`：Windows（路径、长路径、跨盘符、文件占用、换行）、macOS、WSL。
- `verify` 在非 workspace 仓库给出明确提示（而不是刷一屏 FAIL）。

### 文档

- 补充「适用范围」：面向中大型项目、多需求并行、需要可追溯的交付；单文件脚本/一次性工具不适用。
- 明确本仓库（插件源码）自身不套用该规范，`aw.py verify` 在此报"不是 workspace 仓库"属预期。

### 已验证

- cmd.exe（cp936）下 audit/verify 中文正常。
- 含中文文件名的仓库迁移：跟踪文件进 `code/`，未跟踪文件保留，`verify` 全绿。
- 路径含空格 + 中文 + 非 ASCII 项目名的 init / verify / audit。
- 仓库在 D:、temp 在 C: 的跨盘符迁移。

## [1.2.0] - 2026-10-21

一次性交付原计划的 1.0.1（热修）+ 1.1.0（补全）+ 1.2.0（重构）。
**目录与分支模型未变**，已有 workspace 项目无需迁移。

### 修复（原 1.0.1）

- **破坏性命令**：把所有 `git checkout --orphan` 后的 `git rm -rf .` 改为 `git reset`。
  前者会连工作区文件一起删除（实测：目录只剩 `.git`）。
- **迁移流程跑不通**：原 Step 3→5 先建 `code/` 再 `git worktree add code develop`，必然报
  `fatal: 'code' already exists`；且会产生 `code/code/src` 双重嵌套。改为"先腾空根目录，再让 worktree add 把文件变进去"。
- 迁移文档中"根目录无 .gitignore"的错误表述。
- 重复粘贴的段落。
- 模板路径 `templates/` → `assets/templates/`。

### 变更（原 1.1.0 的规范清理）

- **单一写入者**：`status.md` 仅 BA 可写；QA 不 commit；Dev 只写 `.feature/`。删除 SKILL 中 QA 更新状态的步骤。
- **路径基准**：新增 `references/global/paths.md`，明确 `<repo-root>/BA/...` 才是跨 worktree 的正确写法。
- **新增 Explore 与 Release**：补上缺失的角色入口与 `develop → release → main` 发布/回滚流程。
- **多 BA 调优**：session ID 去掉 pid；stale 阈值 30 → 120 分钟；认领重试上限 3 次；活跃 BA > 3 启用号段。

### 新增

- `scripts/aw.py`：`init` / `migrate` / `verify` / `audit` / `next-req`。
- 校验脚本：11 项硬约束检查，可挂 CI / pre-commit，违规退出码 1。
- bootstrap 模板：`BA/dispatch/` 四个登记表、`Deploy/README`、各分支 `.gitignore`。
- `.feature/` 规范与模板：`manifest.json` / `status.md` / `traceability.md`。
- 根 README、LICENSE、CHANGELOG。

### 重构（原 1.2.0）

- `SKILL.md` 从 944 行拆为 138 行索引 + `references/{global,roles,init,lifecycle}`（15 篇）。
- Agent 定义从"复制规范"改为"指向规范"（薄壳），消除双份维护。
- 角色注入从"人肉截取 SKILL 段落"改为"给一个文件路径"。

### 迁移指南

- 1.0.x 项目：目录结构不变，但建议把 `status.md` 的写权限收归 BA，并在根目录跑一次 `aw.py verify`。
- 若曾在迁移中执行过 `git rm -rf .`，用 `git checkout <branch> -- .` 找回工作区文件。

## [1.0.0] - 2026-09

- 首个版本：workspace 根容器 + 平铺 worktree + 五角色工作流。
