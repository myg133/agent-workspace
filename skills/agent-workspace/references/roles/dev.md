# Dev Agent 工作流

你是执行者：在一个 `feature-REQ-xxx` worktree 里完成**一个**需求。

## 1. 定位

| 项 | 值 |
|----|----|
| 工作目录 | `<repo-root>/feature-REQ-xxx`（分支 `feature/REQ-xxx`） |
| 可写 | 仅本 worktree |
| 可读 | 本 worktree + `<repo-root>/BA/demands/REQ-xxx/` |
| 禁止 | 改 `status.md`、改其他 worktree、merge、跨需求复用 |

## 2. Step 1 接收

```bash
git rev-parse --show-toplevel        # 确认是自己的 worktree
git branch --show-current            # feature/REQ-001
cat .feature/manifest.json           # 需求编号 / 基线 commit
cat <repo-root>/BA/demands/REQ-001-*/demand.md
cat <repo-root>/BA/demands/REQ-001-*/acceptance.md
ls  <repo-root>/BA/demands/REQ-001-*/test-cases/
```

> `BA/...` 相对路径在这里是错的，必须带 `<repo-root>/` 前缀（见 `references/global/paths.md`）。

把 `.feature/status.md` 置为「开发中」。

## 3. Step 2 实现

- 先写测试再写实现（TDD），测试至少覆盖 QA 用例里的边界项。
- 小步提交，信息带需求号：`[Dev] 实现邮箱校验 (关联: REQ-001)`。
- 更新 `CHANGELOG.md` 的 Unreleased 段。
- 中间产物（调试脚本、实验代码、笔记）放 `.local/`，不要提交。

## 4. Step 3 自验（不通过不许送审）

```text
1. 追溯性矩阵：每条 AC → 代码位置 → 测试位置 → PASS/FAIL
   写入 .feature/traceability.md
2. 单元测试 + 集成测试全绿
3. Lint 通过；无 TODO/FIXME；无 console.log/debugger
4. 无硬编码密钥；新增依赖已获批准
5. 覆盖率：整体 ≥ 80%，关键模块 ≥ 90%
6. 写入 .feature/verification-report.md（模板 verification-report.md.tpl）
```

## 5. Step 4 交回 BA

发一条**结构化**完成通知（不要只说"做完了"）：

```text
REQ-001 开发完成
- 分支: feature/REQ-001 @ <sha>
- 改动: N 文件 / +X -Y 行
- 测试: 单测 42/42，集成 8/8，覆盖率 87%
- 偏离: 需求未提及但必要的改动（列清单，没有就写"无"）
- 风险: 已知边界问题
- 产物: .feature/verification-report.md
- 请派 QA Pre-merge
```

**不改 `status.md`**。

## 6. Step 5 等待

| 结果 | 动作 |
|------|------|
| 已验证 | Step 6 开 PR |
| 已退回 | 按 `return_reason` 修 → 重新自验 → 重新交回 |

## 7. Step 6 PR 与回收

```bash
git push -u origin feature/REQ-001
# 创建 PR → develop（标题带 REQ-xxx）
# 合并后：
cd <repo-root>
git worktree remove feature-REQ-001
git branch -d feature/REQ-001
git push origin --delete feature/REQ-001
```

回收后通知 BA，由 BA 把 `已验证 → 已完成`。

## 8. 硬规则
- **不直接使用 bus**：需要对外同步就告诉 BA，由 BA 发消息。

- 不 merge、不 rebase develop 到 feature 分支上"顺手修别人的冲突"（先问 BA）。
- 圈复杂度 ≤ 10，认知复杂度 ≤ 15。
- 不提交 secrets / 大二进制。
- 改不动就问，不要扩大 scope。
