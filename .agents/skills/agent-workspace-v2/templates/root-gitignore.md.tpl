# .gitignore 生成说明（**这是说明文档，不是 .gitignore 本身**）

> workspace 分支**不跟踪** `.gitignore`。本文件告诉各 agent 怎么为自己的 worktree 生成 `.gitignore`。
> 各 worktree 的 `.gitignore` 由对应 agent 维护，**不进 git**。

## 为什么 workspace 不跟踪 .gitignore

- workspace 分支的硬约束：`git ls-files` 永远只输出 `README.md`
- 各 worktree 业务不同（develop 是代码、demand 是文档、deploy 是 helm chart），`.gitignore` 需求不同
- 让各 agent 各管各的 `.gitignore` 更符合「谁产生谁维护」原则

## 通用 ignore 模式

下面列出各 agent 应该考虑加进自己 `.gitignore` 的内容。

### 所有 worktree 通用

```gitignore
# ===== 操作系统临时文件 =====
.DS_Store
Thumbs.db
desktop.ini
ehthumbs.db
*.swp
*.swo
*~

# ===== IDE / 编辑器 =====
.vscode/
.idea/
*.iml
*.sublime-project
*.sublime-workspace
.project
.classpath
.settings/

# ===== 临时文件 =====
*.tmp
*.bak
*.orig
*.rej
.cache/
.tmp/
tmp/

# ===== Agent 元数据 =====
.feature/agent-log/
```

### code/（develop 分支）— 代码 worktree

在通用基础上追加：

```gitignore
# ===== Node / 前端 =====
node_modules/
.pnpm-store/
.yarn/
.next/
.nuxt/
.svelte-kit/
dist/
build/
coverage/
*.log

# ===== Python =====
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.mypy_cache/
venv/
.venv/

# ===== Rust =====
target/

# ===== Go =====
vendor/

# ===== Java / JVM =====
*.class
.gradle/
build/
```

### BA/（demand 分支）— 文档 worktree

通常不需要额外 ignore，文档目录本身就是要跟踪的。可选：

```gitignore
# BA Agent 私有工作目录
.ba/
```

### Deploy/（deploy 分支）— 部署配置

```gitignore
# 部署时生成的临时文件
*.rendered
release-*.tgz

# 敏感信息（不进 git）
.env.local
```

### feature-xxx/、hotfix-xxx/

继承所属 worktree 类型（一般是 code 类）的 ignore 模式。

## 验证清单

各 worktree 的 `.gitignore` 应该满足：

- [ ] worktree 自己的 `git status` 不应出现被忽略的临时文件
- [ ] 不应忽略**业务文件**（src/、tests/、package.json 等）
- [ ] 不应与其他 worktree 的 `.gitignore` 冲突（每个 worktree 独立维护）

## 迁移期提示

如果是从老项目迁移过来，原 `.gitignore` 通常放在 `code/` 下：
- `code/.gitignore` 跟踪在 develop 分支
- workspace 分支的 `git ls-files` 仍然只有 `README.md`
- 这是预期行为，**不是违规**
