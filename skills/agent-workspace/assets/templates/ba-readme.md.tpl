# BA — 需求管理（`demand` 分支）

本目录是 BA Agent 的 worktree，所有内容随 `demand` 分支持久化。

## 目录

| 路径 | 内容 |
|------|------|
| `demands/REQ-xxx-slug/` | 需求文档、验收标准、状态、测试用例 |
| `backlog/inbox/` | 未梳理的原始想法 |
| `backlog/refined/` | 已梳理待排期 |
| `sprint/` | 迭代计划与回顾 |
| `decisions/` | 架构决策记录（ADR） |
| `dispatch/` | 调度表：`rules.md` `agent-registry.md` `req-registry.md` `cleanup-log.md` |
| `.ba/` | 本地 session 信息（不跟踪） |
| `.local/` | 未定稿中间文件（不跟踪） |

## 提交纪律

```
git pull --rebase origin demand
# 改文件
git commit -m "[BA] {描述} [session: {session-id}]"
git push origin demand
```

## 启动检查

```bash
git pull --rebase origin demand
python <skill-path>/scripts/aw.py audit
```
