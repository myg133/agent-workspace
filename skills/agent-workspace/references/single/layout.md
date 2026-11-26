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

## 5. 写入边界与导出目录（硬规则）

所有写文件必须落在 `<local-root>` 或当前 worktree 内。

| 用途 | 默认路径 |
|------|----------|
| 临时文件 / 缓存 | `<local-root>/.aw/tmp/` |
| 导出 / 截图 / 日志 | `<local-root>/.aw/exports/<REQ>/` |
| 随需求提交的证据 | `<docs_root>/demands/<REQ>/evidence/`（BA 写） |
| 代码 | 当前 worktree |

禁止：

- `C:/`、`D:/` 盘根，`C:/tmp`、`D:/tmp`；
- `%TEMP%`、`%USERPROFILE%`、Desktop、Downloads、`~/tmp`；
- 用 `..` 逃出 `<local-root>` / 当前 worktree；
- 把本机绝对路径写进提交、消息或报告。

工具必须使用系统临时目录时：

~~~text
1. 优先把 TMP / TEMP / TMPDIR 指到 <local-root>/.aw/tmp；
2. 改不了就在项目内 cwd 运行，把输出复制回 .aw/exports/<REQ>/；
3. 外部临时文件用完删除，不要留在 C:/ 或 D:/。
~~~

写前可用工具检查：

~~~bash
python <skill>/scripts/aw.py path check <path>          # workspace
python <skill>/scripts/aw.py path check <path>   # single
~~~

返回 `ALLOWED <rel>` 才写；`DENIED` 就停。

写前自检：解析目标绝对路径 → 确认前缀是允许根 → 再写。
不通过就停，不要“先写再挪”。
