# 回滚流程

## 触发时机

- 部署后服务异常（健康检查失败、错误率上升）
- QA Agent 发现严重问题
- 用户手动触发回滚

## 原则

回滚本质上是一个**新的部署操作**，不是"撤销"。

## 流程

### Step 1: 确认回滚目标

```
1. 确认要回滚的环境（staging / production）
2. 确认要回滚的应用
3. 确认要回滚到的版本（上一个稳定部署的镜像 tag）
4. 查看 deploy 分支的 commit 历史，找到上一次稳定部署的版本
```

### Step 2: 执行回滚

```bash
# 方法一：git revert（推荐）
git revert HEAD  # 回滚到上一个部署状态
# 调整 .env 中的镜像 tag 为旧版本
# 编辑 values.yaml 或 .env 文件
git add .
git commit -m "[staging] 回滚 api-gateway v1.0.0→v0.9.0 (revert a1b2c3)"
git push origin deploy

# 方法二：手动指定旧版本镜像 tag
# 编辑 .env 文件，设置 IMAGE_TAG 为旧版本
git add .
git commit -m "[staging] 回滚 api-gateway 到 v0.9.0 (image: myapp:9f8e7d)"
git push origin deploy
```

### Step 3: 确认回滚成功

```bash
# 执行健康检查
./scripts/healthcheck.sh staging api-gateway

# 确认：
# - 服务已恢复
# - 错误率已下降
# - 功能正常
```

### Step 4: 记录回滚

```
1. 更新 releases/ 下的发布记录
2. 记录回滚原因
3. 通知 BA Agent 和 Dev Agent
```

## 回滚记录格式

```
### 回滚记录
- **时间**: {日期}
- **环境**: {staging/production}
- **应用**: {应用名}
- **回滚前版本**: {镜像 tag}
- **回滚后版本**: {镜像 tag}
- **原因**: {原因描述}
- **执行者**: {agent-name}
```

## 回滚后的处理

```
1. Dev Agent 分析回滚原因并修复
2. 修复后重新走完整开发 → 验证 → 部署流程
3. 回滚本身不产生新的需求，但修复需要创建新的需求或关联到现有需求
```

## 避免的操作

- 不要直接删除 deploy 分支的 commit（会破坏历史）
- 不要使用 git reset --hard 回滚远程分支
- 不要在一次回滚中回滚多个独立的部署