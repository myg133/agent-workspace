# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/)。

## [1.8.1] - 2026-10-22

### 修复：消息与 manifest 泄露本机路径

- `msg send` 现在校验 `ref` 与 `body`，拒绝 `C:\...`、`/Users/...`、`/home/...`、UNC 等绝对路径
- `<repo-root>/...` 会在发送时归一化为仓库相对路径（`BA/contracts/...`）
- `.feature/manifest.json` 的 `demand_dir` 改为仓库相对路径，不再写入本机绝对路径
- 文档补充「消息里的路径约定」

原因：消息跨机器读（Mac 没有 `C:\`），且绝对路径会把用户目录、机器名与项目布局写进 bus 历史。

> 旧的 `.feature/manifest.json` 不会被自动改写；如果里面有绝对路径，手工改成 `BA/demands/...` 即可。

## [1.8.0] - 2026-10-22

### 新增：Planner 角色（总规划 / 设计 / 协调）

在 BA 之上增加一层规划角色，回答"做什么、先做什么、边界在哪"。

- `references/roles/planner.md`：定位、与 BA 的分工、`BA/plan/` 目录、节奏、容量指标、反模式
- `com.anspire-open.agents/anspire-open-planner.md`
- 写入权：Planner 只写 `BA/plan/` 与 `BA/decisions/`；不写需求、不改状态、不领 feature、不派单
- 8 个 BA 的容量管理：队列长度、认领等待、ack 中位数、返工率
- SKILL 路由表与硬约束同步更新（六个角色）

### 说明

Planner 目前是"纸面角色"：规范与定义已就位，尚未在真实流程中跑过完整周期。

## [1.7.1] - 2026-10-22

### 修复：消息游标会吞消息

- **根因**：旧实现用 `(at, id)` 时间游标。发送端时钟偏慢、或消息重试后补推，
  到达时 `at` 早于游标，就被判定为"已读"，**静默跳过**。
- **改法**：已读状态改为 **消息 id 集合**（`.aw/msg-read/<agent_id>.json`），与时间无关；
  旧游标首次运行自动迁移成等价 id 集合。
- `inbox` 与 `--limit` 现在取**最旧的 N 条**，且只标记真正显示过的，不再出现"只显示最新、旧的永久丢失"。
- `msg flush` 在无 remote 的仓库返回 0（此前误报 exit 3）。

### 说明

- 已读状态是**本机**的（`.aw/`），不随 git 同步；不同 `agent_id` 的已读集合互不影响。
- 同一 `agent_id` 共享一份收件箱，因此 Notifier 必须用 `--no-advance`。

## [1.7.0] - 2026-10-22

### 新增：强制人工指定 agent 名称

- 名称优先级：`--agent <name>` > `AW_AGENT_ID` > **硬失败**
- 没有名称时所有子命令 `exit 2`，输出 `MISSING_AGENT_ID` 与"询问用户后重试"的指令
- **不再自动生成名字**：共享目录下无法可靠区分会话，自动生成会导致重启换名、认领漂移
- `--agent` 可写在子命令前或后：`aw.py --agent ba-1 claim next` / `aw.py claim next --agent ba-1`
- `aw.py agent whoami` 显示 agent_id / session / 名称来源

### 新增：未读消息门禁 + Notifier 角色

- `claim next` 发现未读消息 → `UNREAD_MESSAGES <n>`，**exit 4**，不读消息不能领新任务（`--ignore-unread` 可强制）
- `msg inbox --json`、`msg show <id>`：供 Notifier 子 agent 消费
- 新增只读角色 `references/roles/notifier.md`：只允许 `inbox/show/list`，禁止 `send/ack/claim/git/写文件`
- `msg inbox --no-advance`：Notifier 读消息但不推进游标，失败不丢消息；游标只由 BA 自己推进
- `msg show <id>`：按 id 取单条完整消息（JSON），供摘要后追细节
- 对应 agent 定义：`com.anspire-open.agents/anspire-open-notifier.md`

## [1.6.1] - 2026-10-21

### 新增：可重跑的自测套件

- `skills/agent-workspace/tests/test_aw.py`，17 个用例，`python -m unittest discover -s skills/agent-workspace/tests -v`
- 覆盖：init 布局、verify 污染检测、claim 的 WIP=1 / 重启 / 并发、msg 寻址 / 游标 / ack / 离线队列 / bus 零文件、contract 四条 FAIL 规则、upgrade 检查
- 全部在临时目录运行，不改当前仓库

### 修复

- `git()` 超时现在转为 `GitError`，不再抛裸 `TimeoutExpired`
- `bus_flush` 现在把拉取/推送异常当作一次失败重试，离线时不会中断
- `_bus_fetch` 在读取路径上吞掉网络错误，读本地缓存

## [1.6.0] - 2026-10-21

### 新增：契约检查（跨 BA 接口对齐）

- `aw.py contract check [--strict] [--no-fetch] [--json]`
- 契约文件：`BA/contracts/<name>/vN.md` + `CURRENT`，已 ratified 的版本不可变
- 消费方在 `.feature/manifest.json` 里 `pin` 版本；缺失或落后都会失败
- 与消息通道联动：`contract-change` 后 consumer 未 `ack` → 超 deadline 失败，否则告警

检查规则：

| 规则 | 级别 |
|------|------|
| CURRENT 指向的版本文件不存在 | FAIL |
| feature pin < CURRENT | FAIL |
| feature pin > CURRENT | FAIL |
| consumer 未 pin | FAIL |
| 未声明 consumers | WARN |
| 契约变更未 ack | 超期 FAIL，否则 WARN |

文档：`references/global/contracts.md`；模板：`assets/templates/contract.md.tpl`。

## [1.5.0] - 2026-10-21

### 新增：BA 间消息（bus 分支）

统一走 git：**零文件的 `bus` 分支 + 空 commit**，commit message 即消息体。

- `aw.py msg send / inbox / list / ack / flush`
- 用 `git commit-tree` 造空 commit：**不 checkout、不碰工作区**，4 个 BA 并发安全
- 并发推送：被拒 → fetch → 基于最新 tip 重放 outbox → 重试（不 rebase、不 force）
- 离线可用：先落 `.aw/outbox/`，联网后自动重试
- 寻址：`agent_id` / `all` / `role:ba`；inbox 用本机游标只显示增量
- 契约回执：`msg ack <id> --ok|--reject`，生成 `contract-ack` 消息
- 输出标记 `→ me` / `→ me(cc)` / `→ <别人>`，避免误读

文档：`references/global/messaging.md`（格式、可见性、故障处理、规模估算）。
模板：`assets/templates/message.md.tpl`。

### 变更

- SKILL 硬约束新增：消息只走 bus，契约/决策才进 demand。
- 单条消息约 250B；4 BA × 20 条/天 ≈ 20KB/天，一年约 7MB。

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
