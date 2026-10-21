#!/usr/bin/env python3
"""Agent Workspace 工具：init / migrate / verify / audit / next-req.

只依赖 Python 3.8+ 标准库与 git 命令；不直接改写 .git 内部结构。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "assets" / "templates"
ROOT_FILES = {".gitignore", "README.md"}

OK, WARN, FAIL = "OK  ", "WARN", "FAIL"


class GitError(RuntimeError):
    pass


def git(*args: str, cwd: Path | str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    # core.quotepath=false：中文/空格文件名按原样输出，避免 "\346\226\207" 这类转义
    cmd = ["git", "-c", "core.quotepath=false", *args]
    proc = subprocess.run(
        cmd, cwd=str(cwd) if cwd else None,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and proc.returncode != 0:
        raise GitError(
            "git %s 失败 (code %s)\n%s" % (" ".join(args), proc.returncode, proc.stderr.strip())
        )
    return proc


def git_out(*args: str, cwd: Path | str | None = None) -> str:
    return git(*args, cwd=cwd).stdout.strip()


def _to_path(raw: str, base: Path | None = None) -> Path:
    """把 git 输出转换成真实路径。

    Git for Windows（MSYS 版）在部分场景返回 /c/Users/... 形式；直接用 pathlib 拼会得到
    C:/c/Users/... 这种坏路径，因此必须先做一次映射。
    """
    raw = raw.strip().strip('"')
    if os.name == "nt":
        m = re.match(r"^/([A-Za-z])/(.*)$", raw)
        if m:
            return Path("%s:/%s" % (m.group(1).upper(), m.group(2))).resolve()
    path = Path(raw)
    if not path.is_absolute():
        path = (base or Path.cwd()) / path
    return path.resolve()


def repo_root(start: Path | str | None = None) -> Path:
    """返回 workspace 主 worktree 的根目录（任意 worktree 中都成立）。"""
    try:
        common = git_out("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=start)
    except GitError:
        common = git_out("rev-parse", "--git-common-dir", cwd=start)
    base = Path(start) if start else Path.cwd()
    return _to_path(common, base=base).parent


def worktrees(root: Path) -> list[dict]:
    out = git_out("worktree", "list", "--porcelain", cwd=root)
    result, cur = [], None
    for line in out.splitlines():
        if line.startswith("worktree "):
            cur = {"path": _to_path(line[len("worktree "):]), "branch": None, "prunable": False}
            result.append(cur)
        elif line.startswith("branch ") and cur is not None:
            cur["branch"] = line[len("branch "):].replace("refs/heads/", "")
        elif line.startswith("detached") and cur is not None:
            cur["branch"] = "(detached)"
        elif line.strip() == "prunable" and cur is not None:
            cur["prunable"] = True
    return result


def branch_of(path: Path) -> str:
    return git_out("rev-parse", "--abbrev-ref", "HEAD", cwd=path)


def read_template(name: str) -> str:
    path = TEMPLATE_DIR / name
    if not path.exists():
        raise GitError("模板缺失: %s" % path)
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _clean_worktree(root: Path) -> None:
    """删除工作区内的所有内容（保留 .git）。调用前确保内容已在别的分支提交。"""
    for item in root.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir() and not item.is_symlink():
            shutil.rmtree(item, ignore_errors=True)
        else:
            item.unlink(missing_ok=True)


def ensure_identity(repo: Path) -> list[str]:
    """仓库没配 user.email 时，用 -c 临时身份，返回要附加的 git 参数。"""
    email = git("config", "user.email", cwd=repo, check=False).stdout.strip()
    if email:
        return []
    return ["-c", "user.name=Agent Workspace", "-c", "user.email=noreply@agent-workspace.local"]


def commit(repo: Path, message: str, identity: list[str]) -> None:
    git(*identity, "commit", "-q", "-m", message, cwd=repo)


# ---------------------------------------------------------------- verify

def _check_root_files(root: Path, report) -> None:
    files = sorted(p for p in git_out("ls-files", cwd=root).splitlines() if p)
    if files == sorted(ROOT_FILES):
        report(OK, "根容器跟踪文件", ".gitignore + README.md")
    elif not files:
        report(FAIL, "根容器跟踪文件", "为空：workspace 分支丢失了两个根文件")
    else:
        extra = [f for f in files if f not in ROOT_FILES]
        report(FAIL, "根容器跟踪文件", "多余条目 %d 个: %s" % (len(extra), ", ".join(extra[:8])))

    status = git_out("status", "--porcelain", cwd=root)
    if status:
        lines = status.splitlines()
        report(WARN, "根目录工作区", "有 %d 项待处理: %s" % (len(lines), lines[0]))
    else:
        report(OK, "根目录工作区", "干净")

    dry = git_out("add", "-A", "--dry-run", cwd=root)
    if dry:
        report(FAIL, "忽略规则", "git add -A 会新增: %s" % dry.splitlines()[0])
    else:
        report(OK, "忽略规则", "git add -A 无新增")


def _check_topology(root: Path, report) -> None:
    entries = worktrees(root)
    paths = {e["path"] for e in entries}
    if root not in paths:
        report(FAIL, "主 worktree", "未在 git worktree list 中找到 %s" % root)
        return
    nested, stale, outside = [], [], []
    for e in entries:
        if e["path"] == root:
            continue
        if e.get("prunable") or not e["path"].exists():
            stale.append(str(e["path"]))
            continue
        try:
            e["path"].relative_to(root)
        except ValueError:
            outside.append(str(e["path"]))
            continue
        if e["path"].parent != root:
            nested.append(str(e["path"]))
    if nested:
        report(FAIL, "worktree 层级", "存在中间层或嵌套: %s" % ", ".join(nested))
    else:
        report(OK, "worktree 层级", "全部平铺在仓库根下一层")
    if outside:
        report(FAIL, "worktree 位置", "记录指向仓库外（仓库被复制/移动过？）: %s" % ", ".join(outside[:3]))
    if stale:
        report(WARN, "失效登记", "路径已不存在，执行 git worktree prune: %s" % ", ".join(stale[:3]))

    if (root / "workspaces").exists():
        report(FAIL, "中间目录", "存在 workspaces/，违反平铺约束")
    else:
        report(OK, "中间目录", "无 workspaces/ 等中间层")

    expected = {"code": "develop", "BA": "demand", "Deploy": "deploy"}
    current = {e["path"].name: e["branch"] for e in entries if e["path"] != root}
    missing = [d for d in expected if d not in current]
    if missing:
        report(WARN, "基础 worktree", "缺少 %s" % ", ".join(missing))
    else:
        report(OK, "基础 worktree", "code / BA / Deploy 就位")
    for d, br in expected.items():
        if d in current and current[d] != br:
            report(FAIL, "分支归属", "%s 在 %s 上，应为 %s" % (d, current[d], br))

    prunable = [str(e["path"]) for e in entries if e.get("prunable")]
    if prunable:
        report(WARN, "失效登记", "需要 git worktree prune: %s" % ", ".join(prunable))


def _check_naming(root: Path, report) -> None:
    bad = []
    for e in worktrees(root):
        name = e["path"].name
        br = e["branch"] or ""
        if name.startswith("feature-"):
            m = re.fullmatch(r"feature-REQ-(\d{3})", name)
            if not m or br != "feature/REQ-%s" % m.group(1):
                bad.append("%s → %s" % (name, br))
        elif name.startswith("hotfix-"):
            if not br.startswith("hotfix/"):
                bad.append("%s → %s" % (name, br))
        elif name in ("code", "BA", "Deploy"):
            continue
        elif e["path"] != root:
            bad.append("无法识别的 worktree %s" % name)
    if bad:
        report(FAIL, "命名规范", "; ".join(bad))
    else:
        report(OK, "命名规范", "feature-REQ-xxx / hotfix-xxx 一致")


def _check_feature_artifacts(root: Path, report) -> None:
    missing = []
    for e in worktrees(root):
        if not e["path"].name.startswith("feature-"):
            continue
        if not (e["path"] / ".feature" / "manifest.json").exists():
            missing.append(str(e["path"].relative_to(root)))
    if missing:
        report(WARN, "feature 产物", "缺 .feature/manifest.json: %s" % ", ".join(missing))
    else:
        report(OK, "feature 产物", "无 feature worktree 或产物齐全")


def cmd_verify(args) -> int:
    root = repo_root()
    rows: list[tuple[str, str, str]] = []

    def report(level: str, check: str, detail: str) -> None:
        rows.append((level, check, detail))

    report(OK, "仓库根", str(root))
    branch = branch_of(root)
    if branch == "workspace":
        report(OK, "根分支", "workspace")
    elif not (root / "code").is_dir():
        report(FAIL, "根分支", "%s 不是 workspace 仓库：先 aw.py init，或在 <repo-root> 执行" % root)
        for level, check, detail in rows:
            print("[%s] %-14s %s" % (level, check, detail))
        return 1
    else:
        report(FAIL, "根分支", "当前是 %s，应为 workspace（git checkout workspace）" % branch)

    _check_root_files(root, report)
    _check_topology(root, report)
    _check_naming(root, report)
    _check_feature_artifacts(root, report)

    fails = sum(1 for r in rows if r[0] == FAIL)
    warns = sum(1 for r in rows if r[0] == WARN)
    for level, check, detail in rows:
        print("[%s] %-14s %s" % (level, check, detail))
    print("\n结论: %d FAIL / %d WARN" % (fails, warns))
    if args.json:
        print(json.dumps(
            {"root": str(root), "branch": branch,
             "rows": [{"level": l, "check": c, "detail": d} for l, c, d in rows],
             "fails": fails, "warns": warns},
            ensure_ascii=False, indent=2))
    if fails:
        return 1
    if args.strict and warns:
        return 1
    return 0


# ---------------------------------------------------------------- audit

def _table(header: list[str], rows: list[list[str]]) -> None:
    widths = [len(h) for h in header]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(header))
    print(line)
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r)))


def _last_activity(root: Path, session: str) -> int | None:
    out = git("log", "--all", "--format=%ct", "--grep", "[session: %s]" % session,
              "-1", cwd=root, check=False).stdout.strip()
    return int(out) if out.isdigit() else None


def _read_registry(root: Path) -> list[dict]:
    path = root / "BA" / "dispatch" / "agent-registry.md"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] in ("session_id",) or set(cells[0]) <= set("-: "):
            continue
        if cells[0].startswith("_（示例）") or cells[0].startswith("_("):
            continue
        rows.append({"session": cells[0], "host": cells[1], "role": cells[2],
                     "status": cells[3], "last_seen": cells[-1]})
    return rows


def cmd_audit(args) -> int:
    root = repo_root()
    problems = 0
    branch = branch_of(root)
    if branch != "workspace" and not (root / "code").is_dir():
        print("当前目录不是 workspace 仓库: %s" % root, file=sys.stderr)
        print("先 aw.py init 初始化，或 cd 到 <repo-root> 再执行。", file=sys.stderr)
        return 1
    print("== workspace 卫生")
    files = sorted(p for p in git_out("ls-files", cwd=root).splitlines() if p)
    status = git_out("status", "--porcelain", cwd=root)
    print("  根分支      : %s%s" % (branch, "" if branch == "workspace" else "  <-- 应为 workspace"))
    print("  跟踪文件    : %s" % (", ".join(files) or "(空)"))
    print("  工作区      : %s" % ("干净" if not status else "%d 项待处理" % len(status.splitlines())))
    if branch != "workspace" or files != sorted(ROOT_FILES):
        problems += 1

    print("\n== worktree 拓扑")
    rows = []
    for e in worktrees(root):
        rel = "." if e["path"] == root else str(e["path"].relative_to(root))
        try:
            dirty = git("status", "--porcelain", cwd=e["path"], check=False).stdout.strip()
        except OSError:
            dirty = "?"
        rows.append([rel, e["branch"] or "-", "%d" % (len(dirty.splitlines()) if dirty else 0),
                     "prunable" if e.get("prunable") else ""])
    _table(["路径", "分支", "未提交", "备注"], rows)

    print("\n== 可回收的 feature worktree")
    cleanup_rows = []
    for e in worktrees(root):
        if not e["path"].name.startswith(("feature-", "hotfix-")):
            continue
        br = e["branch"] or ""
        try:
            dirty = git("status", "--porcelain", cwd=e["path"], check=False).stdout.strip()
            ahead = git("log", "--oneline", "origin/develop..HEAD", cwd=e["path"], check=False).stdout.strip()
        except OSError:
            dirty, ahead = "?", "?"
        merged = git("branch", "--merged", "develop", "--format=%(refname:short)",
                     cwd=root, check=False).stdout.split()
        cleanup_rows.append([
            e["path"].name, br, "yes" if dirty else "no",
            "yes" if ahead else "no", "yes" if br in merged else "no",
            "可回收" if (not dirty and not ahead and br in merged) else "保留",
        ])
    if cleanup_rows:
        _table(["worktree", "分支", "脏", "未推送", "已合并", "建议"], cleanup_rows)
    else:
        print("  （无 feature/hotfix worktree）")

    print("\n== session（阈值 %d 分钟）" % args.stale_minutes)
    sessions = _read_registry(root)
    if not sessions:
        print("  （无注册记录）")
    else:
        now = _dt.datetime.now().timestamp()
        srows = []
        for s in sessions:
            ts = _last_activity(root, s["session"])
            if ts is None:
                srows.append([s["session"], s["status"], "无 commit", "?"])
                continue
            mins = int((now - ts) / 60)
            level = "stale" if mins > args.stale_minutes else "fresh"
            srows.append([s["session"], s["status"], "%d 分钟前" % mins, level])
            if level == "stale" and s["status"] == "online":
                problems += 1
        _table(["session", "登记状态", "最后活动", "判定"], srows)

    print("\n结论: %s" % ("需要处理 %d 项" % problems if problems else "干净"))
    return 0 if problems == 0 else 1


# ---------------------------------------------------------------- next-req

def cmd_next_req(args) -> int:
    root = repo_root()
    registry = root / "BA" / "dispatch" / "req-registry.md"
    raw = registry.read_text(encoding="utf-8") if registry.exists() else ""
    # 模板里的示例行以 "| _（示例）" 开头，不参与编号计算
    text = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("| _"))
    used = [int(m) for m in re.findall(r"REQ-(\d{3})", text)]
    nxt = (max(used) + 1) if used else 1
    print("REQ-%03d" % nxt)
    return 0


# ---------------------------------------------------------------- init

def _copy_template(dst: Path, name: str, replace: dict | None = None) -> None:
    text = read_template(name)
    for k, v in (replace or {}).items():
        text = text.replace(k, v)
    write_text(dst, text)


def cmd_init(args) -> int:
    target = Path(args.dir).resolve()
    if target.exists() and any(target.iterdir()):
        print("目录非空，拒绝初始化: %s" % target, file=sys.stderr)
        return 2
    target.mkdir(parents=True, exist_ok=True)
    name = args.name or target.name

    print("→ git init  %s" % target)
    git("init", "-q", cwd=target)
    if (target / ".git" / "HEAD").exists():
        git("checkout", "-q", "-b", "workspace", cwd=target, check=False)

    ident = ensure_identity(target)

    # 1) workspace 根容器
    _copy_template(target / "README.md", "root-readme.md.tpl",
                   {"{项目名称}": name, "{一句话说明项目做什么、给谁用}": args.description or "（待补充）"})
    _copy_template(target / ".gitignore", "root-gitignore.tpl")
    git("add", "README.md", ".gitignore", cwd=target)
    commit(target, "[Workspace] 初始化导航 + 双层防御 .gitignore", ident)
    print("  ✓ workspace: 2 个文件")

    # 2) main（orphan）
    git("checkout", "-q", "--orphan", "main", cwd=target)
    git("reset", "-q", cwd=target)
    _clean_worktree(target)
    (target / ".gitignore").unlink(missing_ok=True)
    write_text(target / "README.md", "# %s\n" % name)
    git("add", "README.md", cwd=target)
    commit(target, "[Init] main branch placeholder", ident)
    print("  ✓ main")

    # 3) develop
    git("checkout", "-q", "-b", "develop", "main", cwd=target)
    print("  ✓ develop")

    # 4) demand（orphan）
    git("checkout", "-q", "--orphan", "demand", cwd=target)
    git("reset", "-q", cwd=target)
    _clean_worktree(target)
    _copy_template(target / "README.md", "ba-readme.md.tpl")
    _copy_template(target / ".gitignore", "ba-gitignore.tpl")
    for tpl, dst in [
        ("agent-registry.md.tpl", "dispatch/agent-registry.md"),
        ("req-registry.md.tpl", "dispatch/req-registry.md"),
        ("dispatch-rules.md.tpl", "dispatch/rules.md"),
        ("cleanup-log.md.tpl", "dispatch/cleanup-log.md"),
    ]:
        _copy_template(target / dst, tpl)
    for d in ("demands", "backlog/inbox", "backlog/refined", "sprint", "decisions"):
        write_text(target / d / ".gitkeep", "")
    git("add", "-A", cwd=target)
    commit(target, "[Init] 需求管理分支（含 bootstrap）", ident)
    print("  ✓ demand")

    # 5) deploy（orphan）
    git("checkout", "-q", "--orphan", "deploy", cwd=target)
    git("reset", "-q", cwd=target)
    _clean_worktree(target)
    _copy_template(target / "README.md", "deploy-readme.md.tpl")
    _copy_template(target / ".gitignore", "deploy-gitignore.tpl")
    for d in ("apps", "environments", "releases", "scripts", "argocd/applications", "argocd/bootstrap"):
        write_text(target / d / ".gitkeep", "")
    git("add", "-A", cwd=target)
    commit(target, "[Init] 部署分支", ident)
    print("  ✓ deploy")

    # 6) 回 workspace 并建平铺 worktree
    _clean_worktree(target)
    git("checkout", "-q", "workspace", cwd=target)
    for path, branch in (("code", "develop"), ("BA", "demand"), ("Deploy", "deploy")):
        git("worktree", "add", path, branch, cwd=target)
        print("  ✓ worktree %-6s → %s" % (path, branch))

    # 7) develop 的 .gitignore（追踪 .local/）
    code = target / "code"
    _copy_template(code / ".gitignore", "code-gitignore.tpl")
    git("add", ".gitignore", cwd=code)
    commit(code, "[Init] 忽略 .local/", ident)
    print("  ✓ code/.gitignore")

    for d in ("code", "BA", "Deploy"):
        for sub in ("discussions", "analysis", "drafts", "references"):
            (target / d / ".local" / sub).mkdir(parents=True, exist_ok=True)

    # 8) 远程（不自动 push）
    if args.remote:
        git("remote", "add", "origin", args.remote, cwd=target, check=False)
        print("  ✓ origin = %s" % args.remote)
        if args.push:
            git("push", "-u", "origin", "workspace", "main", "develop", "demand", "deploy", cwd=target)
            print("  ✓ pushed")

    print("\n完成。下一步：")
    print("  cd %s" % target)
    print("  python %s verify" % Path(__file__).as_posix())
    if args.remote and not args.push:
        print("  git push -u origin workspace main develop demand deploy   # 需要时手动执行")
    print("  # 然后把远程默认分支改为 workspace")
    return 0


# ---------------------------------------------------------------- migrate

def _move_untracked(root: Path, files: list[str], dest: Path) -> None:
    for rel in files:
        src = root / rel
        if not src.exists():
            continue
        dst = dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))


def _remove_empty_dirs(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir() and ".git" not in path.parts and not any(path.iterdir()):
            try:
                path.rmdir()
            except OSError:
                pass


def cmd_migrate(args) -> int:
    root = repo_root()
    if branch_of(root) == "workspace":
        print("已经是 workspace 布局，无需迁移。", file=sys.stderr)
        return 2
    main_branch = args.main or branch_of(root)
    if not main_branch or main_branch in ("HEAD", "workspace"):
        print("无法确定主分支，请用 --main 指定。", file=sys.stderr)
        return 2

    dirty = git_out("status", "--porcelain", "--untracked-files=no", cwd=root)
    if dirty:
        print("有未提交的已跟踪改动，先 commit 或 stash：\n%s" % dirty, file=sys.stderr)
        return 2
    if len(worktrees(root)) > 1:
        print("已存在多个 worktree，请先手工整理。", file=sys.stderr)
        return 2

    backup = Path(args.backup) if args.backup else root.parent / ("backup-%s.git" % _dt.datetime.now().strftime("%Y%m%d%H%M%S"))
    if not args.no_backup:
        print("→ 备份 %s" % backup)
        git("clone", "--mirror", str(root), str(backup))
    if not args.yes:
        print("\n即将迁移 %s（主分支 %s）。确认继续请输入 yes：" % (root, main_branch))
        if input().strip().lower() not in ("yes", "y"):
            print("已取消。")
            return 2

    tracked = [p for p in git_out("ls-tree", "-r", "--name-only", main_branch, cwd=root).splitlines() if p]
    untracked = [p for p in git_out("ls-files", "--others", "--exclude-standard", cwd=root).splitlines() if p]
    print("  跟踪文件 %d 个，本地未跟踪 %d 个" % (len(tracked), len(untracked)))

    print("→ 建立 workspace 根容器")
    git("checkout", "-q", "--orphan", "workspace", cwd=root)
    git("reset", "-q", cwd=root)
    ident = ensure_identity(root)
    _copy_template(root / ".gitignore", "root-gitignore.tpl")
    _copy_template(root / "README.md", "root-readme.md.tpl",
                   {"{项目名称}": root.name, "{一句话说明项目做什么、给谁用}": "（迁移自 %s）" % main_branch})
    git("add", "README.md", ".gitignore", cwd=root)
    commit(root, "[Workspace] 迁移：初始化根容器", ident)

    aside = Path(tempfile.mkdtemp(prefix="aw-aside-"))
    try:
        _move_untracked(root, untracked, aside)
        for rel in tracked:
            if rel in ROOT_FILES:
                continue
            p = root / rel
            if not p.exists():
                continue
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p, ignore_errors=True)   # 子模块（gitlink）
            else:
                p.unlink()
        _remove_empty_dirs(root)

    finally:
        pass

    print("→ 建立 demand / deploy")
    git("checkout", "-q", "--orphan", "demand", cwd=root)
    git("reset", "-q", cwd=root)
    _clean_worktree(root)
    _copy_template(root / "README.md", "ba-readme.md.tpl")
    _copy_template(root / ".gitignore", "ba-gitignore.tpl")
    for tpl, dst in [
        ("agent-registry.md.tpl", "dispatch/agent-registry.md"),
        ("req-registry.md.tpl", "dispatch/req-registry.md"),
        ("dispatch-rules.md.tpl", "dispatch/rules.md"),
        ("cleanup-log.md.tpl", "dispatch/cleanup-log.md"),
    ]:
        _copy_template(root / dst, tpl)
    for d in ("demands", "backlog/inbox", "backlog/refined", "sprint", "decisions"):
        write_text(root / d / ".gitkeep", "")
    git("add", "-A", cwd=root)
    commit(root, "[Init] 需求管理分支（含 bootstrap）", ident)

    git("checkout", "-q", "--orphan", "deploy", cwd=root)
    git("reset", "-q", cwd=root)
    _clean_worktree(root)
    _copy_template(root / "README.md", "deploy-readme.md.tpl")
    _copy_template(root / ".gitignore", "deploy-gitignore.tpl")
    for d in ("apps", "environments", "releases", "scripts", "argocd/applications", "argocd/bootstrap"):
        write_text(root / d / ".gitkeep", "")
    git("add", "-A", cwd=root)
    commit(root, "[Init] 部署分支", ident)

    _clean_worktree(root)
    git("checkout", "-q", "workspace", cwd=root)
    git("worktree", "add", "code", main_branch, cwd=root)
    for item in sorted(aside.rglob("*")):
        if item.is_file():
            rel = item.relative_to(aside)
            dst = root / "code" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(dst))
    shutil.rmtree(aside, ignore_errors=True)
    git("worktree", "add", "BA", "demand", cwd=root)
    git("worktree", "add", "Deploy", "deploy", cwd=root)

    print("\n迁移完成。还需要你手工做：")
    print("  1. 远程默认分支改为 workspace（GitHub/GitLab settings）")
    print("  2. 各 worktree 的 .gitignore 加 .local/（develop/demand/deploy 各自提交）")
    print("  3. CI 显式 checkout %s" % main_branch)
    print("  4. 通知协作者重新 clone")
    print("  5. 跑 python %s verify 自检" % Path(__file__).as_posix())
    return 0


# ---------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aw.py", description="Agent Workspace 工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="初始化一个新的 workspace 项目")
    p_init.add_argument("dir")
    p_init.add_argument("--name", default=None)
    p_init.add_argument("--description", default=None)
    p_init.add_argument("--remote", default=None)
    p_init.add_argument("--push", action="store_true", help="初始化后直接 push（外部可见动作）")
    p_init.set_defaults(func=cmd_init)

    p_mig = sub.add_parser("migrate", help="把已有仓库原地迁移为 workspace 布局")
    p_mig.add_argument("--main", default=None, help="现有主分支名，默认当前分支")
    p_mig.add_argument("--backup", default=None)
    p_mig.add_argument("--no-backup", action="store_true")
    p_mig.add_argument("--yes", action="store_true")
    p_mig.set_defaults(func=cmd_migrate)

    p_ver = sub.add_parser("verify", help="校验 workspace 硬约束")
    p_ver.add_argument("--strict", action="store_true", help="WARN 也视为失败")
    p_ver.add_argument("--json", action="store_true")
    p_ver.set_defaults(func=cmd_verify)

    p_aud = sub.add_parser("audit", help="只读巡检")
    p_aud.add_argument("--stale-minutes", type=int, default=120)
    p_aud.set_defaults(func=cmd_audit)

    p_req = sub.add_parser("next-req", help="计算下一个可用 REQ 编号")
    p_req.set_defaults(func=cmd_next_req)
    return parser


def _init_console() -> None:
    """让 Windows 控制台按 UTF-8 输出中文（cmd.exe 默认 cp936 会乱码）。"""
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _init_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except GitError as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1
    except OSError as exc:
        print("系统错误: %s" % exc, file=sys.stderr)
        print("提示: 请确认路径存在、未被占用（OneDrive/杀毒软件可能锁文件），且磁盘可写。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
