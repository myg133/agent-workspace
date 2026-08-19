# Dev Agent 自验证流程

## 触发时机

代码开发完成后，提交 PR 之前。

## 流程

### Step 1: 追溯性检查

```
1. 读取 BA/demands/REQ-xxx/demand.md
2. 读取 BA/demands/REQ-xxx/acceptance.md
3. 逐条对照：代码中是否实现了每条需求
4. 输出到 .feature/traceability.md

格式：
OK AC-01: 邮箱格式校验 → src/auth/email.ts:validateEmail()
OK AC-02: 密码错误提示 → src/auth/login.ts:showError()
MISSING AC-03: 登录成功跳转 → 未实现
```

### Step 2: 运行测试

```
1. 运行单元测试
   → 记录通过数/总数
2. 运行集成测试
   → 记录通过数/总数
3. 检查测试覆盖率（如果项目配置了覆盖率检查）
   → 记录覆盖率
```

### Step 3: 质量检查

```
1. 运行 linter → 无严重错误
2. 搜索代码中的 TODO/FIXME/console.log/debugger
   grep -rn "TODO\|FIXME\|console.log\|debugger" src/ --include="*.ts" --include="*.js"
3. 检查 docs/ 是否同步更新
4. 确认 CHANGELOG.md 已更新
```

### Step 4: 生成验证报告

```
汇总到 .feature/verification-report.md（使用核心 skill 的模板）

内容：
- 追溯性检查结果
- 测试结果
- 质量检查结果
- 结论：可提交 PR / 需修改
```

### Step 5: 提交验证请求

```
1. 将 .feature/ 目录的变更提交到 feature 分支
2. 更新 BA/demands/REQ-xxx/status.md → "待验证"
3. 通知 BA Agent 和 QA Agent
```

## 验证报告模板

详见核心 skill 的 `templates/verification-report.md.tpl`。