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
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "assets" / "templates"
ROOT_FILES = {".gitignore", "README.md"}

OK, WARN, FAIL = "OK  ", "WARN", "FAIL"


class GitError(RuntimeError):
    pass


class IdentityError(GitError):
    """没有 agent 名称——必须由人指定后才能继续。"""


def git(*args: str, cwd: Path | str | None = None, check: bool = True,
        timeout: float | None = None) -> subprocess.CompletedProcess:
    # core.quotepath=false：中文/空格文件名按原样输出，避免 "\346\226\207" 这类转义
    cmd = ["git", "-c", "core.quotepath=false", *args]
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd) if cwd else None, timeout=timeout,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        raise GitError("git %s 超时（%ss）" % (" ".join(args), timeout))
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


# ---------------------------------------------------------------- claim / queue
#
# 同机多 BA 共享一个仓库时的认领层：
#   - 身份：AW_AGENT_ID（稳定槽位）+ AW_SESSION_ID / DSH_SESSION_ID（本次启动）
#   - 互斥：OS 文件锁（进程退出自动释放）
#   - 状态：一个任务一个文件，避免整表覆盖
#   - WIP：每个 agent_id 同时只能持有 1 个任务，由工具强制，不靠提醒

AW_DIR = ".aw"
CLAIM_STATES = ("active", "blocked", "review")


def aw_path(root: Path, *parts: str) -> Path:
    path = root / AW_DIR
    for part in parts:
        path = path / part
    return path


def aw_init(root: Path) -> None:
    for sub in ("locks", "claims", "sessions", "archive", "outbox"):
        aw_path(root, sub).mkdir(parents=True, exist_ok=True)
    queue = aw_path(root, "queue.json")
    if not queue.exists():
        write_text(queue, "[]\n")


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 唯一临时名：并发写同一文件时不会互相踩（Windows 上固定 .tmp 会 WinError 32）
    tmp = path.with_name("%s.%d.%s.tmp" % (path.name, os.getpid(), secrets.token_hex(2)))
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    os.replace(tmp, path)


class FileLock:
    """跨进程排他锁：Windows 用 msvcrt，POSIX 用 fcntl，进程退出自动释放。"""

    def __init__(self, path: Path, timeout: float = 10.0):
        self.path = path
        self.timeout = timeout
        self.fd: int | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(str(self.path), os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.time() + self.timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.time() > deadline:
                    os.close(self.fd)
                    self.fd = None
                    raise TimeoutError("等待锁超时: %s" % self.path)
                time.sleep(0.05)

    def __exit__(self, *exc) -> None:
        if self.fd is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)
            self.fd = None


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            kernel32.CloseHandle(handle)
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


SESSION_TTL_SECONDS = 1800


def _session_alive(rec: dict, ttl: int = SESSION_TTL_SECONDS) -> bool:
    """存活判定：显式退出 > 同机 pid > 心跳新鲜度。"""
    if not rec:
        return False
    if rec.get("status") == "offline":
        return False
    if rec.get("host") == socket.gethostname():
        pid = int(rec.get("pid") or 0)
        if pid and pid_alive(pid):
            return True
    seen = rec.get("last_seen") or ""
    try:
        ts = _dt.datetime.fromisoformat(seen).timestamp()
    except ValueError:
        return False
    return (time.time() - ts) < ttl


