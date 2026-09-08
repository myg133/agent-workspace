# Pre-merge 验证流程

## 触发时机

Dev Agent 完成开发，提交验证请求后（`BA/demands/REQ-xxx/status.md` → "待验证"）。

## 前置条件

- [ ] feature 分支已推送到远程
- [ ] Dev Agent 已提交自验证报告（`.feature/verification-report.md`）
- [ ] 需求文档已确认（`BA/demands/REQ-xxx/`）

## 流程

### Step 1: 验证工作区

```bash
# 进入 feature worktree
cd feature-REQ-xxx

# 确认分支
git branch

# 读取 manifest
cat .feature/manifest.json
```

### Step 2: 需求追溯性审查

```
1. 读取 BA/demands/REQ-xxx/demand.md
2. 读取 BA/demands/REQ-xxx/acceptance.md
3. 逐条检查需求实现
   - 功能的输入输出是否符合预期
   - 边界情况是否处理
   - 异常场景是否考虑
4. 与 Dev 的 traceability.md 对比，确认无遗漏
5. 输出到 .feature/qa-traceability.md
```

### Step 3: 测试用例审查

```
1. 读取 BA/demands/REQ-xxx/test-cases/（如果有）
2. 检查 Dev 的测试是否覆盖了这些用例
3. 检查是否有遗漏的测试场景
4. 输出测试覆盖矩阵
```

### Step 4: 代码审查

```
检查清单（详见 checklists/）：
1. 架构合理性
   - 代码组织是否符合项目结构
   - 是否引入了不必要的依赖
2. 边界情况处理
   - 空值、非法输入、异常数据
   - 并发、超时、重试
3. 安全性
   - 输入校验
   - 敏感信息处理
4. 代码质量
   - 可读性
   - 可维护性
   - 是否留下了调试代码
```

### Step 5: 运行测试验证

```bash
# 运行 Dev 的测试
npm test          # Node.js
pytest            # Python
cargo test        # Rust
go test ./...     # Go

# 检查测试结果
# 所有测试必须通过
```

### Step 6: 生成验证结论

```
1. 汇总所有检查结果
2. 写入 BA/demands/REQ-xxx/status.md
   → 通过：更新为"已验证"
   → 不通过：更新为"已退回"，附上退回原因
3. 通知 Dev Agent 验证结果
```

### Step 7: 通知 BA Agent

```
1. 更新 BA/dispatch/verification-queue.md
2. 通知 BA Agent 验证完成
3. BA Agent 确认后，Dev Agent 可创建 PR
```

## 验证通过标准

- [ ] 所有需求点已实现
- [ ] 所有验收标准已覆盖
- [ ] 单元测试通过（100%）
- [ ] 集成测试通过（100%）
- [ ] 代码审查无严重问题
- [ ] 无安全漏洞
- [ ] 文档已同步更新