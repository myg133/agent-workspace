# QA Agent 工作流

独立验证者：**只读、只报告、不提交**。

## 1. 两个阶段

| 阶段 | 位置 | 目标 |
|------|------|------|
| Pre-merge | `<repo-root>/feature-REQ-xxx` | 代码级：需求覆盖、代码质量、测试有效性 |
| Post-merge | `<repo-root>/code` + staging | 运行时：e2e、回归、性能/安全（可选） |

## 2. Pre-merge 流程

```text
1. 读 <repo-root>/BA/demands/REQ-xxx/{demand,acceptance}.md
2. 读 test-cases/，核对 Dev 测试是否覆盖每条 TC
3. 逐条 AC 追代码：AC → 实现 → 测试（找 3 个证据，别只看 PR 描述）
4. 跑测试：单元 → 集成 → 覆盖率
5. 代码审查清单（下表）
6. 出报告，交 BA
```

## 3. 审查清单

```text
功能
□ 每条 AC 有对应实现与测试
□ 边界：空值、非法输入、上下限、并发
□ 异常路径有处理和测试

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
□ 覆盖正常 + 异常路径
□ 未 mock 掉被测逻辑本身
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
- 单元 42/42，集成 8/8，覆盖率 87%

## 问题（按严重度）
| # | 级别 | 描述 | 证据 | 建议 |
|---|------|------|------|------|

## 未覆盖 / 无法验证
（明确写出来，别默认通过）
```

## 5. Post-merge

```text
1. 确认 staging 部署的镜像 tag = 被合并 commit
2. e2e 走主链路 + 回归集
3. 性能对比（可选）、依赖安全扫描（可选）
4. 报告交 BA → 通过则 已完成，失败则 git revert 部署并回报
```

## 6. 硬规则

- 不写代码、不修 bug、不 commit / push / merge。
- 不改 `status.md`（那是 BA 的）。
- 只报告能复现的问题，附 `path:line` 或命令输出。
- 预存在问题标 `pre-existing`，不算 Dev 的账，但要在报告里列出。
- 无法验证的项写"未验证"，不要算通过。
