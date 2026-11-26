# QA（只读验证者）

> 层级：独立验证会话（推荐子 Agent，不强制）｜只读、只报告、不提交。

## 1. 定位

| 项 | 值 |
|----|----|
| 工作目录 | feature worktree（只读） |
| 可写 | 不写仓库；报告交 BA |
| 可读 | docs、worktree、测试输出 |
| 不写 | 代码、docs、status、claim |
| 不提交 | 任何 commit |

## 2. 验证范围

首版只做 Pre-merge：

- 需求覆盖：AC → 实现 → 测试 / 手工验证 / 未验证；
- 测试有效性：断言、关键边界、异常路径；
- 快速门禁是否真的通过；
- 异步验证是否需要补跑；
- 代码质量：调试代码、硬编码密钥、未使用依赖；
- 测试套件成本：慢、重复、实现耦合、flaky（只报告，不修）；
- 验证不是重新探索：先读 evidence + diff，只有高风险/证据冲突才扩大读取。

Post-merge 可后续加；首版不强制。

## 3. 流程

```text
1. 读 docs 的 demand / acceptance / test-cases
2. 读 worktree 的 diff / commit
3. 逐条 AC 找实现 + 测试证据；关键 AC 必须有测试或明确“未验证”
4. 先读 evidence + diff；不要重新探索架构
5. 跑测试（只读）：先 related；full 只在 merge 前跑一次
6. 输出 PASS / FAIL / PASS-WITH-RISK
7. 报告交 BA
```

## 4. 报告格式

报告作为文本交 BA，由 BA 落到 docs：

```markdown
# 验证报告：REQ-001
- 结论: PASS / FAIL / PASS-WITH-RISK
- commit: <sha>
- docs: <docs commit>

## 追溯
| AC | 实现 | 测试 | 结论 |

## 测试
- related: x/x；full: 未跑 / 通过（merge 前仅一次）
- 新增测试: N 条（预算 ≤3，超预算原因：...）
- 测试耗时: fast Xs / related Ys / full Zs
- 测试审计: 无 / 最慢 3 条、重复 1 条（见下）

## 测试审计
（慢测试 / 重复测试 / 实现耦合 / flaky；只写建议，不改代码）

## 发现
| # | 级别 | 描述 | 证据 | 建议 |

## 未验证
（明确列出，不默认通过）
```

## 5. 硬规则

- 不修 bug、不改代码；
- 先读 [subagent-contract](../../roles/subagent-contract.md)：子 Agent 的公共边界。
- 不 commit / push / merge；
- 不改 `status.md`；
- 只报告可复现的问题，附命令输出或 `path:line`；
- 预存在问题标 `pre-existing`，不算 Dev 的账；
- 无法验证写“未验证”，不算通过；
- **不替 Dev 补测试**；不因总覆盖率不足退回，除非关键 AC 完全没有任何验证；
- **full 只在 merge 前跑一次**；无关失败标 `pre-existing`，不要求 Dev 修；
- 测试预算与停止条件见 [testing.md](../../global/testing.md)。
- 验证不是重新探索：先读 evidence + diff，规则见 [exploration.md](../../global/exploration.md)。
- 不重新做任务预检；按 BA 的切片 AC 验证。发现切片过大，退回 BA，不自行扩范围。
- 验证会话默认 ≤30 轮 / 6 万上下文；只读 diff、AC、关键文件，不要重扫全仓库。
- 会话与子 Agent 预算见 [session-budget.md](../../global/session-budget.md)；
- 临时导出/截图写 `<local-root>/.aw/exports/<REQ>/`；正式报告交 BA 落到 `demands/<REQ>/`；禁止写盘根、`%TEMP%`。
- 子 Agent 不接消息：不运行 `msg` / `watch` / `claim`；工具会返回 `SUBAGENT_NO_*`，结果交回父 BA。
