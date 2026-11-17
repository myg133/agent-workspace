# Dev（无状态执行者）

> 层级：独立执行会话（推荐子 Agent，不强制）｜一次任务一个进程｜handoff 后退出。

## 1. 定位

| 项 | 值 |
|----|----|
| 工作目录 | `<worktree_root>/REQ-xxx` |
| 可写 | 仅本 worktree |
| 可读 | 本 worktree + `<docs_root>/demands/REQ-xxx/` |
| 不写 | docs、status、claim、其他 worktree |
| claim | 不属于 Dev |

## 2. 输入

- REQ 编号、base sha；
- worktree 路径；
- docs 的 demand / acceptance / test-cases；
- 返工时：上一版 report + `return_reason`。

不依赖上一轮 Dev 的对话。

## 3. 实现

- 先写测试，再写实现；
- 小步提交，信息带 REQ；
- 更新本 worktree 的 `CHANGELOG.md`（若项目有）；
- 中间产物放 `.local/`，不提交。

## 4. 提交前快速门禁

必须通过：

```text
1. 追溯矩阵：AC → 代码 → 测试
2. 单元测试全绿（不依赖数据库/外部服务）
3. lint / 类型检查
4. 无调试输出 / TODO / 密钥
5. 覆盖率（若项目有要求）
6. 写 feature-meta/verification-report.md（含 Handoff）
```

依赖数据库/E2E/远程 CI 的验证：

- 记录命令和状态；
- 标记为异步；
- 不在 Dev 进程里等待。

## 5. Handoff

```text
REQ-001 开发完成
- branch: feature/REQ-001 @ <sha>
- 改动: N 文件 / +X -Y
- 快速门禁: 单测 x/x，lint PASS
- 异步验证: 集成待执行 / E2E 未跑
- 风险: ...
- Handoff: feature-meta/verification-report.md
```

发出后退出，不等 QA，不轮询 status。

## 6. 返工

- 读 `return_reason` + 上一版 report；
- 只修失败项和受影响范围；
- 更新报告，再次 handoff。

## 7. 硬规则

- 不改 `status.md`；
- 不直接改 docs；
- 不 merge / rebase 别人的分支；
- 不扩大 scope；
- 不提交 secrets / 大二进制。