def terminal_anchor() -> str:
    """终端级锚点：同一个终端里的命令共享，不同终端互不相同。

    不依赖 agent 工具注入环境变量——WT_SESSION 等由终端自己设置。
    """
    for key in ("WT_SESSION", "TERM_SESSION_ID", "TMUX_PANE", "SSH_TTY", "TTY"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return "%s=%s" % (key, value)
    return ""


def _binding_key(anchor: str) -> str:
    return "%s|%s" % (socket.gethostname(), anchor)


def load_bindings(root: Path) -> dict:
    return read_json(aw_path(root, "identities.json"), {})


def save_bindings(root: Path, data: dict) -> None:
    write_json(aw_path(root, "identities.json"), data)


ROSTER_REL = ("BA", "plan", "agents.json")


def roster_path(root: Path) -> Path:
    return root.joinpath(*ROSTER_REL)


def load_roster(root: Path) -> list[dict]:
    data = read_json(roster_path(root), {})
    agents = data.get("agents") if isinstance(data, dict) else None
    return [a for a in (agents or []) if isinstance(a, dict) and a.get("id")]


def save_roster(root: Path, agents: list[dict]) -> None:
    write_json(roster_path(root), {"agents": agents})


def active_agents(root: Path) -> set[str]:
    return {a["id"] for a in load_roster(root) if a.get("status", "active") == "active"}


def validate_recipients(root: Path, to: list[str], cc: list[str], force: bool = False) -> None:
    """收件人必须是已注册且 active 的 agent（或 all / role:x 组）。"""
    if force:
        return
    roster = load_roster(root)
    if not roster:
        return  # 未配置 roster：保持向后兼容，不拦
    known = {a["id"]: a for a in roster}
    active = active_agents(root)
    for token in [t for t in to + cc if t]:
        if token == "all":
            if not active:
                raise GitError("没有 active 的 agent，无法广播")
            continue
        if token.startswith("role:"):
            role = token[5:]
            if not any(a.get("role") == role and a["id"] in active for a in roster):
                raise GitError("没有 active 的 role:%s" % role)
            continue
        if token not in known:
            sample = ", ".join(sorted(known)[:8])
            raise GitError("未注册的 agent: %s\n已注册: %s" % (token, sample or "（空）"))
        if token not in active:
            raise GitError("%s 不是 active 状态（Planner 可用 agent activate 恢复）" % token)


def bind_identity(root: Path, key: str, name: str, force: bool = False) -> tuple[bool, str | None]:
    """原子绑定：加锁读-改-写，避免并发丢绑定。"""
    with FileLock(aw_path(root, "locks", "identities.lock"), timeout=10):
        bindings = load_bindings(root)
        old = (bindings.get(key) or {}).get("agent_id")
        if old and old != name and not force:
            return False, old
        bindings[key] = {"agent_id": name, "bound_at": _now()}
        save_bindings(root, bindings)
        return True, old


def resolve_identity(root: Path, role: str = "ba", rebind: bool = False) -> dict:
    aw_init(root)
    explicit = (os.environ.get("AW_AGENT_ID") or "").strip()
    no_bind = os.environ.get("AW_NO_BIND") == "1"
    anchor = "" if no_bind else terminal_anchor()
    bindings = load_bindings(root)
    key = _binding_key(anchor) if anchor else ""
    bound = bindings.get(key, {})
    source = os.environ.get("AW_AGENT_SOURCE") or ("env AW_AGENT_ID" if explicit else "")

    if explicit:
        agent_id = explicit
        if anchor:
            ok, old = bind_identity(root, key, agent_id, force=rebind)
            if not ok:
                raise GitError(
                    "这个终端已经绑定 %s，不能改名成 %s。\n"
                    "要改绑定：aw.py agent bind %s --force" % (old, agent_id, agent_id)
                )
            source = source or "--agent"
    elif bound and bound.get("agent_id"):
        agent_id = bound["agent_id"]
        source = "terminal"
    else:
        raise IdentityError(
            "MISSING_AGENT_ID\n"
            "还没有 agent 名称，不能继续。\n"
            "两种方式（二选一）：\n"
            "  1) 指定一次，本终端会记住：aw.py --agent pcA-ba-1 agent whoami\n"
            "  2) 显式绑定：            aw.py agent bind pcA-ba-1\n"
            "如果启动器能设置环境变量，也可以用 AW_AGENT_ID。"
        )
    session_id = (
        os.environ.get("AW_SESSION_ID")
        or os.environ.get("DSH_SESSION_ID")
        or "%s-%s-%s" % (agent_id, _dt.datetime.now().strftime("%Y%m%d%H%M%S"), os.urandom(2).hex())
    )
    # 会话文件按 agent 槽位归并：一个槽位同时只有一个活会话
    aw_init(root)
    path = aw_path(root, "sessions", "%s.json" % agent_id)
    old = read_json(path, {})
    agent_pid = int(os.environ.get("AW_AGENT_PID") or 0)
    if not agent_pid and old.get("pid") and pid_alive(int(old["pid"])):
        agent_pid = int(old["pid"])
    record = {
        "agent_id": agent_id,
        "session_id": session_id,
        "pid": agent_pid,
        "host": socket.gethostname(),
        "role": role,
        "cwd": str(Path.cwd()),
        "started_at": old.get("started_at") or _now(),
        "last_seen": _now(),
        "source": source,
    }
    write_json(path, record)
    return record


def load_claims(root: Path) -> list[dict]:
    claims = []
    for path in sorted(aw_path(root, "claims").glob("*.json")):
        data = read_json(path, None)
        if isinstance(data, dict) and data.get("req"):
            data["_path"] = str(path)
            claims.append(data)
    return claims


def load_queue(root: Path) -> list[dict]:
    data = read_json(aw_path(root, "queue.json"), [])
    return data if isinstance(data, list) else []


def save_queue(root: Path, queue: list[dict]) -> None:
    write_json(aw_path(root, "queue.json"), queue)


def claim_path(root: Path, req: str) -> Path:
    return aw_path(root, "claims", "%s.json" % req)


def holding_claim(claims: list[dict], agent_id: str) -> dict | None:
    for c in claims:
        if c.get("agent_id") == agent_id and c.get("state", "active") in CLAIM_STATES:
            return c
    return None


def archive_claim(root: Path, claim: dict, reason: str) -> None:
    """把认领移出 claims/：归档 + 从活动集合中删除。"""
    data = {k: v for k, v in claim.items() if k != "_path"}
    data["released_at"] = _now()
    data["release_reason"] = reason
    stamp = _dt.datetime.now().strftime("%Y%m%d%H%M%S")
    write_json(aw_path(root, "archive", "%s-%s.json" % (claim["req"], stamp)), data)
    Path(claim["_path"]).unlink(missing_ok=True)


def requeue(root: Path, claim: dict, queue: list[dict], source: str) -> None:
    if not any(q["req"] == claim["req"] for q in queue):
        queue.insert(0, {"req": claim["req"], "title": claim.get("title", ""),
                         "added_at": _now(), "source": source})


def _reap_dead(root: Path, claims: list[dict], queue: list[dict]) -> int:
    """把死会话占用的认领归档并退回队列，返回处理条数。"""
    reaped = 0
    for c in claims:
        session = read_json(aw_path(root, "sessions", "%s.json" % c.get("agent_id", "")), {})
        if not _session_alive(session):
            requeue(root, c, queue, "recovered")
            archive_claim(root, c, "dead-session")
            reaped += 1
    return reaped


def _create_worktree(root: Path, req: str, base: str) -> None:
    name = "feature-%s" % req
    branch = "feature/%s" % req
    path = root / name
    if path.exists():
        cur = git("rev-parse", "--abbrev-ref", "HEAD", cwd=path, check=False).stdout.strip()
        if cur == branch:
            return
        raise GitError("%s 已存在且不在 %s 上（当前 %s）" % (name, branch, cur))
    has_branch = git("rev-parse", "--verify", "--quiet", "refs/heads/%s" % branch,
                     cwd=root, check=False).returncode == 0
    last = None
    # 同一仓库并发 worktree add 会撞 .git/worktrees 锁，这里用项目锁串行化
    with FileLock(aw_path(root, "locks", "worktree.lock"), timeout=30):
        for attempt in range(5):
            try:
                if has_branch:
                    git("worktree", "add", name, branch, cwd=root)
                else:
                    git("worktree", "add", name, "-b", branch, base, cwd=root)
                return
            except GitError as exc:
                last = exc
                time.sleep(0.3 * (2 ** attempt))
    raise GitError("创建 worktree 失败（重试 5 次）: %s" % last)


def _write_manifest(root: Path, req: str, ident: dict) -> None:
    wt = root / ("feature-%s" % req)
    if not wt.exists():
        return
    demands = root / "BA" / "demands"
    demand_dir = next((p for p in demands.glob("%s-*" % req)), demands / req) if demands.is_dir() else demands / req
    try:
        demand_rel = demand_dir.relative_to(root).as_posix()
    except ValueError:
        demand_rel = "BA/demands/%s" % req
    manifest = {
        "req": req,
        "branch": "feature/%s" % req,
        "agent_id": ident["agent_id"],
        "session_id": ident["session_id"],
        "owner": ident["agent_id"],
        "base_branch": "develop",
        "created_at": _now(),
        "demand_dir": demand_rel,   # 仓库相对路径，跨机可读
    }
    write_json(wt / ".feature" / "manifest.json", manifest)
    # 把分配记录提交进 feature 分支：既是审计，也让工作区保持干净（便于回收）
    ident_args = ensure_identity(wt)
    git(*ident_args, "add", ".feature/manifest.json", cwd=wt, check=False)
    git(*ident_args, "commit", "-q", "-m", "[BA] 分配 %s → %s" % (req, ident["agent_id"]),
        cwd=wt, check=False)


def cmd_claim(args) -> int:
    root = repo_root()
    ident = resolve_identity(root, role=args.role)
    action = args.action
    aw_init(root)

    if action == "whoami":
        claims = load_claims(root)
        mine = holding_claim(claims, ident["agent_id"])
        print("agent_id  : %s" % ident["agent_id"])
        print("session   : %s" % ident["session_id"])
        print("role      : %s" % ident["role"])
        print("repo      : %s" % root)
        print("holding   : %s" % (mine["req"] if mine else "-"))
        return 0

    if action == "list":
        claims = load_claims(root)
        if not claims:
            print("（无认领）")
            return 0
        rows = []
        for c in claims:
            rows.append([c["req"], c.get("agent_id", "-"), c.get("state", "-"),
                         c.get("worktree", "-"), c.get("claimed_at", "-")[11:19]])
        _table(["REQ", "agent", "state", "worktree", "claimed"], rows)
        return 0

    if action == "next":
        if not getattr(args, "ignore_unread", False):
            unread = _unread_for(root, ident)
            if unread:
                print("UNREAD_MESSAGES %d" % len(unread))
                for m in unread[:5]:
                    print("  %s %s %s" % (m.get("at", ""), m.get("from", ""), m.get("type", "")))
                print("先处理消息：aw.py msg inbox（或让 notifier 读完），再 claim。")
                return 4
        with FileLock(aw_path(root, "locks", "claims.lock")):
            claims = load_claims(root)
            queue = load_queue(root)
            _reap_dead(root, claims, queue)
            claims = load_claims(root)
            mine = holding_claim(claims, ident["agent_id"])
            if mine:
                save_queue(root, queue)
                print("ALREADY_HOLDING %s" % mine["req"])
                return 3
            taken = {c["req"] for c in claims if c.get("state") in CLAIM_STATES}
            candidate = next((q for q in queue if q["req"] not in taken), None)
            if not candidate:
                save_queue(root, queue)
                print("QUEUE_EMPTY")
                return 3
            req = candidate["req"]
            claim = {
                "req": req,
                "title": candidate.get("title", ""),
                "agent_id": ident["agent_id"],
                "session_id": ident["session_id"],
                "worktree": "feature-%s" % req,
                "state": "active",
                "claimed_at": _now(),
            }
            write_json(claim_path(root, req), claim)
            queue = [q for q in queue if q["req"] != req]
            save_queue(root, queue)
        return _finish_claim(root, req, ident)

    if action == "take":
        req = args.req.upper()
        with FileLock(aw_path(root, "locks", "claims.lock")):
            claims = load_claims(root)
            queue = load_queue(root)
            _reap_dead(root, claims, queue)
            claims = load_claims(root)
            mine = holding_claim(claims, ident["agent_id"])
            if mine:
                save_queue(root, queue)
                print("ALREADY_HOLDING %s" % mine["req"])
                return 3
            existing = next((c for c in claims if c["req"] == req and c.get("state") in CLAIM_STATES), None)
            if existing:
                print("TAKEN_BY %s" % existing.get("agent_id", "?"))
                return 3
            claim = {
                "req": req,
                "title": next((q.get("title", "") for q in queue if q["req"] == req), ""),
                "agent_id": ident["agent_id"],
                "session_id": ident["session_id"],
                "worktree": "feature-%s" % req,
                "state": "active",
                "claimed_at": _now(),
            }
            write_json(claim_path(root, req), claim)
            save_queue(root, [q for q in queue if q["req"] != req])
        return _finish_claim(root, req, ident)

    if action == "release":
        req = args.req.upper()
        with FileLock(aw_path(root, "locks", "claims.lock")):
            path = claim_path(root, req)
            claim = read_json(path, None)
            if not claim:
                print("NOT_CLAIMED %s" % req)
                return 3
            if claim.get("agent_id") != ident["agent_id"] and not args.force:
                print("NOT_YOURS %s（属于 %s）" % (req, claim.get("agent_id")))
                return 3
            claim["state"] = "released"
            claim["released_at"] = _now()
            write_json(aw_path(root, "archive", "%s-%s.json" % (req, _dt.datetime.now().strftime("%Y%m%d%H%M%S"))), claim)
            path.unlink(missing_ok=True)
        if args.remove_worktree:
            wt = root / ("feature-%s" % req)
            if wt.exists():
                dirty = git("status", "--porcelain", cwd=wt, check=False).stdout.strip()
                if dirty and not args.force:
                    print("RELEASED %s（worktree 有未提交改动，已保留）" % req)
                    return 0
                git("worktree", "remove", wt.name, cwd=root, check=False)
        print("RELEASED %s" % req)
        return 0

    if action == "doctor":
        claims = load_claims(root)
        queue = load_queue(root)
        sessions = {}
        for p in aw_path(root, "sessions").glob("*.json"):
            data = read_json(p, {})
            if data.get("agent_id"):
                sessions[data["agent_id"]] = data
        problems = []

        by_agent: dict[str, list[dict]] = {}
        for c in claims:
            if c.get("state") in CLAIM_STATES:
                by_agent.setdefault(c.get("agent_id", "?"), []).append(c)
        for agent, items in by_agent.items():
            if len(items) > 1:
                problems.append(("multi-claim", "%s 持有 %s" % (agent, ", ".join(i["req"] for i in items))))

        for c in claims:
            if c.get("state") not in CLAIM_STATES:
                continue
            sess = sessions.get(c.get("agent_id", ""))
            if not _session_alive(sess):
                problems.append(("dead-session", "%s 由已退出的会话占用（%s）" % (c["req"], c.get("agent_id"))))
            wt = root / c.get("worktree", "")
            if not wt.exists():
                problems.append(("missing-worktree", "%s 的 worktree 不存在" % c["req"]))

        registered = {c.get("worktree") for c in claims if c.get("state") in CLAIM_STATES}
        for p in root.iterdir():
            if p.is_dir() and p.name.startswith("feature-REQ-") and p.name not in registered:
                problems.append(("orphan-worktree", "%s 没有对应的认领" % p.name))

        if not problems:
            print("OK 没有发现问题（%d 个认领，%d 个会话）" % (len(claims), len(sessions)))
            return 0
        for kind, detail in problems:
            print("[%s] %s" % (kind, detail))
        if not args.repair:
            print("\n加 --repair 可修复 multi-claim / dead-session / 队列")
            return 1

        with FileLock(aw_path(root, "locks", "claims.lock")):
            claims = load_claims(root)
            queue = load_queue(root)
            fixed = 0
            seen: dict[str, dict] = {}
            for c in sorted(claims, key=lambda x: x.get("claimed_at", "")):
                agent = c.get("agent_id", "?")
                sess = read_json(aw_path(root, "sessions", "%s.json" % agent), {})
                dead = not _session_alive(sess)
                duplicate = agent in seen
                missing_wt = not (root / c.get("worktree", "")).exists()
                if dead or duplicate or missing_wt:
                    reason = "dead-session" if dead else ("multi-claim" if duplicate else "missing-worktree")
                    requeue(root, c, queue, reason)
                    archive_claim(root, c, reason)
                    fixed += 1
                else:
                    seen[agent] = c
            save_queue(root, queue)
        print("已修复 %d 项" % fixed)
        return 0

    raise GitError("未知 claim 动作: %s" % action)


def _finish_claim(root: Path, req: str, ident: dict) -> int:
    base = "develop"
    try:
        _create_worktree(root, req, base)
        _write_manifest(root, req, ident)
    except (GitError, OSError) as exc:
        queue = load_queue(root)
        claim = read_json(claim_path(root, req), None)
        if claim:
            claim["_path"] = str(claim_path(root, req))
            requeue(root, claim, queue, "rollback")
            archive_claim(root, claim, "worktree-failed")
        save_queue(root, queue)
        print("CLAIM_FAILED %s: %s" % (req, exc))
        return 1
    print("CLAIMED %s" % req)
    print("  agent   : %s" % ident["agent_id"])
    print("  worktree: %s" % (root / ("feature-%s" % req)))
    print("  branch  : feature/%s" % req)
    return 0


def cmd_agent(args) -> int:
    root = repo_root()
    aw_init(root)
    action = args.action or "whoami"
    anchor = terminal_anchor()
    key = _binding_key(anchor) if anchor else ""

    if action == "roster":
        agents = load_roster(root)
        if not agents:
            print("（roster 为空；用 aw.py agent register <name> 注册）")
            return 0
        payload = []
        for a in sorted(agents, key=lambda x: x["id"]):
            sess = read_json(aw_path(root, "sessions", "%s.json" % a["id"]), {})
            payload.append({
                "id": a["id"],
                "role": a.get("role", "ba"),
                "status": a.get("status", "active"),
                "host": a.get("host", ""),
                "session_alive": bool(_session_alive(sess)),
            })
        if getattr(args, "json", False):
            print(json.dumps({"agents": payload}, ensure_ascii=False, indent=2))
        else:
            _table(["agent", "role", "status", "host", "session"],
                   [[x["id"], x["role"], x["status"], x["host"] or "-",
                     "alive" if x["session_alive"] else "-"] for x in payload])
        return 0

    if action in ("register", "activate", "deactivate"):
        cwd = Path.cwd().resolve()
        ba = (root / "BA").resolve()
        allowed = cwd == root.resolve() or cwd == ba or ba in cwd.parents
        if not allowed:
            print("请在仓库根或 BA/ 下执行（roster 属于 demand 分支）", file=sys.stderr)
            return 2
        name = (args.name or "").strip()
        if not name:
            print("用法: aw.py agent %s <name>" % action, file=sys.stderr)
            return 2
        agents = load_roster(root)
        by_id = {a["id"]: a for a in agents}
        if action == "register":
            entry = by_id.get(name) or {"id": name, "registered_at": _now()}
            entry["role"] = args.role or entry.get("role", "ba")
            entry["host"] = args.host or entry.get("host", socket.gethostname())
            entry["status"] = "active"
            entry["updated_at"] = _now()
            if name not in by_id:
                agents.append(entry)
            save_roster(root, agents)
            print("REGISTERED %s (%s)" % (name, entry["role"]))
            return 0
        if name not in by_id:
            print("未注册的 agent: %s" % name, file=sys.stderr)
            return 3
        by_id[name]["status"] = "active" if action == "activate" else "inactive"
        by_id[name]["updated_at"] = _now()
        save_roster(root, agents)
        print("%s %s" % ("ACTIVE" if action == "activate" else "INACTIVE", name))
        return 0

    if action == "publish":
        ba = root / "BA"
        if not ba.is_dir():
            print("找不到 BA/ 工作区", file=sys.stderr)
            return 2
        rel = "plan/agents.json"
        if not (ba / rel).exists():
            print("名册不存在：先 agent register", file=sys.stderr)
            return 3
        dirty = git("status", "--porcelain", rel, cwd=ba, check=False).stdout.strip()
        if not dirty:
            print("NO_CHANGES")
            return 0
        git("add", rel, cwd=ba)
        ident_args = ensure_identity(ba)
        git(*ident_args, "commit", "-q", "-m", args.message or "[BA] 更新 agent 名册", cwd=ba)
        if not _has_remote(ba):
            print("COMMITTED_LOCAL")
            return 0
        for attempt in range(3):
            pushed = git("push", "-q", "origin", "demand", cwd=ba, check=False, timeout=30)
            if pushed.returncode == 0:
                print("PUBLISHED")
                return 0
            git("pull", "--rebase", "-q", "origin", "demand", cwd=ba, check=False, timeout=30)
            time.sleep(0.5 * (2 ** attempt))
        print("PUSH_FAILED（本地已提交，稍后重试 push）", file=sys.stderr)
        return 3

    if action == "exit":
        ident = resolve_identity(root)
        claims = [c for c in load_claims(root)
                  if c.get("agent_id") == ident["agent_id"] and c.get("state") in CLAIM_STATES]
        if claims and not args.force:
            print("还有认领未释放: %s" % ", ".join(c["req"] for c in claims), file=sys.stderr)
            print("先 claim release，或加 --force 强制退出（认领会变成死会话）", file=sys.stderr)
            return 3
        sess_path = aw_path(root, "sessions", "%s.json" % ident["agent_id"])
        sess = read_json(sess_path, {})
        sess["status"] = "offline"
        sess["ended_at"] = _now()
        write_json(sess_path, sess)
        if not args.keep_binding and key:
            bindings = load_bindings(root)
            bindings.pop(key, None)
            save_bindings(root, bindings)
        print("EXITED %s" % ident["agent_id"])
        print("  claims : %d" % len(claims))
        print("  binding: %s" % ("kept" if args.keep_binding else ("removed" if key else "-")))
        return 0

    if action in ("bind", "unbind"):
        if not anchor:
            print("当前环境没有终端锚点（WT_SESSION / TERM_SESSION_ID / TTY），只能用 --agent。",
                  file=sys.stderr)
            return 2
        if action == "bind":
            name = (args.name or "").strip()
            if not name:
                print("用法: aw.py agent bind <name> [--force]", file=sys.stderr)
                return 2
            ok, old = bind_identity(root, key, name, force=args.force)
            if not ok:
                print("这个终端已经绑定 %s；要改绑加 --force" % old, file=sys.stderr)
                return 3
            print("BOUND %s" % name)
            print("  anchor: %s" % anchor)
            return 0
        bindings = load_bindings(root)
        bindings.pop(key, None)
        save_bindings(root, bindings)
        print("UNBOUND %s" % anchor)
        return 0

    ident = resolve_identity(root)
    reg = next((a for a in load_roster(root) if a["id"] == ident["agent_id"]), None)
    print("agent_id : %s" % ident["agent_id"])
    print("session  : %s" % ident["session_id"])
    print("role     : %s" % ident["role"])
    print("repo     : %s" % root)
    print("source   : %s" % ident.get("source", "unknown"))
    print("anchor   : %s" % (anchor or "（无终端锚点）"))
    print("roster   : %s" % (reg.get("status", "active") if reg else "未注册"))
    return 0


def cmd_queue(args) -> int:
    root = repo_root()
    aw_init(root)
    queue = load_queue(root)
    if args.action == "list":
        if not queue:
            print("（队列为空）")
            return 0
        _table(["REQ", "title", "added"], [[q["req"], q.get("title", ""), q.get("added_at", "")[:10]] for q in queue])
        return 0
    if args.action == "add":
        req = args.req.upper()
        if any(q["req"] == req for q in queue):
            print("ALREADY_QUEUED %s" % req)
            return 3
        queue.append({"req": req, "title": args.title or "", "added_at": _now(), "source": "manual"})
        save_queue(root, queue)
        print("QUEUED %s" % req)
        return 0
    if args.action == "sync":
        demands = root / "BA" / "demands"
        added = 0
        existing = {q["req"] for q in queue}
        claims = {c["req"] for c in load_claims(root) if c.get("state") in CLAIM_STATES}
        if demands.is_dir():
            for d in sorted(demands.iterdir()):
                if not d.is_dir() or not d.name.startswith("REQ-"):
                    continue
                req = d.name.split("-", 1)[0] + "-" + d.name.split("-")[1] if d.name.count("-") >= 1 else d.name
                status = d / "status.md"
                text = status.read_text(encoding="utf-8") if status.exists() else ""
                if "已就绪" not in text:
                    continue
                if req in existing or req in claims:
                    continue
                queue.append({"req": req, "title": d.name, "added_at": _now(), "source": "demands"})
                existing.add(req)
                added += 1
        save_queue(root, queue)
        print("SYNCED %d（队列共 %d）" % (added, len(queue)))
        return 0
    raise GitError("未知 queue 动作: %s" % args.action)


# ---------------------------------------------------------------- msg bus
#
# 统一消息通道：空的 bus 分支 + 空 commit，消息体就是 commit message。
# - 不 checkout、不碰工作区：用 commit-tree 直接造 commit
# - 永不 rebase / force：冲突时基于最新 origin/bus 重放本地队列
# - 离线可用：先落 .aw/outbox/，flush 时再推

BUS_BRANCH = "bus"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
MSG_TYPES = ("fyi", "question", "blocker", "handoff", "contract-change", "contract-ack", "decision")


def _now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _msg_id() -> str:
    return secrets.token_hex(4)


ABS_PATH_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9+.-])[A-Za-z]:[\\/]"),   # C:\ 或 C:/（不误伤 https://）
    re.compile(r"^\\\\"),                             # UNC \\server\share
    re.compile(r"(?<![A-Za-z0-9:.])/(?:Users|home|root|mnt)/"),  # /Users/x /home/x
)


