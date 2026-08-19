# 部署流程

## 触发时机

- QA Agent Post-merge 验证通过，确认可以部署到 production
- 用户手动触发部署
- CD 流水线监听 deploy 分支变更

## 流程

### Step 1: 确认部署目标

```
1. 确认要部署的环境（staging / production）
2. 确认要部署的应用
3. 确认镜像 tag
   - 默认：develop 的最新 commit SHA
   - 发布：Git Tag
   - 特殊：用户指定
```

### Step 2: 更新镜像 tag

```bash
# 编辑对应环境的 .env 文件
# 更新 IMAGE_TAG 为要部署的版本
echo "IMAGE_TAG=a1b2c3d4" > environments/.env.staging
```

### Step 3: 提交变更

```bash
git add apps/api-gateway/helm/environments/.env.staging
git commit -m "[staging] 部署 api-gateway v1.0.0 (image: myapp:a1b2c3d)"
git push origin deploy
```

### Step 4: 触发 CD

```
1. 推送 deploy 分支后，CD 流水线自动触发
2. 监控 CD 流水线状态
3. 确认部署成功
```

### Step 5: 健康检查

```bash
# 执行健康检查脚本
./scripts/healthcheck.sh staging api-gateway

# 检查：
# - Pod 状态
# - 服务响应
# - 日志无异常
```

### Step 6: 记录发布

```
1. 更新 releases/ 下的发布记录
2. 如果发布到 production，创建 release notes
3. 通知相关 Agent 部署完成
```

## 部署到 production 的额外步骤

```
1. 确认 staging 环境已验证通过
2. 确认 BA Agent 已批准 production 部署
3. 执行 staging 同样的部署流程
4. 部署后执行更严格的健康检查
5. 监控一段时间确认无异常
```

## 部署失败处理

```
1. 如果 CD 失败 → 排查原因，修复后重新部署
2. 如果部署成功但服务异常 → 执行回滚流程
3. 记录失败原因到 releases/ 下的发布记录
```