# Post-merge 验证流程

## 触发时机

PR 已合并到 `develop` 分支，且 `develop` 已自动部署到 `staging` 环境。

## 前置条件

- [ ] Pre-merge 验证已通过
- [ ] PR 已合并到 develop 分支
- [ ] CI 已构建镜像并推送到镜像仓库
- [ ] Staging 环境已部署最新的 develop 版本

## 流程

### Step 1: 确认部署状态

```
1. 确认 staging 环境已部署最新版本
2. 确认镜像 tag 对应 develop 的最新 commit SHA
3. 确认健康检查通过
```

### Step 2: 端到端测试

```
1. 按照需求文档中的业务流程，逐条执行 e2e 测试
2. 测试用例来源：
   - BA/demands/REQ-xxx/test-cases/
   - 已有的 e2e 测试套件
3. 记录测试结果
```

### Step 3: 回归测试

```
1. 运行完整的回归测试套件
2. 确认本次变更没有破坏现有功能
3. 重点关注变更涉及的模块和相关联的模块
```

### Step 4: 性能测试（可选）

```
1. 如果需求涉及性能要求，运行性能测试
2. 对比基准数据（如果有）
3. 检查性能退化
```

### Step 5: 安全扫描（可选）

```
1. 运行依赖安全扫描
2. 检查新增 API 的安全性
3. 检查配置安全性
```

### Step 6: 生成验证报告

```
1. 汇总所有检查结果
2. 写入 BA/demands/REQ-xxx/status.md
   → 通过：更新为"已完成"（生产部署就绪）
   → 不通过：更新为"staging 验证不通过"，通知 Deploy Agent 回滚
3. 如果通过，通知 Deploy Agent 可以部署到 production
```

## 验证通过标准

- [ ] 所有 e2e 测试通过
- [ ] 回归测试通过
- [ ] 性能指标符合要求（如果有）
- [ ] 安全扫描无高危漏洞
- [ ] 功能运行正常

## 验证不通过的处理

```
1. 更新需求状态为"staging 验证不通过"
2. 通知 BA Agent 和 Dev Agent
3. Deploy Agent 将 staging 回滚到上一个稳定版本
4. Dev Agent 重新开始开发流程
```