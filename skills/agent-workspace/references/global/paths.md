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


## 6. 写入边界与导出目录（硬规则）

**所有写操作必须落在项目根或当前 worktree 内。** 不允许写到盘根、用户目录、系统临时目录。

| 用途 | 默认路径 | 说明 |
|------|----------|------|
| 临时文件 / 缓存 | `<repo-root>/.aw/tmp/` | 可随时删；不要放 `/tmp`、`C:/tmp`、`D:/tmp` |
| 导出 / 截图 / 日志 | `<repo-root>/.aw/exports/<REQ>/` | 本机产物，默认不提交 |
| 随需求提交的证据 | `<repo-root>/BA/demands/<REQ>/evidence/` | 只有 BA 写；Dev 放自己的 `feature-meta/evidence/` |
| 代码 | 当前 worktree | 不跨 worktree 写 |

禁止：

- `C:/`、`D:/` 等盘根，`C:/tmp`、`D:/tmp`；
- `%TEMP%`、`%USERPROFILE%`、Desktop、Downloads、`~/tmp`；
- 任何用 `..` 逃出项目根 / 当前 worktree 的路径；
- 把本机绝对路径写进提交、消息或报告（对外只写项目相对路径）。

工具必须使用系统临时目录时：

~~~text
1. 优先把 TMP / TEMP / TMPDIR 指到 <repo-root>/.aw/tmp；
2. 改不了环境变量，就在项目内 cwd 运行，并把输出复制回 .aw/exports/<REQ>/；
3. 外部临时文件用完删除，不要留在 C:/ 或 D:/。
~~~

写前可用工具检查：

~~~bash
python <skill>/scripts/aw.py path check <path>          # workspace
python <skill>/scripts/aw_single.py path check <path>   # single
~~~

返回 `ALLOWED <rel>` 才写；`DENIED` 就停。

写前自检：

~~~text
解析目标绝对路径 → 确认前缀是允许根 → 再写。
不通过就停，不要“先写再挪”。
~~~

## 7. 脚本里的路径

```bash
ROOT="$(git rev-parse --path-format=absolute --git-common-dir | xargs dirname)"
BA="$ROOT/BA"
FEAT="$(git rev-parse --show-toplevel)"
```

`git rev-parse --git-common-dir` 在任意 worktree 中都指向**主仓库**的 `.git`，因此它的父目录就是 `<repo-root>`。这是唯一可靠的跨 worktree 定位方式。
