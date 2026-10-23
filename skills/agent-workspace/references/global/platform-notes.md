# 平台差异（Windows / macOS / Linux）

`aw.py` 只用标准库 + git 命令，但有些平台细节值得先知道。

## Windows

### 1. 调用方式

| 方式 | 命令 |
|------|------|
| 推荐（cmd / PowerShell） | `aw.cmd verify` / `.\aw.ps1 verify` |
| Python 启动器 | `py -3 scripts\aw.py verify` |
| 只要 python 在 PATH | `python scripts\aw.py verify` |

`aw.cmd` 会自动在 `py` 与 `python` 之间选择。

### 2. 中文输出

脚本启动时会：

1. 调 `SetConsoleOutputCP(65001)` 把控制台切到 UTF-8；
2. 把 stdout / stderr 重设为 UTF-8（`errors="replace"`）。

所以 **cmd.exe 默认 cp936 也不会乱码**。若仍乱码，通常是重定向到文件后用 GBK 编辑器打开——文件本身是 UTF-8。

### 3. 路径形式

Git for Windows 是 MSYS 版，部分命令会返回 `/c/Users/...`。脚本内部统一转成 `C:/Users/...`。
你自己写命令时用：

```bash
git rev-parse --path-format=absolute --show-toplevel
```

不要用 PowerShell 的 `pwd`（输出带 `Microsoft.PowerShell.Core\FileSystem::` 前缀，不能直接喂给 git）。

### 4. 中文 / 空格文件名

脚本对所有 git 调用都加了 `-c core.quotepath=false`，中文文件名不会被转成 `"\344\270\255"` 形式。

如果你的仓库有中文文件名，**不要**拿 `git ls-files` 的输出直接做字符串拼接再删文件——先确认没被引号包裹。

### 5. 长路径

Windows 默认 260 字符上限，`feature-REQ-001/src/...` 容易踩到：

```powershell
git config --global core.longpaths true
```

并在系统策略里启用 Win32 长路径（注册表 `LongPathsEnabled=1`）。

### 6. 跨盘符

`migrate` 会把未跟踪文件临时挪到系统 temp（通常 C:）。仓库在 D: 时会退化成「复制 + 删除」，`node_modules` 大会很慢。

规避：迁移前把 `node_modules` / `.venv` 移出仓库，或先 `git clean` 掉可再生目录。

### 7. 文件被占用

OneDrive / 杀毒软件 / 正在跑的 dev server 会锁文件，导致 `worktree remove` 或 `migrate` 失败：

- 关掉占用进程；
- 或把仓库移出 OneDrive 同步目录；
- `--force` 只跳过 git 检查，不解锁文件。

### 8. 换行符

`core.autocrlf=true` 不影响本工作流（模板都是 `.md` / `.tpl`）。若要 Linux CI 也一致，加 `.gitattributes`：

```gitattributes
* text=auto eol=lf
*.cmd text eol=crlf
*.ps1 text eol=crlf
```

## macOS / Linux

### 启动 CLI

```bash
./skills/agent-workspace/scripts/aw verify
# 或
aw verify        # 软链/加入 PATH 后
```

### MCP

配置、路径与包装脚本见 `references/global/mcp.md` 的「Linux / macOS」一节。
要点：用 `python3`、`cwd` 用绝对 POSIX 路径、`AW_AGENT_ID` 用 `export`。

- 直接 `python3 scripts/aw.py ...`。
- macOS 默认大小写不敏感：`Feature-REQ-001` 与 `feature-REQ-001` 是同一个目录。
- CI 里跑 `verify` / `audit` 需要完整仓库：`actions/checkout` 用 `fetch-depth: 0`，否则 `git log` 拿不到历史。

## WSL

在 WSL 里操作 Windows 盘（`/mnt/d/...`）上的仓库：

- 极慢，且权限位失真；
- 可能报 `dubious ownership`：`git config --global --add safe.directory /mnt/d/...`；
- 建议仓库放 WSL 内部（`~/code/...`），Windows 侧用 `\\wsl$\` 访问。

## 通用自检

```bash
python scripts/aw.py verify --strict   # WARN 也算失败
python scripts/aw.py audit
```
