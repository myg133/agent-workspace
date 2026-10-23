# Agent 身份（防漂移）

## 0. 为什么会"不知道自己是谁"

| 原因 | 表现 |
|------|------|
| 长会话上下文被压缩 | 开头那句"你叫 pcA-ba-1"被挤掉 |
| 工具不能注入环境变量 | 每条命令都是新进程，没有 `AW_AGENT_ID` |
| 模型遇到报错会"自救" | 看到 `MISSING_AGENT_ID` 后自己编一个名字继续跑 |
| 同一目录多会话 | 写一个 `.aw/agent-id` 文件也分不清谁是谁 |

结果：同一个 agent 在不同命令里用了不同名字，认领、消息、契约全部串位。

**对策：把身份锚在"终端"上，而不是锚在模型的记忆里。**

## 1. 解析顺序

```text
1. --agent <name>            （显式，最高）
2. AW_AGENT_ID               （启动器能注入时）
3. 终端锚点绑定               （本终端第一次指定时自动记住）
4. 都没有 → exit 2（MISSING_AGENT_ID）
```

## 2. 终端锚点

读取顺序：`WT_SESSION` → `TERM_SESSION_ID` → `TMUX_PANE` → `SSH_TTY` → `TTY`。

这些变量**由终端自己设置**，不依赖 agent 工具，也不依赖模型记不记得。

### 自动绑定

第一次带 `--agent` 执行时，会把这个终端与名字绑定：

```bash
aw.py --agent pcA-ba-1 agent whoami    # 顺便完成绑定
aw.py agent whoami                     # 之后不带参数也能认出来
```

### 显式绑定

```bash
aw.py agent bind pcA-ba-1      # 当前终端 → pcA-ba-1
aw.py agent bind pcA-ba-2 --force   # 改绑（会提示原绑定）
aw.py agent unbind             # 解除
```

### 同终端换名会被拒绝

```text
错误: 这个终端已经绑定 pcA-ba-1，不能改名成 pcA-ba-2。
要改绑定：aw.py agent bind pcA-ba-2 --force
```

这是防漂移的关键：**一个终端只允许一个名字**。

## 3. 一个终端跑多个 agent 怎么办

用 `--no-bind` 跳过终端绑定，每次显式带名字：

```bash
aw.py --agent pcA-ba-1 --no-bind claim next
aw.py --agent pcA-ba-2 --no-bind msg inbox
```

代价：没有任何自动记忆，必须保证每条命令都带对名字。

## 4. 漂移之后怎么修

```bash
# 1) 看当前终端到底是谁
aw.py agent whoami

# 2) 看所有绑定
cat .aw/identities.json

# 3) 改绑
aw.py agent bind <正确名字> --force

# 4) 检查错名产生的认领
aw.py claim list
aw.py claim doctor

# 5) 释放错名的认领（不删 worktree）
aw.py --agent <错名> claim release REQ-xxx --force
```

已经写进 bus 的消息改不了（禁止 force-push），只能统计影响范围后按新规则拦住。

## 5. 限制

| 场景 | 行为 |
|------|------|
| 无终端锚点（CI、服务、纯管道） | 只能每次显式 `--agent` |
| 同一终端多 agent | `--no-bind` + 每次显式 |
| 终端复用（同一 tab 重启） | 绑定仍在；若换了人，`bind --force` 修正 |
| `.aw/` 被删除 | 绑定丢失，重新 bind 一次 |

## 6. Roster（注册表）

`BA/plan/agents.json`，由 Planner 维护，随 `demand` 分支跨机器共享。

```bash
aw.py agent register pcA-ba-1 --role ba     # 注册 / 重新激活
aw.py agent publish                         # 提交并推送名册到 demand
aw.py agent roster --json                   # 看名单与本地会话
aw.py agent deactivate pcA-ba-2             # 停用（不再接收消息）
aw.py agent activate pcA-ba-2               # 恢复
```

注册只写本地文件；**必须 `agent publish` 推送到 demand，其他机器才看得到**。
其他机器 `git pull --rebase` 后才能 `agent roster` 看到新人。

`msg send` 会校验收件人：

| 收件人 | 规则 |
|--------|------|
| `pcA-ba-1` | 必须在 roster 中，且 `status=active` |
| `all` | 至少有一个 active agent |
| `role:ba` | 至少有一个该角色的 active agent |

未注册 / 未激活 → 直接拒绝，并列出已注册的名字。
`--force` 可绕过（应急用，不推荐）。

> 没配置 roster 时保持向后兼容（不拦）；建议项目一开始就建立名单。

## 7. 退出机制

```bash
aw.py agent exit            # 收工：session 置 offline + 解绑终端
aw.py agent exit --force    # 有认领时强制退出（认领会变成死会话，由 doctor 回收）
aw.py agent exit --keep-binding   # 保留终端绑定（同一终端换个名字继续用）
```

| 动作 | 作用域 | 效果 |
|------|--------|------|
| `agent exit` | 会话 | session 变 `offline`、终端解绑；不删历史 |
| `agent deactivate` | 名册 | 不再接收消息；跨机可见（随 demand 提交） |

推荐收工顺序：

```bash
aw.py claim release REQ-xxx --remove-worktree
aw.py agent exit
```

Planner 每周把长期不用的名字 `deactivate`，避免消息发给“幽灵”。

## 8. 自检

| 时机 | 命令 |
|------|------|
| 会话启动 | `aw.py agent whoami` |
| 认领前 | 由 `claim next` 隐式校验（无身份直接 exit 2） |
| 巡检 | Planner / BA 抽查 `.aw/identities.json` 是否有重复名字 |

## 9. 与 WIP 的关系

WIP=1 判定只看 `agent_id`：

- 换 session 不换名字 → 仍然只允许 1 个认领；
- 换名字 → 等于换人，历史认领不会自动跟过去（需要 `claim release` 或 `doctor --repair`）。

名字稳定是前提，终端绑定是让"稳定"不依赖模型记忆的手段。
