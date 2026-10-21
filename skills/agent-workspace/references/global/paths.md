# 路径基准（最容易出错的一节）

## 1. 三条规则

1. **跨 worktree 的引用一律以 `<repo-root>/` 开头。**
   `<repo-root>` = `git rev-parse --show-toplevel` 在**主 worktree** 中的值。
2. **相对路径只用于自己的 worktree 内部。**
3. **不要假设"我所在的 worktree 里有 BA/ 目录"** —— 没有。`BA/` 是另一个分支的 worktree。

## 2. 各角色实际能看到的路径

| 你在 | 你的工作目录 | 能读 | 能写 |
|------|--------------|------|------|
| BA Agent | `<repo-root>/BA` | `<repo-root>/BA/**`、只读 `code/` | 仅 `<repo-root>/BA/**` |
| Dev Agent | `<repo-root>/feature-REQ-xxx` | 自己的 worktree + `<repo-root>/BA/demands/REQ-xxx/` | 仅自己的 worktree |
| QA Agent | 同 Dev（Pre-merge）；`code/`（Post-merge） | 两者 + BA 需求文档 | 无（只报告） |
| Deploy Agent | `<repo-root>/Deploy` | `deploy` 分支内容 + 镜像清单 | 仅 `<repo-root>/Deploy/**` |
| Explore Agent | 任意 | 全部 | 无（只读） |

## 3. 为什么 `BA/demands/...` 是错的写法

在 `feature-REQ-001/` 里执行 `cat BA/demands/REQ-001/demand.md`，解析的是：

```text
<repo-root>/feature-REQ-001/BA/demands/REQ-001/demand.md   ← 不存在
```

而实际文件在：

```text
<repo-root>/BA/demands/REQ-001/demand.md                   ← 正确
```

正确写法有三种，任选其一：

```bash
cat <repo-root>/BA/demands/REQ-001/demand.md    # 推荐：显式、可复制
cat ../BA/demands/REQ-001/demand.md             # 平铺布局下也成立
REQ_DIR="$(git rev-parse --path-format=absolute --git-common-dir)/../BA"  # 脚本里用
```

## 4. 兄弟目录可见 ≠ 可以写

平铺布局的副作用：`../BA`、`../code` 在物理上**都存在**。

- **读**：允许（只读探查需求、复用测试用例）。
- **写**：**禁止**。在 `feature-` 里改 `../BA` 会落到 `demand` 分支的 worktree 里，产生"用户没让你改的提交"，且绕过 BA 的状态机。
- 需要改 BA 的内容 → 交给 BA Agent，或在自己的报告里写明。

## 5. 脚本里的路径

```bash
ROOT="$(git rev-parse --path-format=absolute --git-common-dir | xargs dirname)"
BA="$ROOT/BA"
FEAT="$(git rev-parse --show-toplevel)"
```

`git rev-parse --git-common-dir` 在任意 worktree 中都指向**主仓库**的 `.git`，因此它的父目录就是 `<repo-root>`。这是唯一可靠的跨 worktree 定位方式。