def _has_abs_path(text: str) -> bool:
    return any(p.search(text or "") for p in ABS_PATH_PATTERNS)


def normalize_ref(ref: str) -> str:
    """ref 必须是仓库相对路径；拒绝本机绝对路径，统一用 /。"""
    value = (ref or "").strip().replace("\\", "/")
    if not value:
        return ""
    value = re.sub(r"^<repo-root>/", "", value)
    value = re.sub(r"^\./", "", value)
    if _has_abs_path(value) or value.startswith("/"):
        raise GitError(
            "ref 不能是本机绝对路径（跨机器不可读，也会泄露目录结构）。\n"
            "请改成仓库相对路径，例如：BA/contracts/user-api/v3.md"
        )
    if value.startswith("../"):
        raise GitError("ref 请用仓库相对路径（如 BA/contracts/x.md），不要用 ../ 回到仓库根。")
    return value


def parse_message(text: str) -> dict | None:
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[0].startswith("[msg]"):
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return None
    meta: dict = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value
    meta["body"] = "\n".join(lines[end + 1:]).strip()
    return meta


def render_message(meta: dict) -> str:
    to = meta.get("to") or []
    cc = meta.get("cc") or []
    subject = (meta.get("subject") or "").strip()
    head = [
        "[msg] %s%s -> %s" % (meta.get("type", "fyi"),
                              (" " + subject) if subject else "",
                              ", ".join(to) or "-"),
        "",
        "---",
        "id: %s" % meta["id"],
        "from: %s" % meta["from"],
        "to: [%s]" % ", ".join(to),
    ]
    if cc:
        head.append("cc: [%s]" % ", ".join(cc))
    head.append("at: %s" % meta["at"])
    head.append("type: %s" % meta["type"])
    for key in ("ref", "contract", "version", "deadline", "thread", "priority", "re", "result"):
        if meta.get(key):
            head.append("%s: %s" % (key, meta[key]))
    head += ["---", meta.get("body", "")]
    return "\n".join(head) + "\n"


