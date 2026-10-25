# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/)。

## [1.25.1] - 2026-10-25

### 文档：README 增加 bus 可视化配套仓库

- 新增「配套：bus 消息可视化」：指向
  [agent-workspace-bus-viewer](https://github.com/myg133/agent-workspace-bus-viewer)
- 说明 build / serve / `--remote` 三种用法，以及"只读 bus、不替代 aw.py msg"的边界
- 自测用例数从 42 更新为 61

## [1.25.0] - 2026-10-25

### 新增：欠回复强制门禁

- `claim next` / `claim take`：有 `expect=ack/reply` 未回复时拒绝，exit 4，列出前 5 条
- `agent exit`：有欠回复时拒绝，exit 3；`--force` 可强退
- 新增 `--ignore-pending`（claim）作为显式逃生口
- `stats` 新增 `obligations_pending`（全局未结清消息数）
- MCP：`claim_next` / `claim_take` 支持 `ignore_pending`
- 文档：messaging.md「强制门禁」、BA 硬规则、SKILL 全局规则

## [1.24.0] - 2026-10-25

### 新增：消息反馈义务（expect / pending / reply）

- 消息新增 `expect` 字段：`none` / `ack` / `reply`，默认按 type 推导
- 新增 `reply_by` 可选字段
- 新增 `msg pending`：列出等我还账的消息（expect 非 none 且未回复）
- 新增 `msg reply <id> --body`：自动带 `re` / `thread` / 收件人 / 契约版本
- `msg inbox` / `msg list` / `msg wait` 输出标记 `↩reply` / `↩ack`
- MCP 新增 `msg_pending` / `msg_reply`，`msg_send` 支持 `expect` / `reply_by`
- 文档：messaging.md「反馈义务」、BA 不发呆、Planner 每日清 pending

## [1.23.1] - 2026-10-24

### 消息发送体验

- body 超限报错改为：**当前字数 + 具体落盘建议**（`BA/demands/<REQ>/notes.md`）
- 绝对路径检查跳过 fenced code block，避免日志/代码示例里的 `C:\` 误伤
- `messaging.md` 同步：body 上限、code fence 豁免、名册改为 BA 自注册 + Planner 审批

## [1.23.0] - 2026-10-24

### 新增：stats 统计"每个 REQ 的升级问题数"

- `collect_stats` 解析 bus 上 `type: question` 的消息，按 `ref` 中的 `REQ-xxx` 归组
- 新增字段：`questions_total`、`questions_last_7d`、`questions_by_req`、
  `reqs_tracked`、`questions_per_req`
- 表格输出新增一行 `questions`（总数 / 7 天 / 每 REQ）
- 口径：分母 = 有认领 + 在队列 + 被提问过的 REQ 数
- 文档：`decision-rights.md` §8 度量改为可直接对照 stats 字段

## [1.22.0] - 2026-10-24

### 新增：决策权与升级协议（解决 BA 过度依赖 Planner）

- 新增 `references/global/decision-rights.md`：
  - 决策权矩阵：细节归 BA、顺序归 Planner、范围归用户
  - 只有四种情况可以升级：跨 BA 冲突 / 优先级 / 不可逆 / 文档矛盾
  - 提问必须带 `proposal + default`；没有提案不回答
  - 沉默即同意：Planner 2 小时不回复，BA 按 default 执行
  - 每个 REQ 的 `decisions.md` + Planner 周检
- `roles/ba.md` 新增「默认自决」；需求目录增加 `decisions.md`
- `roles/planner.md` 新增「回答而不是重做」：默认批准 BA 的提案，只在四种情况否决
- 模板：`assets/templates/decisions.md.tpl`

## [1.21.0] - 2026-10-24

### 改为 BA 自注册 + Planner 审批

- `agent register` 不再要求 Planner 令牌：**BA 自己注册自己**
- team 模式（存在带令牌的 active Planner）下，自注册为 `pending`；
  Planner 执行 `agent_activate` 后才 `active`
- solo 模式（无 Planner）直接 `active`
- 重新注册已有名字：需要本人 token 或 Planner token，防止被顶替
- `agent activate/deactivate` 在 team 模式下需要 Planner 令牌
- 发送消息前检查发送者状态：`pending` 直接拒绝
- 文档：BA 增加「注册自己」，Planner §4.1 改为「名册审批（不代注册）」

## [1.20.1] - 2026-10-24

### 文档：三个角色改为 MCP 工具调用

- `roles/ba.md`、`roles/planner.md`、`roles/notifier.md` 的命令示例
  从 `aw.py xxx` 改为 `工具名 {参数}` 形式
- 覆盖 claim / msg / queue / contract / agent / audit / doctor / stats 全部调用
- 唯一保留的 CLI：`agent register --issue-token`（bootstrap / token 是人类的系统外动作）
- 每个文件顶部注明：agent 不要 shell 调 `aw.py`，CLI 等价命令见 mcp.md 对照表

## [1.20.0] - 2026-10-24

### MCP 工具面补齐 + 移除内置 bus-report

- 新增 MCP 工具：`next_req` `msg_list` `msg_flush` `doctor` `stats` `agent_check`
- `mcp.md` 新增「CLI → MCP 对照」：覆盖全部 agent 运行命令，并标注仅 CLI 的人类运维命令
- SKILL 明确：**agent 运行时一律走 MCP**；CLI 只用于 init/migrate/upgrade/bootstrap/token/mcp install
- 移除 `references/global/bus-report.md` 及 SKILL/README 中的 bus-report 条目：
  外部工具不内置进 skill

## [1.19.1] - 2026-10-24

### 文档：消息面板 bus-report

- 新增 `references/global/bus-report.md`：三种形态（build / serve / watch）、
  `--remote` 零 clone、产出文件、时间口径、只读边界
- SKILL 路由表新增「看消息 / 沟通报告」
- `aw.py stats` 末尾提示用 bus-report 看消息
- 不重复实现 HTML 面板：数字归 `stats`，消息归 `bus-report`

## [1.19.0] - 2026-10-24

### 新增：doctor / stats / CI 矩阵 / 抢占式 bootstrap

- `aw.py doctor`：一页聚合 workspace、拓扑、认领、队列、契约、solo/team 模式；有 FAIL 时退出码 1
- `aw.py stats [--json]`：active claims、最老认领/队列、session 存活、消息数、ack 中位数、worktree 数
- `.github/workflows/test.yml`：Ubuntu / macOS / Windows 三平台跑 52 个测试
- `agent bootstrap <name>`：名册为空时抢占式注册第一个 Planner（文件锁防并发）
- `agent register`：名册里存在带令牌的 Planner 时，必须提供 Planner 令牌（`--agent-token`）

### 说明

- bootstrap 只在名册为空时可用；名册非空但没有 Planner 时不会自动放开
- 名册里没有带令牌的 Planner 时，register 保持旧行为（向后兼容）

## [1.18.1] - 2026-10-24

### 文档：Planner 的启用与单人模式

- `planner.md` 新增 §0：
  - 第一个 Planner 的注册方式（名册为空也能注册）
  - 单人 / 单 BA 模式：没有 active Planner 时 BA 可代行规划、直接 `claim take`
  - 从 solo 切到 team 的四步
- `agent roster` 增加 `mode: solo|team` 判定；多个 BA 但没有 Planner 时给出提示
- `agent roster --json` 返回 `{"mode": ..., "agents": [...]}`

## [1.18.0] - 2026-10-24

### 新增：agent 令牌，防止 MCP 冒名

只靠 `agent_id` 是自报的，任何会话都能填别人的名字。现在注册时签发一次性 token：

- `aw.py agent register <name> --issue-token` 生成并打印 `TOKEN <name> <token>`（只显示一次）
- roster 只存 SHA-256 哈希，不存明文
- MCP 调用带 `token` 参数，或设置 `AW_AGENT_TOKEN`；CLI 用 `--agent-token`
- token 缺失/错误 → `BAD_TOKEN`，工具不执行
- `aw.py agent token <name>` 轮换，旧 token 立即失效
- 文档：mcp.md「令牌：防止冒名」、identity.md 注册流程

### 说明

token 仍在该 agent 的上下文里，不能防住"自己人"；它挡住的是**跨会话冒名**。
注册入口本身是信任式的（能写 `BA/plan/agents.json` 才能注册）。

## [1.17.0] - 2026-10-24

### 新增：MCP 工具支持每次调用传 agent_id

桌面端 agent 拿不到 `AW_AGENT_ID`，之前所有工具都会返回 `MISSING_AGENT_ID`。

- 每个 MCP 工具新增可选参数 `agent_id`
- 优先级：调用参数 > 环境变量 `AW_AGENT_ID` > 报错
- 参数会作为 `--agent` 传给 `aw.py`，行为与 CLI 一致
- 返回体里的 `agent` 字段反映本次实际使用的身份
- 文档：mcp.md 新增「没有环境变量时：每次调用带 agent_id」

### 说明

`agent_id` 是自报的，工具只能校验 roster 是否存在且 active，不能证明归属；
多会话共用同一个 MCP 服务进程时，必须每次显式传入。

## [1.16.0] - 2026-10-23

### 新增：bus 写权限限定

- 只有 **BA / Planner** 能执行 `msg send` / `msg ack` / `msg flush`
- 子 agent（Dev / QA / Deploy / Explore / Notifier）调用会被拒绝：
  `bus 只允许 BA / Planner 使用；子 agent 请与你的 BA 交互`
- 角色判定：`AW_ROLE` 环境变量 > roster `role` > 默认 `ba`
- 读取（inbox / wait / show）不受限，供 Notifier 代读
- 文档：messaging.md 新增「谁能写 bus」，五个角色文档补充硬规则

## [1.15.1] - 2026-10-23

### 文档：客户端差异

- `mcp.md` 新增「omp / mcode / DSH」配置对照：文件位置、父键、工具名前缀、env 处理
- 记录两个实测限制：mcode 的 `cwd` 只接受 `./` / `${PLUGIN_ROOT}`；DSH 必须用 `!!js` 转发 `AW_AGENT_ID`
- SKILL 的 MCP 判定改为**后缀匹配**（兼容 `mcp__aw__` 前缀），并说明 DSH 工具命名

## [1.15.0] - 2026-10-23

### 新增：MCP 安装与使用策略

- `aw.py mcp status / install / ensure / print`：检测并写入 Claude Desktop / Cursor / VS Code / Claude Code 配置
- 安装前自动备份原配置；已安装则输出 `ALREADY INSTALLED`
- 生成 `.aw/mcp/aw-mcp.cmd`（Windows）或 `.aw/mcp/aw-mcp.sh`（POSIX）包装器，解决客户端不支持 `cwd`
- SKILL 增加 MCP 使用策略（硬规则）：
  - 工具列表有 `agent_whoami` → 必须用 MCP，禁止 shell 调 CLI（诊断除外）
  - 没有 → 先 `mcp ensure`，再退回 CLI，并提示重启
  - 同一会话不混用 MCP 与 CLI

### 说明

MCP 工具不能热加载，安装后必须重启客户端；“强制安装”指流程强制，不是当前会话即时生效。

## [1.14.1] - 2026-10-23

### 文档：把 MCP 工具写进 SKILL

- `SKILL.md` 增加 MCP 工具分组表（身份/认领/消息/门禁/队列）与统一返回约定
- 明确 `0 / 3 / 4` 是业务正常，只有真正失败才 `isError`
- 明确「能阻塞就不要轮询」，等消息优先 `msg_wait`
- 路由表新增「通过 MCP 调用」一行
- README 测试数从 17 更新为 42

## [1.14.0] - 2026-10-23

### 新增：Linux / macOS 支持

- `scripts/aw`：POSIX shell 启动器（等价于 Windows 的 `aw.cmd`），已做 `sh -n` 语法检查
- `.gitattributes`：强制 `*.sh` / `scripts/aw` 以 LF 检出，避免 Windows 克隆后 shebang 失效
- MCP 文档新增「Linux / macOS」：客户端配置路径、`python3`、`export AW_AGENT_ID`、不支持 `cwd` 时的包装脚本
- `platform-notes.md` 同步 POSIX 启动方式

### 说明

锁实现本来就分平台：Windows 用 `msvcrt.locking`，POSIX 用 `fcntl.flock`；本次补齐启动器与文档。CI 仍未覆盖 macOS/Linux 实跑。

## [1.13.0] - 2026-10-23

### 新增：msg_wait（阻塞等待消息）

- CLI：`aw.py msg wait --timeout 120 --interval 5 [--thread ...] [--contract ...] [--type ...] [--sender ...] [--consume] [--json]`
- 命中返回消息，退出码 0；超时返回 `WAIT_TIMEOUT` / `found:false`，退出码 3
- **默认不消费**（不推进已读），`--consume` 才标记
- MCP 新增 `msg_wait` 工具，服务端阻塞，一次调用替代 24 次 5 秒轮询
- 文档：mcp.md / messaging.md 补充等待与轮询分档

## [1.12.0] - 2026-10-23

### 新增：注册流程进 MCP + 名册发布

- MCP 新增工具：`agent_register` / `agent_activate` / `agent_deactivate` / `agent_publish` / `agent_exit`
- `agent_roster` 改为返回 JSON（`id / role / status / host / session_alive`）
- CLI 新增 `aw.py agent publish`：提交 `BA/plan/agents.json` 并推送到 `demand`，带 pull --rebase 重试
- 名册仍是**仓库内文件**（`BA/plan/agents.json`），保证 agent 之间互相可见；publish 是让跨机可见的关键一步
- 文档补充注册流程：register → publish → pull → roster

## [1.11.0] - 2026-10-23

### 新增：stdio MCP 适配层

- `scripts/aw_mcp.py`：把 `aw.py` 暴露为 17 个 MCP 工具（无第三方依赖）
- 一个 agent 一个进程：`AW_AGENT_ID` 由启动环境注入
- 服务器启动时固定 `AW_AGENT_PID=本进程 pid`、`AW_SESSION_ID=proc-<pid>`，
  **身份与进程绑定，不再依赖 session_id 关联**
- 工具返回统一 JSON（`ok / exit_code / stdout / stderr / agent`），
  0/3/4 视为业务正常，只有真正失败才是 `isError`
- 参数 schema 覆盖枚举与必填项，agent 不需要读源码
- 文档：`references/global/mcp.md`

### 说明

MCP 只做调用面，逻辑仍全部在 `aw.py`；CLI 保留，供 CI、脚本与不支持 MCP 的客户端使用。

## [1.10.0] - 2026-10-23

### 新增：Agent 名册 + 收件人校验 + 退出机制

**问题**：Planner 会自己造 agent 名字，给根本没注册过的 agent 发消息。

- 名册 `BA/plan/agents.json`（随 demand 分支跨机共享）
- `aw.py agent register <name> [--role ba]` / `agent roster` / `agent activate|deactivate`
- `msg send` 校验收件人：必须已注册且 active；`all` / `role:x` 要求至少一个 active
- 未注册直接拒绝并列出可用名字；应急 `--force` 可绕过
- `aw.py agent exit`：session 置 offline、解绑终端；有认领时拒绝（`--force` 强制，认领变死会话）
- `agent whoami` 增加 roster 状态

### 说明

- 未配置 roster 时保持向后兼容（不拦截）；建议项目一开始就建立名册。
- exit 是会话级，deactivate 是名册级：收工用 exit，长期离岗用 deactivate。

## [1.9.0] - 2026-10-23

### 新增：终端锚点绑定，修复 agent 身份漂移

现象：长会话里几个 agent 忘了自己叫什么，同一 agent 在不同命令用了不同名字，认领与消息串位。

根因：身份只存在于"模型记忆 + 环境变量"，而上下文会压缩、工具又注入不了环境变量。

修复：

- 身份解析新增第三层：**终端锚点**（`WT_SESSION` / `TERM_SESSION_ID` / `TMUX_PANE` / `SSH_TTY` / `TTY`）
- 首次带 `--agent` 时自动把当前终端与该名字绑定；之后不带参数也能识别
- `aw.py agent bind <name> [--force]` / `agent unbind` 显式管理
- **同终端换名直接拒绝**，这是防漂移的关键
- `--no-bind`：一个终端跑多个 agent 时跳过绑定，每次显式带名字
- `agent whoami` 显示 `source`（--agent / env / terminal）与当前锚点

文档：`references/global/identity.md` 重写，含漂移后的修复步骤与限制。

### 修复

- **并发写同一 JSON 冲突**：`write_json` 的临时文件名改为「进程号 + 随机」，修复 Windows `WinError 32`
- **绑定读写竞态**：`identities.json` 的读-改-写加锁，避免并发丢失绑定
- **并发建 worktree 失败**：`git worktree add` 用项目锁串行化（.git/worktrees 锁竞争）
- **消息顺序**：改为 bus 提交顺序（旧→新），不再按时间戳排序；同一秒内的消息也能正确分页

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
