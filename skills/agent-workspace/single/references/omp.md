# omp 唤醒插件

单机版不通过 MCP notification 唤醒，而是读本地 wake 文件：

```text
<local-root>/.aw/wake/<agent>.json
```

插件把新消息转成一次 omp 用户消息（`deliverAs: "steer"`），agent 下一轮用
`aw_single.py msg inbox` 取正文。

## 1. 安装

把 `agents/omp/aw-single-wake.ts` 复制到 omp 扩展目录：

**Windows**

```powershell
New-Item -ItemType Directory "$env:USERPROFILE\.omp\agent\extensions" -Force
Copy-Item agents\omp\aw-single-wake.ts "$env:USERPROFILE\.omp\agent\extensions\aw-single-wake.ts"
```

**macOS / Linux**

```bash
mkdir -p ~/.omp/agent/extensions
cp agents/omp/aw-single-wake.ts ~/.omp/agent/extensions/aw-single-wake.ts
```

重启 omp。

## 2. 启动环境

```powershell
$env:AW_AGENT_ID = "ba-1"
$env:AW_SINGLE_ROOT = "D:\proj"   # 可选；默认从 cwd 向上找 .aw/config.json
omp
```

- `AW_AGENT_ID` 决定读 `.aw/wake/<agent>.json`；
- `AW_SINGLE_ROOT` 是单机版本地根，不是代码仓库根；
- 不设 `AW_SINGLE_ROOT` 时，从 omp 会话 cwd 向上最多 8 层查找 `.aw/config.json`。

## 3. 启动 watcher

插件只读 wake 文件，不负责扫描 inbox。需要先跑：

```bash
aw_single.py watch --ensure --interval 5
```

然后：

```bash
aw_single.py msg send --to ba-1 --type question --body "ping"
```

watcher 写 `.aw/wake/ba-1.json`，插件读取后 steer。

Windows 下 watcher 使用 `CREATE_NO_WINDOW` + `STARTF_USESHOWWINDOW`，
git 子进程不会反复弹控制台窗口。

插件加载时还会写 `.aw/sessions/<agent>.json`（pid / pid_started_at / session），
并每 30 秒刷新 `last_seen`。watcher 用这个文件判断本机 agent 是否在线。

## 4. Presence

插件启动后：

1. 写 `.aw/sessions/<agent>.json`；
2. 每 30 秒更新 `last_seen`；
3. 进程正常退出时把 `pid` 写成 0；
4. watcher 扫描 session，更新 `.aw/presence/<agent>.json`。

查看：

```bash
aw_single.py presence --json
```

`status` 为 `online` / `offline`。MQTT presence 发布由 watcher 负责，后续接入。

## 5. 子 agent 与唤醒所有权

一个 agent 只能有一个主进程持有唤醒权。

插件加载时会读 `.aw/sessions/<agent>.json`：

- 如果里面的 `pid` 还活着，且不是当前进程 → 判定自己是子进程/重复会话；
- 直接关闭唤醒，日志写：
  `wake-disabled not-owner agent=ba-2 owner=<pid> me=<pid>`；
- 不会覆盖父会话的 session。

因此 BA spawn 的 QA/Dev 即使继承了 `AW_AGENT_ID=ba-2`，也不会再收到发给 ba-2 的 wake。

更稳妥的做法是 spawn 时设置：

```text
AW_WAKE_DISABLE=1
```

或者给子 agent 独立身份：

```text
AW_AGENT_ID=ba-2-qa
AW_ROLE=qa
```

## 6. 不要重复唤醒

- 用插件时，不要再给 `watch` 加 `--exec`；
- 同一 agent 只装一个 wake 插件；
- 多个 omp 会话共用一个 agent_id 时，插件会各自唤醒，建议一个 agent 一个会话。

## 6. 日志

默认：

```text
%USERPROFILE%\.omp\logs\aw-single-wake.log
~/.omp/logs/aw-single-wake.log
```

可用 `AW_OMP_WAKE_LOG` 覆盖。

应看到：

```text
loaded agent=ba-1 root=...
recv <id>
steer <n>
```

## 7. 验证

```bash
aw_single.py msg send --to ba-1 --type question --body "wake test"
Get-Content "$env:USERPROFILE\.omp\logs\aw-single-wake.log" -Tail 20
aw_single.py presence
```

omp 会话应出现一条 `[local] 收到 ...` 用户消息。
