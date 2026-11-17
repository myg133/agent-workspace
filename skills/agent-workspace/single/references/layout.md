# 目录与路径

## 1. 本地根

```text
D:/proj/                  # 示例占位符
├── app/                  # 代码仓库
├── docs/                 # 文档仓库
├── worktrees/            # feature worktree
└── .aw/                  # 本地状态
```

`app/` 和 `docs/` 是两个独立 git 仓库；`worktrees/` 和 `.aw/` 不是仓库。

## 2. 代码仓库

保持原样：

```text
app/
├── .git/
├── src/
└── ...
```

不创建：

- `code/`
- `BA/`
- `Deploy/`
- `feature-REQ-xxx/`（放在 `worktrees/`）

## 3. Worktree

```text
worktrees/
└── REQ-001/              # 分支 feature/REQ-001
    ├── .git              # git worktree 指针
    ├── src/
    └── feature-meta/
```

约束：

- 不嵌套在 `app/` 内；
- 一个 REQ 一个目录；
- 分支名 `feature/REQ-xxx`；
- 基于 `base_branch`。

## 4. Docs

```text
docs/
└── demands/
    └── REQ-001/
        ├── demand.md
        ├── acceptance.md
        ├── status.md
        └── test-cases/
```

Dev/QA 只读；BA 写。
