# 消息可视化：bus-report

`bus-report` 是独立工具（不在本 skill 内），从 `bus` 分支生成 BA 沟通报告。
本 skill 不重复造面板，只在需要看消息时指向它。

示例路径：`D:\Projects\bus-report`。

## 1. 三种形态

### 静态报告（可单独发人）

```bash
cd D:/Projects/bus-report
bun run bus-report.ts build --repo D:/path/to/workspace --out ./out
```

打开：

```text
out/ba-bus-communication.html
```

数据内嵌在 HTML 里，单文件可转发。

### 实时服务（推荐日常看）

```bash
bun run bus-report.ts serve --remote git@host:group/repo.git --out ./out --port 8787
```

浏览器打开 <http://127.0.0.1:8787>，点「刷新数据」会现场 fetch 一次 bus。

### 定时重建

```bash
bun run bus-report.ts watch --remote <url> --out ./out --interval 10
```

## 2. 不 clone 也能读（--remote）

bus 的 commit 是空 commit（tree 恒为空树），消息只在 commit message 里。
`--remote` 只建一个 bare 缓存 `out/.bus-cache.git`，只 fetch `bus` 一个 ref：

- 对目标仓库零接触：不 clone、不检出、不写工作区；
- 冷启动约 1.6s / 数百 KB；增量刷新通常 <1s；
- 只要机器上有该仓库的 git 凭据即可。

## 3. 运行时

三选一：

```bash
bun  run bus-report.ts build
deno run -A bus-report.ts build
node --experimental-strip-types bus-report.ts build
```

## 4. 产出

| 文件 | 用途 |
|------|------|
| `ba-bus-communication.html` | 报告本体，内嵌数据快照 |
| `bus-data.js` | `window.__BUS_DATA__`，页面优先加载 |
| `bus-data.json` | 纯 JSON，供程序消费 |

页面数据源有三档徽标：实时接口 / 外部 js（已是最新）/ 内嵌快照。

## 5. 时间口径

- `at` 用 **commit author date**，是排序与跨度的唯一依据；
- 消息体里手写的 `at:` 保留为 `declaredAt`，偏差 ≥1 分钟时页面标 `*`；
- 显示统一 UTC+8。

## 6. 与本 skill 的关系

- 只读：不写 workspace、不 push、不改 bus；
- `aw.py stats` 只输出数字，末尾提示用 bus-report 看消息；
- 名字映射用 `agents.alias.json`，不影响 `BA/plan/agents.json` 的权威性。
