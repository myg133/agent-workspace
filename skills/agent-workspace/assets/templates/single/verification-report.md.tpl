# 验证报告：REQ-xxx

- **阶段**: 快速门禁 / Pre-merge / Post-merge
- **验证者**: {agent_id}
- **分支 / commit**: feature/REQ-xxx @ {sha}
- **docs**: {docs_repo} / {demand_path} @ {demand_commit}
- **结论**: PASS / FAIL / PASS-WITH-RISK

## 追溯

| AC | 实现位置 | 测试位置 / 手工验证 | 结论 |
|----|---------|---------|------|
| AC-001 |  |  |  |

## 测试

- 执行范围: {fast / related / full；full 仅 merge 前跑一次}
- 快速门禁: {通过 / 失败}
- 新增测试: {N} 条（预算 ≤3，超预算原因：{...}）
- 异步集成: {通过 / 失败 / 未执行}
- E2E: {通过 / 失败 / 未执行}
- 测试耗时: {fast Xs / related Ys / full Zs 或未跑}
- 会话 / 子 Agent: {N} / {N}（预算：≤100 轮、≤3 个子 Agent）
- 变更行覆盖（可选）: {N}%（不要用全仓库总覆盖率代替）
- 未跑 / 未验证: {命令、原因、负责人}

## Handoff

- **commit**:
- **base**:
- **测试预算**: {新增 N / 上限 3；是否跑 full}
- **异步验证请求**:
- **已知风险**:
- **返工入口**:

## 问题

| # | 级别 | 描述 | 证据 | 建议 |
|---|------|------|------|------|
