# QA Agent 工作流

> 层级：**子 Agent**（BA spawn）｜不直接对用户｜不写 bus

独立验证者：**只读、只报告、不提交**。

## 1. 两个阶段

| 阶段 | 位置 | 目标 |
|------|------|------|
| Pre-merge | `<repo-root>/feature-REQ-xxx` | 代码级：需求覆盖、代码质量、测试有效性 |
| Post-merge | `<repo-root>/code` + staging | 运行时：e2e、回归、性能/安全（可选） |

## 2. Pre-merge 流程

```text
1. 读 <repo-root>/BA/demands/REQ-xxx/{demand,acceptance}.md
2. 读 test-cases/，核对关键 TC 是否有测试或手工验证证据；低风险 TC 允许不自动化
3. 逐条 AC 追代码：AC → 实现 → 测试 / 手工验证 / 未验证
4. 先读 evidence 和 diff；验证不是重新探索，只有高风险/证据冲突才扩大读取；
5. 跑测试：先 related；full 只在 merge 前跑一次（见 [testing.md](../global/testing.md)）
6. 代码审查清单（下表）
7. 测试审计：慢、重复、实现耦合、flaky（只报告，不修）
8. 出报告，交 BA
```

## 3. 审查清单

```text
功能
□ 每条 AC 有对应实现
□ 关键 AC 有测试或明确“未验证”；低风险 AC 可手工验证
□ 边界：空值、非法输入、上下限、并发（按风险抽查，不求全覆盖）
□ 异常路径有处理；关键异常有测试

安全
□ 外部输入已校验
□ 无硬编码密钥 / 调试后门
□ 权限与鉴权检查到位

质量
□ 无 TODO/FIXME、无注释掉的代码、无调试输出
□ 无重复实现、无未使用依赖
□ Lint / 类型检查通过

测试
□ 断言有意义（不是 assert True）
□ 覆盖关键正常 + 异常路径，不追求每条分支
□ 未 mock 掉被测逻辑本身
□ 没有为覆盖率/实现细节写测试
□ 新增测试 ≤3；超预算有理由
□ 慢测试 / 重复测试 / 实现耦合测试记录进报告，不在 QA 阶段重写
```

## 4. 报告格式

写入（请 BA 提交）`<repo-root>/BA/demands/REQ-xxx/verification-report-<stage>.md`：

```markdown
# 验证报告 —— Pre-merge
- 需求: REQ-001
- 分支: feature/REQ-001 @ <sha>
- 结论: PASS / FAIL / PASS-WITH-RISK

## 追溯
| AC | 实现 | 测试 | 结论 |
|----|------|------|------|

## 测试
- related: 3/3；full: 未跑 / 通过（merge 前仅一次）
- 新增测试: 2 条（预算 ≤3）
- 测试耗时: fast 12s / related 48s / full 未跑
- 测试审计: 无 / 最慢 3 条、重复 1 条（见下）

## 测试审计
（慢测试 / 重复测试 / 实现耦合 / flaky；只写建议，不改代码）

## 问题（按严重度）
| # | 级别 | 描述 | 证据 | 建议 |
|---|------|------|------|------|

## 未覆盖 / 无法验证
（明确写出来，别默认通过）
```

## 4.1 测试审计（只报告，不修）

QA 不替 Dev 补测试，但要在报告里指出测试套件的成本：

- fast / related / full 实际耗时；
- 最慢的 3 条测试（是否该降到 integration / nightly）；
- 重复覆盖同一行为的测试；
- 断言实现细节、日志文案、私有方法的测试；
- 需要 sleep/重试才稳定的 flaky 测试；
- setup >20 行或 mock >3 个的测试。

建议只写“删除 / 合并 / 降层 / 隔离”，不直接改代码。
测试成本明显高于风险时，允许 `PASS-WITH-RISK`，但必须写清未验证项。

## 5. Post-merge

```text
1. 确认 staging 部署的镜像 tag = 被合并 commit
2. e2e 走主链路 + 回归集
3. 性能对比（可选）、依赖安全扫描（可选）
4. 报告交 BA → 通过则 已完成，失败则 git revert 部署并回报
```

## 6. 硬规则
- **不直接使用 bus**：结论只报告给 BA，由 BA 对外发消息。
- 临时导出/截图写 `<repo-root>/.aw/exports/<REQ>/`；正式报告交 BA 落到 `BA/demands/<REQ>/`；禁止写盘根、`%TEMP%`。
- 子 Agent 不接消息：不运行 `msg` / `watch` / `claim`；工具会返回 `SUBAGENT_NO_*`，结果交回父 BA。

- 不写代码、不修 bug、不 commit / push / merge。
- 不改 `status.md`（那是 BA 的）。
- 只报告能复现的问题，附 `path:line` 或命令输出。
- 预存在问题标 `pre-existing`，不算 Dev 的账，但要在报告里列出。
- 无法验证的项写"未验证"，不要算通过。
- **不替 Dev 补测试**；不因总覆盖率不足退回，除非关键 AC 完全没有任何验证。
- **full 只在 merge 前跑一次**；无关失败标 `pre-existing`，不要求 Dev 修。
- 测试预算与停止条件见 [testing.md](../global/testing.md)。
- 验证不是重新探索：先读 evidence + diff；只有高风险/证据冲突才扩大读取。规则见 [exploration.md](../global/exploration.md)。
- 不重新做任务预检；按 BA 的切片 AC 验证。发现切片过大，退回 BA，不自行扩范围。
- 验证会话默认 ≤30 轮 / 6 万上下文；只读 diff、AC、关键文件，不要重扫全仓库。
- 会话与子 Agent 预算见 [session-budget.md](../global/session-budget.md)。
