# 升级已运行的项目（1.x → 1.x）

## 核心结论

> **目录结构不需要迁移。** 1.x 内 `workspace` 根容器 + 平铺 worktree 是稳定契约。
> 升级只做两件事：**补缺失文件**、**改引用路径**。清理只针对"项目自己长歪的目录"。

## 1. 哪些要动，哪些不要动

| 对象 | 1.0 → 1.4 有变化吗 | 升级动作 |
|------|-------------------|---------|
| 仓库根（README + .gitignore） | 无 | 不动 |
| `code/` `BA/` `Deploy/` | 无 | 不动 |
| `feature-xxx/` | 无 | 不动（已合并的按回收流程处理） |
| `BA/dispatch/*.md` | 表结构变了（认领改为 `.aw/`） | 只补缺失文件；旧表冻结为快照 |
| `.feature/` | 新增规范 | 可选：补 `manifest.json` |
| `.aw/` | 新增（本地状态） | 只在启用 claim 时创建 |
| `.local/` | 无 | 确认各 worktree 的 `.gitignore` 里有 `.local/` |
| `references/*.md` | **改名**（skill 内部） | 改 prompt / 文档里的引用 |
| `skills/agent-workspace`（项目内 vendor） | 会版本漂移 | 建议移除，改外部安装 |

一句话：**拓扑不动，补文件，改引用**。

## 2. 需要"清"的只有这 6 类

| # | 现象 | 判定 | 处理 |
|---|------|------|------|
| 1 | 根目录有 `workspaces/` 等中间层 | 违反平铺 | 把 worktree 移回根下一层，删空目录 |
| 2 | worktree 在 `feature-x/code/` 这类二级嵌套 | 违反平铺 | `git worktree repair` 或重建 |
| 3 | feature worktree 已合并、干净、无未推送，且闲置 > 1 小时 | 僵尸 | `git worktree remove` + `git branch -d` |
| 4 | `git worktree list` 里有路径不存在的登记 | 失效 | `git worktree prune` |
| 5 | 根分支 `git ls-files` 出现业务文件 | 污染 | `git rm -r --cached <path>` + `[Workspace] cleanup` |
| 6 | 项目里 vendor 了旧版 skill | 版本漂移 | 移除，改为外部安装 + 版本指针 |

**不要**为了"对齐新版"去重建仓库、rebase、改分支名、批量重命名 worktree。
那些动作的收益是零，风险是全部历史。

## 3. 需要"补"的（只增不改）

```bash
cp <skill>/assets/templates/ba-readme.md.tpl         BA/README.md
cp <skill>/assets/templates/dispatch-rules.md.tpl    BA/dispatch/rules.md
cp <skill>/assets/templates/agent-registry.md.tpl    BA/dispatch/agent-registry.md
cp <skill>/assets/templates/req-registry.md.tpl      BA/dispatch/req-registry.md
cp <skill>/assets/templates/cleanup-log.md.tpl       BA/dispatch/cleanup-log.md
cp <skill>/assets/templates/deploy-readme.md.tpl     Deploy/README.md
```

已存在的文件**不要覆盖**——里面可能是你的真实数据。

## 4. 需要"改"的（人工，5 分钟）

| 位置 | 改什么 |
|------|--------|
| agent prompt | 只引用 `SKILL.md` / `references/roles/<role>.md` / `aw.py`，不要引用"第 N 部分"或旧文件名 |
| 项目内文档 | `worktree-audit.md` → `references/lifecycle/audit.md`；`worktree-cleanup.md` → `references/lifecycle/cleanup.md` |
| 各 worktree 的 `.gitignore` | 有 `.local/` 目录就补一行 `.local/` |
| 根 `.gitignore` | 必须仍包含 `/*/` |

## 5. 流程

```bash
# ① 预检（只读，不改任何东西）
python <skill>/scripts/aw.py upgrade
python <skill>/scripts/aw.py verify --strict
python <skill>/scripts/aw.py audit

# ② 按输出执行「补 / 清 / 改」，每类做完再跑一次 ①

# ③ 记录
# .aw/version.json  {"skill_version": "1.4.0", "upgraded_at": "..."}
# BA/dispatch/upgrade-1.4.0.md  人读的升级日志
```

`upgrade` 的输出分三段：**需要补 / 需要清 / 需要改**，加上「不要动」的护栏。
退出码 0 表示无需动作，1 表示有待处理项（可用于 CI 或升级门禁）。

## 6. 灰度与回滚

| 阶段 | 做法 |
|------|------|
| 灰度 | 一个项目 / 一个 feature worktree 先跑通一个完整需求 |
| 全量 | 补文件 + 改引用 + **重启 agent 会话**（旧上下文里还是老路径） |
| 回滚（skill） | 版本目录指针切回旧版本，0 风险 |
| 回滚（项目） | 删掉本次新增的文件即可；升级没有改任何已有内容 |

## 7. 版本记录

| 位置 | 内容 | 是否跟踪 |
|------|------|---------|
| `.aw/version.json` | `{"skill_version": "...", "upgraded_at": "..."}` | 否（本机） |
| `BA/dispatch/upgrade-<ver>.md` | 时间、执行人、补了什么、遗留什么 | 是（团队可见） |

## 8. 升级检查覆盖不到的情况

- 自定义模板（你改过的 `.tpl`）：脚本不比对内容，只检查文件是否存在。
- 自建目录（`docs/`、`design/`）：不判断对错，只在根目录出现时按"污染"报。
- prompt 里的间接引用（比如"按上次那份规范做"）：只能人工过一遍。
