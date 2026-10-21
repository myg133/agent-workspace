# Changelog

本项目遵循 [Semantic Versioning](https://semver.org/)。

## [1.2.0] - 2026-10-21

一次性交付原计划的 1.0.1（热修）+ 1.1.0（补全）+ 1.2.0（重构）。
**目录与分支模型未变**，已有 workspace 项目无需迁移。

### 修复（原 1.0.1）

- **破坏性命令**：把所有 `git checkout --orphan` 后的 `git rm -rf .` 改为 `git reset`。
  前者会连工作区文件一起删除（实测：目录只剩 `.git`）。
- **迁移流程跑不通**：原 Step 3→5 先建 `code/` 再 `git worktree add code develop`，必然报
  `fatal: 'code' already exists`；且会产生 `code/code/src` 双重嵌套。改为"先腾空根目录，再让 worktree add 把文件变进去"。
- 迁移文档中"根目录无 .gitignore"的错误表述。
- 重复粘贴的段落。
- 模板路径 `templates/` → `assets/templates/`。

### 变更（原 1.1.0 的规范清理）

- **单一写入者**：`status.md` 仅 BA 可写；QA 不 commit；Dev 只写 `.feature/`。删除 SKILL 中 QA 更新状态的步骤。
- **路径基准**：新增 `references/global/paths.md`，明确 `<repo-root>/BA/...` 才是跨 worktree 的正确写法。
- **新增 Explore 与 Release**：补上缺失的角色入口与 `develop → release → main` 发布/回滚流程。
- **多 BA 调优**：session ID 去掉 pid；stale 阈值 30 → 120 分钟；认领重试上限 3 次；活跃 BA > 3 启用号段。

### 新增

- `scripts/aw.py`：`init` / `migrate` / `verify` / `audit` / `next-req`。
- 校验脚本：11 项硬约束检查，可挂 CI / pre-commit，违规退出码 1。
- bootstrap 模板：`BA/dispatch/` 四个登记表、`Deploy/README`、各分支 `.gitignore`。
- `.feature/` 规范与模板：`manifest.json` / `status.md` / `traceability.md`。
- 根 README、LICENSE、CHANGELOG。

### 重构（原 1.2.0）

- `SKILL.md` 从 944 行拆为 138 行索引 + `references/{global,roles,init,lifecycle}`（15 篇）。
- Agent 定义从"复制规范"改为"指向规范"（薄壳），消除双份维护。
- 角色注入从"人肉截取 SKILL 段落"改为"给一个文件路径"。

### 迁移指南

- 1.0.x 项目：目录结构不变，但建议把 `status.md` 的写权限收归 BA，并在根目录跑一次 `aw.py verify`。
- 若曾在迁移中执行过 `git rm -rf .`，用 `git checkout <branch> -- .` 找回工作区文件。

## [1.0.0] - 2026-09

- 首个版本：workspace 根容器 + 平铺 worktree + 五角色工作流。