def _bus_fetch(root: Path) -> None:
    try:
        git("fetch", "-q", "origin", BUS_BRANCH, cwd=root, check=False, timeout=20)
    except GitError:
        pass  # 离线/远端不可达：读本地已有 bus


def _bus_tip(root: Path) -> str | None:
    for ref in ("refs/remotes/origin/%s" % BUS_BRANCH, "refs/heads/%s" % BUS_BRANCH):
        sha = git("rev-parse", "-q", "--verify", ref, cwd=root, check=False).stdout.strip()
        if sha:
            return sha
    return None


def _has_remote(root: Path) -> bool:
    return bool(git("remote", cwd=root, check=False).stdout.strip())


def _commit_message(root: Path, text: str, parent: str | None, at: str) -> str:
    aw_init(root)
    tmp = aw_path(root, "outbox", ".tmp-msg")
    write_text(tmp, text)
    env = dict(os.environ)
    if at:
        env["GIT_AUTHOR_DATE"] = at
        env["GIT_COMMITTER_DATE"] = at
    args = ["commit-tree", EMPTY_TREE]
    if parent:
        args += ["-p", parent]
    args += ["-F", str(tmp)]
    proc = subprocess.run(["git", "-c", "core.quotepath=false", *ensure_identity(root), *args],
                          cwd=str(root), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    tmp.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise GitError("commit-tree 失败: %s" % proc.stderr.strip())
    return proc.stdout.strip()


def bus_flush(root: Path, quiet: bool = False) -> str:
    """把 outbox 里的消息按顺序重放到 bus 上并推送。返回 ok / queued / local。"""
    outbox = aw_path(root, "outbox")
    outbox.mkdir(parents=True, exist_ok=True)
    pending = sorted(p for p in outbox.glob("*.md"))
    if not pending:
        return "ok"
    if not _has_remote(root):
        base = _bus_tip(root)
        for path in pending:
            meta = parse_message(path.read_text(encoding="utf-8")) or {}
            base = _commit_message(root, path.read_text(encoding="utf-8"), base, meta.get("at", ""))
            path.unlink(missing_ok=True)
        git("update-ref", "refs/heads/%s" % BUS_BRANCH, base, cwd=root, check=False)
        return "local"

    for attempt in range(4):
        try:
            _bus_fetch(root)
            base = _bus_tip(root)
            created = base
            for path in pending:
                text = path.read_text(encoding="utf-8")
                meta = parse_message(text) or {}
                created = _commit_message(root, text, created, meta.get("at", ""))
            git("update-ref", "refs/heads/%s" % BUS_BRANCH, created, cwd=root, check=False)
            pushed = git("push", "-q", "origin", "%s:%s" % (BUS_BRANCH, BUS_BRANCH),
                         cwd=root, check=False, timeout=30)
            if pushed.returncode == 0:
                for path in pending:
                    path.unlink(missing_ok=True)
                return "ok"
        except (GitError, OSError):
            pass
        time.sleep(0.4 * (2 ** attempt))
    if not quiet:
        print("推送失败，消息已排队（下次 send/inbox 会自动重试）", file=sys.stderr)
    return "queued"


def _bus_ref(root: Path) -> str | None:
    for ref in ("refs/remotes/origin/%s" % BUS_BRANCH, "refs/heads/%s" % BUS_BRANCH):
        if git("rev-parse", "-q", "--verify", ref, cwd=root, check=False).returncode == 0:
            return ref.replace("refs/remotes/", "").replace("refs/heads/", "")
    return None


def load_bus_messages(root: Path, fetch: bool = True) -> list[dict]:
    if fetch:
        _bus_fetch(root)
    ref = _bus_ref(root)
    if not ref:
        return []
    out = git("log", ref, "--format=%H%x1f%B%x1f", cwd=root, check=False).stdout
    chunks = out.split("\x1f")
    messages = []
    for i in range(0, len(chunks) - 1, 2):
        sha = chunks[i].strip().splitlines()[-1] if chunks[i].strip() else ""
        text = chunks[i + 1]
        meta = parse_message(text)
        if meta and meta.get("id"):
            meta["_sha"] = sha
            messages.append(meta)
    # git log 是「新 → 旧」，反转成「旧 → 新」：消息顺序等于提交顺序，不受时钟影响
    messages.reverse()
    for idx, meta in enumerate(messages):
        meta["_seq"] = idx
    return messages


def _is_mine(meta: dict, ident: dict) -> str | None:
    to = meta.get("to") or []
    cc = meta.get("cc") or []
    tokens = {"all", "role:%s" % ident.get("role", "ba"), ident["agent_id"]}
    if tokens & set(to):
        return "to"
    if tokens & set(cc):
        return "cc"
    return None


def _fmt_recipient(meta: dict, ident: dict) -> str:
    kind = _is_mine(meta, ident)
    if kind == "to":
        return "me"
    if kind == "cc":
        return "me(cc)"
    to = ", ".join(meta.get("to") or [])
    return to or "-"


def _msg_line(meta: dict, ident: dict, full: bool = False) -> str:
    who = _fmt_recipient(meta, ident)
    label = "→ %-12s" % who
    extra = meta.get("contract", "")
    if meta.get("version"):
        extra += "@%s" % meta["version"]
    line = "%s %-20s %-14s %-18s %s" % (
        (meta.get("at") or "")[:19], meta.get("from", "?"), label,
        meta.get("type", "?"), extra)
    if full:
        line += "\n    id=%s ref=%s\n    %s" % (
            meta.get("id"), meta.get("ref", "-"), meta.get("body", "").replace("\n", "\n    "))
    return line


def _read_ids(root: Path, agent_id: str, messages: list[dict]) -> set[str]:
    """已读集合（按消息 id，而不是时间戳）。

    旧版本用 (at, id) 游标，会被"更早时间戳、更晚到达"的消息绕过导致丢消息；
    这里在首次读取时把旧游标转换成等价 id 集合，保持向后兼容。
    """
    path = aw_path(root, "msg-read", "%s.json" % agent_id)
    if path.exists():
        return set(read_json(path, {}).get("ids") or [])
    at, mid = _read_cursor(root, agent_id)
    migrated: set[str] = set()
    if at or mid:
        for m in messages:
            if (m.get("at", ""), m.get("id", "")) <= (at, mid) and m.get("id"):
                migrated.add(m["id"])
        _write_read_ids(root, agent_id, migrated, {m.get("id") for m in messages if m.get("id")})
    return migrated


def _write_read_ids(root: Path, agent_id: str, ids: set[str], universe: set[str]) -> None:
    path = aw_path(root, "msg-read", "%s.json" % agent_id)
    with FileLock(aw_path(root, "locks", "msg-read.lock")):
        current = set(read_json(path, {}).get("ids") or [])
        keep = (current & universe) if universe else current
        merged = keep | set(ids)
        write_json(path, {"ids": sorted(merged), "updated_at": _now()})


def _unread_for(root: Path, ident: dict) -> list[dict]:
    messages = [m for m in load_bus_messages(root) if _is_mine(m, ident)]
    read = _read_ids(root, ident["agent_id"], messages)
    return [m for m in messages if m.get("id") not in read]


def _read_cursor(root: Path, agent_id: str) -> tuple[str, str]:
    data = read_json(aw_path(root, "msg-cursor.json"), {})
    entry = data.get(agent_id, {})
    return entry.get("at", ""), entry.get("id", "")


def _write_cursor(root: Path, agent_id: str, at: str, mid: str) -> None:
    path = aw_path(root, "msg-cursor.json")
    data = read_json(path, {})
    data[agent_id] = {"at": at, "id": mid}
    write_json(path, data)


def cmd_msg(args) -> int:
    root = repo_root()
    ident = resolve_identity(root)
    aw_init(root)
    action = args.action

    if action == "send":
        to = [t.strip() for t in (args.to or "").split(",") if t.strip()]
        cc = [t.strip() for t in (args.cc or "").split(",") if t.strip()]
        if not to:
            raise GitError("--to 不能为空（可以是 all / role:ba / agent_id）")
        if args.type not in MSG_TYPES:
            raise GitError("type 必须是: %s" % ", ".join(MSG_TYPES))
        body = (args.body or "").strip()
        if not body:
            raise GitError("--body 不能为空")
        if len(body) > 2000:
            raise GitError("body 超过 2000 字符，请把正文放进 BA/contracts/ 或 BA/decisions/")
        ref = normalize_ref(args.ref)
        if _has_abs_path(body):
            raise GitError(
                "消息正文里不要放本机绝对路径（跨机器不可读，也会泄露目录结构）。\n"
                "用仓库相对路径，例如：BA/contracts/user-api/v3.md"
            )
        validate_recipients(root, to, cc, force=getattr(args, "force", False))
        roster = load_roster(root)
        if roster and not getattr(args, "force", False):
            me = next((a for a in roster if a["id"] == ident["agent_id"]), None)
            if not me:
                raise GitError("发送者未注册: %s（先 aw.py agent register）" % ident["agent_id"])
            if me.get("status") != "active":
                raise GitError("发送者不是 active: %s" % ident["agent_id"])
        meta = {
            "id": _msg_id(), "from": ident["agent_id"], "to": to, "cc": cc,
            "at": _now_utc(), "type": args.type, "body": body,
            "ref": ref, "contract": args.contract or "",
            "version": args.version or "", "deadline": args.deadline or "",
            "thread": args.thread or "", "priority": args.priority or "p2",
            "subject": args.subject or (args.contract or ""),
        }
        text = render_message(meta)
        path = aw_path(root, "outbox", "%s-%s.md" % (meta["at"].replace(":", "").replace("-", ""), meta["id"]))
        write_text(path, text)
        state = bus_flush(root)
        if state == "ok":
            print("SENT %s" % meta["id"])
        elif state == "local":
            print("SENT_LOCAL %s（仓库没有 remote，消息只在本地 bus 上）" % meta["id"])
        else:
            print("QUEUED %s" % meta["id"])
        return 0 if state == "ok" else (0 if state == "local" else 3)

    if action == "flush":
        state = bus_flush(root)
        print("FLUSH %s" % state)
        return 0 if state in ("ok", "local") else 3

    if action in ("inbox", "list"):
        messages = load_bus_messages(root, fetch=not args.no_fetch)
        if not args.all:
            messages = [m for m in messages if _is_mine(m, ident)]
        if args.sender:
            messages = [m for m in messages if m.get("from") == args.sender]
        if args.since:
            messages = [m for m in messages if (m.get("at") or "") >= args.since]
        messages.sort(key=lambda m: m.get("_seq", 0))
        universe = {m.get("id") for m in messages if m.get("id")}
        if action == "inbox" and not args.all:
            read = _read_ids(root, ident["agent_id"], messages)
            messages = [m for m in messages if m.get("id") not in read]
            if args.limit:
                # 未读时取最旧的 N 条，避免"只显示最新、旧的被永久跳过"
                show = messages[:args.limit]
            else:
                show = messages
        else:
            show = messages[-args.limit:] if args.limit else messages
        if args.json:
            fields = ("id", "from", "to", "cc", "at", "type", "subject", "contract",
                      "version", "ref", "deadline", "thread", "priority", "re", "result", "body")
            payload = [{k: m.get(k) for k in fields if m.get(k)} for m in show]
            print(json.dumps({"count": len(payload), "messages": payload},
                             ensure_ascii=False, indent=2))
        else:
            if not show:
                print("（无消息）")
            for meta in show:
                print(_msg_line(meta, ident, full=args.full))
        if show and action == "inbox" and not args.no_advance and not args.all:
            _write_read_ids(root, ident["agent_id"],
                            {m["id"] for m in show if m.get("id")}, universe)
        return 0

    if action == "wait":
        deadline = time.time() + max(1, int(args.timeout))
        interval = max(1, int(args.interval))
        while True:
            candidates = _unread_for(root, ident)
            if args.thread:
                candidates = [m for m in candidates if m.get("thread") == args.thread]
            if args.contract:
                candidates = [m for m in candidates if m.get("contract") == args.contract]
            if args.type:
                candidates = [m for m in candidates if m.get("type") == args.type]
            if args.sender:
                candidates = [m for m in candidates if m.get("from") == args.sender]
            if candidates:
                if args.json:
                    fields = ("id", "from", "to", "at", "type", "subject", "contract",
                              "version", "ref", "thread", "body")
                    print(json.dumps({"found": True, "count": len(candidates),
                                      "messages": [{k: m.get(k) for k in fields if m.get(k)}
                                                   for m in candidates]},
                                     ensure_ascii=False, indent=2))
                else:
                    for m in candidates:
                        print(_msg_line(m, ident, full=True))
                if args.consume:
                    _write_read_ids(root, ident["agent_id"],
                                    {m["id"] for m in candidates if m.get("id")},
                                    {m["id"] for m in load_bus_messages(root, fetch=False) if m.get("id")})
                return 0
            remaining = deadline - time.time()
            if remaining <= 0:
                if args.json:
                    print(json.dumps({"found": False, "count": 0, "messages": []},
                                     ensure_ascii=False))
                else:
                    print("WAIT_TIMEOUT")
                return 3
            time.sleep(min(interval, remaining))

    if action == "show":
        target = next((m for m in load_bus_messages(root, fetch=not args.no_fetch)
                       if m.get("id") == args.id), None)
        if not target:
            print("NOT_FOUND %s" % args.id)
            return 3
        print(json.dumps(target, ensure_ascii=False, indent=2))
        return 0

    if action == "ack":
        target = next((m for m in load_bus_messages(root) if m.get("id") == args.id), None)
        if not target:
            print("NOT_FOUND %s" % args.id)
            return 3
        ok = args.ok or not args.reject
        body = args.note or ("同意" if ok else "不同意")
        meta = {
            "id": _msg_id(), "from": ident["agent_id"], "to": [target.get("from", "")],
            "cc": target.get("cc") or [], "at": _now_utc(), "type": "contract-ack",
            "body": body, "re": target.get("id"), "result": "ok" if ok else "no",
            "contract": target.get("contract", ""), "version": target.get("version", ""),
            "subject": "ack %s" % target.get("id"),
        }
        text = render_message(meta)
        path = aw_path(root, "outbox", "%s-%s.md" % (meta["at"].replace(":", "").replace("-", ""), meta["id"]))
        write_text(path, text)
        state = bus_flush(root)
        print("ACK %s -> %s %s" % (meta["id"], target.get("id"), "ok" if ok else "no"))
        return 0 if state == "ok" else 3

    raise GitError("未知 msg 动作: %s" % action)


# ---------------------------------------------------------------- mcp setup

MCP_SERVER = Path(__file__).resolve().parent / "aw_mcp.py"


def _mcp_candidates(root: Path) -> list[tuple[str, Path]]:
    home = Path.home()
    appdata = os.environ.get("APPDATA")
    items: list[tuple[str, Path]] = []
    if appdata:
        items.append(("claude", Path(appdata) / "Claude" / "claude_desktop_config.json"))
    items.append(("claude", home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"))
    items.append(("claude", home / ".config" / "Claude" / "claude_desktop_config.json"))
    items.append(("cursor", home / ".cursor" / "mcp.json"))
    items.append(("cursor", root / ".cursor" / "mcp.json"))
    items.append(("claude-code", root / ".mcp.json"))
    items.append(("vscode", root / ".vscode" / "mcp.json"))
    return items


def _mcp_config_key(client: str) -> str:
    return "servers" if client == "vscode" else "mcpServers"


def _mcp_wrapper(root: Path) -> Path:
    folder = aw_path(root, "mcp")
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path = folder / "aw-mcp.cmd"
        content = '@echo off\r\ncd /d "%s"\r\n"%s" "%s" %%*\r\n' % (root, sys.executable, MCP_SERVER)
    else:
        path = folder / "aw-mcp.sh"
        content = '#!/bin/sh\ncd "%s" && exec "%s" "%s" "$@"\n' % (root, sys.executable, MCP_SERVER)
    write_text(path, content)
    if os.name != "nt":
        try:
            os.chmod(path, 0o755)
        except OSError:
            pass
    return path


def _mcp_entry(client: str, wrapper: Path) -> dict:
    entry = {"command": str(wrapper), "args": []}
    if client == "vscode":
        entry = {"type": "stdio", **entry}
    return entry


def _install_mcp(client: str, path: Path, root: Path, dry_run: bool = False) -> dict:
    key = _mcp_config_key(client)
    wrapper = _mcp_wrapper(root)
    entry = _mcp_entry(client, wrapper)
    data = read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    servers = data.get(key)
    if not isinstance(servers, dict):
        servers = {}
    had = "aw" in servers
    unchanged = servers.get("aw") == entry
    servers["aw"] = entry
    data[key] = servers
    if not dry_run and not unchanged:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup = path.with_name(path.name + ".bak-" + _dt.datetime.now().strftime("%Y%m%d%H%M%S"))
            shutil.copy2(path, backup)
        write_json(path, data)
    return {"client": client, "path": str(path), "key": key, "replaced": had,
            "unchanged": unchanged, "wrapper": str(wrapper)}


def cmd_mcp(args) -> int:
    root = repo_root()
    aw_init(root)
    action = args.action

    if action == "print":
        wrapper = _mcp_wrapper(root)
        print(json.dumps({"mcpServers": {"aw": _mcp_entry("claude", wrapper)}},
                         ensure_ascii=False, indent=2))
        print("\n# 把 cwd 设成 %s，或直接使用上面的 wrapper" % root, file=sys.stderr)
        return 0

    if action == "status":
        rows = []
        for client, path in _mcp_candidates(root):
            data = read_json(path, {}) if path.exists() else {}
            servers = data.get(_mcp_config_key(client)) if isinstance(data, dict) else {}
            has = isinstance(servers, dict) and "aw" in servers
            rows.append({"client": client, "path": str(path),
                         "exists": path.exists(), "installed": has})
        if args.json:
            print(json.dumps({"root": str(root), "candidates": rows}, ensure_ascii=False, indent=2))
        else:
            _table(["client", "exists", "installed", "path"],
                   [[r["client"], "yes" if r["exists"] else "-",
                     "yes" if r["installed"] else "-", r["path"]] for r in rows])
        return 0

    # install / ensure
    client = args.client or "auto"
    path: Path | None = Path(args.path).expanduser().resolve() if args.path else None

    if path is None:
        candidates = _mcp_candidates(root)
        if client != "auto":
            candidates = [(c, p) for c, p in candidates if c == client]
        existing = [(c, p) for c, p in candidates if p.exists()]
        if existing:
            client, path = existing[0]
        elif client != "auto" and candidates:
            # 显式客户端：允许创建配置（父目录一起创建）
            client, path = candidates[0]
        else:
            print("没有检测到已存在的 MCP 客户端配置。\n"
                  "请显式指定，例如：\n"
                  "  aw.py mcp install --client cursor --path ~/.cursor/mcp.json\n"
                  "  aw.py mcp install --client claude", file=sys.stderr)
            return 3

    result = _install_mcp(client, path, root, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["unchanged"] and not args.dry_run:
            print("ALREADY INSTALLED %s" % path)
            print("  wrapper: %s" % result["wrapper"])
            return 0
        verb = "WOULD INSTALL" if args.dry_run else "INSTALLED"
        print("%s %s" % (verb, path))
        print("  client : %s" % client)
        print("  key    : %s" % result["key"])
        print("  wrapper: %s" % result["wrapper"])
        print("\n重启客户端后 MCP 工具才会出现；环境里需要带 AW_AGENT_ID。")
    return 0
# ---------------------------------------------------------------- contract check

def _ver_num(value) -> int:
    return int(re.sub(r"[^0-9]", "", str(value)) or 0)


def _parse_contract_file(path: Path | None) -> dict:
    meta: dict = {"consumers": []}
    if path is None or not path.exists():
        return meta
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.match(r"^\s*-\s*([A-Za-z_]+)\s*:\s*(.+?)\s*$", line)
        if not m:
            continue
        key, value = m.group(1).lower(), m.group(2).strip()
        if key in ("consumers", "cc"):
            inner = value[1:-1] if value.startswith("[") and value.endswith("]") else value
            meta[key] = [v.strip() for v in inner.split(",") if v.strip()]
        else:
            meta[key] = value
    return meta


def load_contracts(root: Path) -> list[dict]:
    base = root / "BA" / "contracts"
    if not base.is_dir():
        return []
    contracts = []
    for folder in sorted(base.iterdir()):
        if not folder.is_dir():
            continue
        versions = {_ver_num(p.stem): p for p in folder.glob("v*.md")}
        entry = {"name": folder.name, "versions": versions, "meta": {"consumers": []}}
        current_file = folder / "CURRENT"
        if not current_file.exists():
            entry["error"] = "缺 CURRENT 文件"
            contracts.append(entry)
            continue
        current = _ver_num(current_file.read_text(encoding="utf-8", errors="ignore").strip())
        entry["current"] = current
        if current not in versions:
            entry["error"] = "CURRENT=v%d 但 v%d.md 不存在" % (current, current)
        entry["meta"] = _parse_contract_file(versions.get(current))
        contracts.append(entry)
    return contracts


def load_feature_pins(root: Path) -> list[dict]:
    features = []
    for e in worktrees(root):
        if not e["path"].name.startswith("feature-") or not e["path"].exists():
            continue
        manifest = e["path"] / ".feature" / "manifest.json"
        data = read_json(manifest, {}) if manifest.exists() else {}
        pins = data.get("contracts") or {}
        features.append({
            "name": e["path"].name,
            "agent_id": data.get("agent_id", ""),
            "pins": {str(k): _ver_num(v) for k, v in pins.items()},
            "has_manifest": manifest.exists(),
        })
    return features


def _contract_acks(root: Path, fetch: bool) -> list[dict]:
    return [m for m in load_bus_messages(root, fetch=fetch) if m.get("type") == "contract-ack"]


def cmd_contract(args) -> int:
    root = repo_root()
    contracts = load_contracts(root)
    if not contracts:
        print("未启用契约管理（BA/contracts/ 不存在或为空）")
        return 0

    features = load_feature_pins(root)
    messages = load_bus_messages(root, fetch=not args.no_fetch)
    acks = [m for m in messages if m.get("type") == "contract-ack"]
    changes = [m for m in messages if m.get("type") == "contract-change"]

    fails, warns, rows = [], [], []
    now = _dt.datetime.now(_dt.timezone.utc)

    for c in contracts:
        name = c["name"]
        current = c.get("current")
        consumers = c.get("meta", {}).get("consumers", [])
        if c.get("error"):
            fails.append("%s: %s" % (name, c["error"]))
        pinning = []
        for f in features:
            if name in f["pins"]:
                pinning.append("%s(v%d)" % (f["name"], f["pins"][name]))
                if current and f["pins"][name] < current:
                    fails.append("%s: %s pin v%d < current v%d" % (name, f["name"], f["pins"][name], current))
                elif current and f["pins"][name] > current:
                    fails.append("%s: %s pin v%d > current v%d（版本超前）" % (name, f["name"], f["pins"][name], current))
        for f in features:
            if f["agent_id"] and f["agent_id"] in consumers and name not in f["pins"]:
                fails.append("%s: %s 的消费者 %s 未在 manifest 里 pin 该契约" % (name, f["name"], f["agent_id"]))
        if not consumers:
            warns.append("%s: 未声明 consumers，无法判断谁需要确认" % name)
        rows.append([name, "v%s" % current if current else "?", ", ".join(consumers) or "-",
                     ", ".join(pinning) or "-"])

        latest_change = next((m for m in reversed(changes)
                              if m.get("contract") == name
                              and (not current or _ver_num(m.get("version", 0)) == current)), None)
        # changes 是「旧 → 新」，reversed 后第一个匹配即最新一次变更
        if latest_change:
            acked = {m.get("from") for m in acks
                     if m.get("contract") == name
                     and _ver_num(m.get("version", 0)) == _ver_num(latest_change.get("version", 0))}
            missing = [x for x in consumers if x not in acked]
            if missing:
                deadline = latest_change.get("deadline") or ""
                overdue = False
                if deadline:
                    try:
                        overdue = _dt.datetime.fromisoformat(deadline.replace("Z", "+00:00")) < now
                    except ValueError:
                        overdue = False
                msg = "%s v%s 等待 ack: %s" % (name, latest_change.get("version"), ", ".join(missing))
                (fails if overdue else warns).append(msg)

    if args.json:
        print(json.dumps({"contracts": rows, "fails": fails, "warns": warns},
                         ensure_ascii=False, indent=2))
    else:
        print("契约检查  （%s）" % root)
        if rows:
            _table(["契约", "current", "consumers", "已 pin 的 feature"], rows)
        for item in fails:
            print("[FAIL] %s" % item)
        for item in warns:
            print("[WARN] %s" % item)
        print("\n结论: %d FAIL / %d WARN" % (len(fails), len(warns)))

    if fails:
        return 1
    if args.strict and warns:
        return 1
    return 0


# ---------------------------------------------------------------- upgrade (只读检查)

REMOVED_REFS = {
    "worktree-audit.md": "references/lifecycle/audit.md",
    "worktree-cleanup.md": "references/lifecycle/cleanup.md",
}


def skill_version(path: Path | None = None) -> str:
    target = path or (SKILL_DIR / "SKILL.md")
    try:
        text = target.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "unknown"
    m = re.search(r"(?m)^\s*version:\s*(\S+)\s*$", text)
    return m.group(1) if m else "unknown"


def _scan_refs(root: Path, limit: int = 600) -> list[tuple[str, str, str]]:
    skip = {".git", "node_modules", ".local", "dist", "build", ".venv", "__pycache__", ".aw"}
    hits, seen = [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for name in filenames:
            if not name.endswith((".md", ".txt", ".yaml", ".yml")):
                continue
            seen += 1
            if seen > limit:
                return hits
            path = Path(dirpath) / name
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for old, new in REMOVED_REFS.items():
                if old in text:
                    hits.append((str(path.relative_to(root)), old, new))
    return hits


def cmd_upgrade(args) -> int:
    root = repo_root()
    installed = skill_version()
    add, clean, adjust = [], [], []

    if not (root / "code").is_dir() and branch_of(root) != "workspace":
        print("当前目录不是 workspace 项目，upgrade 不适用: %s" % root, file=sys.stderr)
        return 2

    # 1. 布局
    if branch_of(root) != "workspace":
        adjust.append(("根分支", "当前 %s，应为 workspace" % branch_of(root), "git checkout workspace"))
    files = sorted(p for p in git_out("ls-files", cwd=root).splitlines() if p)
    if files != sorted(ROOT_FILES):
        extra = [f for f in files if f not in ROOT_FILES]
        adjust.append(("根容器跟踪文件", "多余 %d 项: %s" % (len(extra), ", ".join(extra[:5])),
                       "git rm -r --cached <path> 后提交 [Workspace] cleanup"))

    wt = worktrees(root)
    for e in wt:
        if e["path"] == root:
            continue
        if not e["path"].exists() or e.get("prunable"):
            clean.append(("失效 worktree", str(e["path"]), "git worktree prune"))
        elif e["path"].parent != root:
            clean.append(("worktree 位置违规", str(e["path"]), "移到仓库根下一层后 git worktree repair"))

    if (root / "workspaces").exists():
        clean.append(("中间目录 workspaces/", "违反平铺约束", "清空后删除目录，worktree 重建到仓库根"))

    # 2. 补 bootstrap
    bootstrap = [
        ("BA/README.md", "ba-readme.md.tpl"),
        ("BA/dispatch/rules.md", "dispatch-rules.md.tpl"),
        ("BA/dispatch/agent-registry.md", "agent-registry.md.tpl"),
        ("BA/dispatch/req-registry.md", "req-registry.md.tpl"),
        ("BA/dispatch/cleanup-log.md", "cleanup-log.md.tpl"),
        ("Deploy/README.md", "deploy-readme.md.tpl"),
    ]
    for rel, tpl in bootstrap:
        if not (root / rel).exists():
            add.append((rel, "cp <skill>/assets/templates/%s %s" % (tpl, rel)))

    # 3. .gitignore
    gi = root / ".gitignore"
    gi_text = gi.read_text(encoding="utf-8", errors="ignore") if gi.exists() else ""
    if "/*/" not in gi_text:
        adjust.append((".gitignore 缺少 /*/", "第一层子目录未被屏蔽，git add -A 可能污染 workspace 分支",
                       "按 assets/templates/root-gitignore.tpl 补齐"))
    for e in wt:
        local = e["path"] / ".local"
        if not local.is_dir():
            continue
        wgi = e["path"] / ".gitignore"
        text = wgi.read_text(encoding="utf-8", errors="ignore") if wgi.exists() else ""
        if ".local/" not in text:
            adjust.append(("%s/.gitignore" % (e["path"].name), "有 .local/ 但未忽略", "追加一行 .local/ 并提交"))

    # 4. feature 产物
    for e in wt:
        if e["path"].name.startswith("feature-") and not (e["path"] / ".feature" / "manifest.json").exists():
            add.append(("%s/.feature/manifest.json" % e["path"].name,
                        "缺少分配记录",
                        "启用 .feature 规范时补 manifest（agent_id / base_commit）"))

    # 5. 僵尸 worktree
    for e in wt:
        name = e["path"].name
        if not name.startswith(("feature-", "hotfix-")) or not e["path"].exists():
            continue
        try:
            age_hours = (time.time() - e["path"].stat().st_ctime) / 3600
        except OSError:
            age_hours = 0
        if age_hours < args.idle_hours:
            continue  # 刚建的 worktree 天然"已合并"，不算僵尸
        br = e["branch"] or ""
        try:
            dirty = git("status", "--porcelain", cwd=e["path"], check=False).stdout.strip()
        except OSError:
            continue
        merged = br in git("branch", "--merged", "develop", "--format=%(refname:short)",
                           cwd=root, check=False).stdout.split()
        if merged and not dirty:
            clean.append(("已合并未回收", name, "aw.py claim release %s --remove-worktree（或手工 worktree remove）"
                          % name.replace("feature-", "")))

    # 6. 旧引用 / vendored skill
    for rel, old, new in _scan_refs(root):
        adjust.append((rel, "引用了已改名的 %s" % old, "改为 %s" % new))

    for candidate in ("skills/agent-workspace", ".agents/skills/agent-workspace"):
        skill_md = root / candidate / "SKILL.md"
        if skill_md.exists():
            adjust.append((candidate, "项目内 vendor 了 skill（版本 %s）" % skill_version(skill_md),
                           "建议改为外部安装 + 版本指针，避免多项目版本漂移"))

    # 7. 版本记录
    record = aw_path(root, "version.json")
    recorded = read_json(record, {}).get("skill_version")
    if recorded and recorded != installed:
        add.append((".aw/version.json", "记录 %s，当前 skill %s" % (recorded, installed),
                    "升级完成后更新记录"))

    if args.json:
        print(json.dumps({"root": str(root), "installed": installed, "recorded": recorded,
                          "add": add, "clean": clean, "adjust": adjust}, ensure_ascii=False, indent=2))
    else:
        print("Agent Workspace 升级检查")
        print("  项目       : %s" % root)
        print("  技能版本   : %s" % installed)
        print("  项目记录   : %s" % (recorded or "（未记录）"))
        for title, items, mark in (("需要补", add, "+"), ("需要清", clean, "-"), ("需要改", adjust, "~")):
            print("\n[%s %d 项]" % (title, len(items)))
            if not items:
                print("  （无）")
            for item in items:
                print("  %s %-34s %s" % (mark, item[0][:34], item[1]))
                if len(item) > 2 and item[2]:
                    print("      → %s" % item[2])
        print("\n[不要动]")
        print("  - 不要重建仓库、rebase、改分支名")
        print("  - 已合并 worktree 的清理走 claim release 或 worktree remove，不要 rm -rf")
        print("\n结论: %d 补 / %d 清 / %d 改" % (len(add), len(clean), len(adjust)))

    return 0 if not (add or clean or adjust) else 1


# ---------------------------------------------------------------- main

def _subparser_list(parser: argparse.ArgumentParser) -> list[argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return list(action.choices.values())
    return []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aw.py", description="Agent Workspace 工具")
    parser.add_argument("--agent", default=None, help="agent_id（优先于 AW_AGENT_ID）")
    parser.add_argument("--no-bind", action="store_true", help="不读写终端绑定（一个终端跑多个 agent 时用）")
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

    p_claim = sub.add_parser("claim", help="任务认领（每个 agent 同时只允许 1 个）")
    p_claim.add_argument("action", choices=["whoami", "next", "take", "release", "list", "doctor"])
    p_claim.add_argument("req", nargs="?", default="")
    p_claim.add_argument("--role", default="ba")
    p_claim.add_argument("--force", action="store_true")
    p_claim.add_argument("--remove-worktree", action="store_true")
    p_claim.add_argument("--repair", action="store_true")
    p_claim.add_argument("--ignore-unread", action="store_true", help="忽略未读消息强制认领")
    p_claim.set_defaults(func=cmd_claim)

    p_agent = sub.add_parser("agent", help="查看/绑定当前 agent 身份")
    p_agent.add_argument("action",
                         choices=["whoami", "check", "bind", "unbind", "register", "roster",
                                  "activate", "deactivate", "exit", "publish"],
                         nargs="?", default="whoami")
    p_agent.add_argument("name", nargs="?", default="")
    p_agent.add_argument("--force", action="store_true", help="bind 强制改绑 / exit 强制退出")
    p_agent.add_argument("--role", default="", help="register 时的角色")
    p_agent.add_argument("--host", default="", help="register 时的机器名")
    p_agent.add_argument("--keep-binding", action="store_true", help="exit 时保留终端绑定")
    p_agent.add_argument("--json", action="store_true", help="roster 输出 JSON")
    p_agent.add_argument("--message", default="", help="publish 的提交信息")
    p_agent.set_defaults(func=cmd_agent)

    p_mcp = sub.add_parser("mcp", help="MCP 客户端配置：status / install / print")
    p_mcp.add_argument("action", choices=["status", "install", "ensure", "print"])
    p_mcp.add_argument("--client", choices=["auto", "claude", "cursor", "vscode", "claude-code"], default="auto")
    p_mcp.add_argument("--path", default="")
    p_mcp.add_argument("--dry-run", action="store_true")
    p_mcp.add_argument("--json", action="store_true")
    p_mcp.set_defaults(func=cmd_mcp)

    p_contract = sub.add_parser("contract", help="契约一致性检查")
    p_contract.add_argument("action", choices=["check", "list"])
    p_contract.add_argument("--strict", action="store_true")
    p_contract.add_argument("--no-fetch", action="store_true")
    p_contract.add_argument("--json", action="store_true")
    p_contract.set_defaults(func=cmd_contract)

    p_msg = sub.add_parser("msg", help="BA 间消息（空 commit 走 bus 分支）")
    p_msg.add_argument("action", choices=["send", "inbox", "list", "ack", "flush", "show", "wait"])
    p_msg.add_argument("--json", action="store_true", help="机器可读输出")
    p_msg.add_argument("id", nargs="?", default="")
    p_msg.add_argument("--to", default="", help="收件人，逗号分隔；支持 all / role:ba / agent_id")
    p_msg.add_argument("--cc", default="")
    p_msg.add_argument("--type", default="fyi", choices=list(MSG_TYPES))
    p_msg.add_argument("--body", default="")
    p_msg.add_argument("--subject", default="")
    p_msg.add_argument("--ref", default="")
    p_msg.add_argument("--contract", default="")
    p_msg.add_argument("--version", default="")
    p_msg.add_argument("--deadline", default="")
    p_msg.add_argument("--thread", default="")
    p_msg.add_argument("--priority", default="p2")
    p_msg.add_argument("--all", action="store_true", help="包含不是发给我的消息")
    p_msg.add_argument("--sender", default="", help="只看某个发送者")
    p_msg.add_argument("--since", default="", help="只看某个 UTC 时间之后")
    p_msg.add_argument("--limit", type=int, default=50)
    p_msg.add_argument("--full", action="store_true")
    p_msg.add_argument("--no-fetch", action="store_true")
    p_msg.add_argument("--no-advance", action="store_true", help="只读，不推进游标（Notifier 用）")
    p_msg.add_argument("--force", action="store_true", help="跳过收件人注册校验")
    p_msg.add_argument("--timeout", type=int, default=120, help="wait 最长秒数（默认 120）")
    p_msg.add_argument("--interval", type=int, default=5, help="wait 轮询间隔秒数")
    p_msg.add_argument("--consume", action="store_true", help="wait 命中后标记已读")
    p_msg.add_argument("--ok", action="store_true", help="ack 时表示同意（默认）")
    p_msg.add_argument("--note", default="", help="ack 附言")
    p_msg.add_argument("--reject", action="store_true", help="ack 时表示不同意")
    p_msg.set_defaults(func=cmd_msg)

    p_up = sub.add_parser("upgrade", help="升级检查（只读，不改任何文件）")
    p_up.add_argument("--json", action="store_true")
    p_up.add_argument("--idle-hours", type=float, default=1.0, help="worktree 存活多久才算僵尸，默认 1 小时")
    p_up.set_defaults(func=cmd_upgrade)

    p_queue = sub.add_parser("queue", help="待认领队列")
    p_queue.add_argument("action", choices=["add", "list", "sync"])
    p_queue.add_argument("req", nargs="?", default="")
    p_queue.add_argument("--title", default="")
    p_queue.set_defaults(func=cmd_queue)

    # 允许 --agent 写在子命令后面：aw.py msg inbox --agent ba-1
    for subparser in _subparser_list(parser):
        subparser.add_argument("--agent", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        subparser.add_argument("--no-bind", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
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
    if getattr(args, "agent", None):
        os.environ["AW_AGENT_ID"] = args.agent
        os.environ["AW_AGENT_SOURCE"] = "--agent"
    elif os.environ.get("AW_AGENT_ID"):
        os.environ.setdefault("AW_AGENT_SOURCE", "env AW_AGENT_ID")
    if getattr(args, "no_bind", False):
        os.environ["AW_NO_BIND"] = "1"
    try:
        return args.func(args)
    except IdentityError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except TimeoutError as exc:
        print("等待锁超时: %s" % exc, file=sys.stderr)
        return 1
    except GitError as exc:
        print("错误: %s" % exc, file=sys.stderr)
        return 1
    except OSError as exc:
        print("系统错误: %s" % exc, file=sys.stderr)
        print("提示: 请确认路径存在、未被占用（OneDrive/杀毒软件可能锁文件），且磁盘可写。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
