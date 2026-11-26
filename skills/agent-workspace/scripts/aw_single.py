#!/usr/bin/env python3
"""agent-workspace-single: 单机、双仓、传统分支的轻量协作层。

只负责本地 claim / queue / feature worktree；不写 docs 状态，不创建
demand/bus/deploy 分支。依赖 Python 3.8+ 标准库与 git。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

REQ_RE = re.compile(r"^REQ-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
REQ_FORMAT_HINT = "REQ 格式应为 REQ-001 / REQ-ONT-C1"
STATE_DIR = ".aw"


class ToolError(RuntimeError):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def _is_subagent() -> bool:
    value = (os.environ.get("AW_SUBAGENT") or os.environ.get("AW_NO_MSG") or "").strip().lower()
    return value in ("1", "true", "yes", "on")


def _reject_subagent(action: str) -> None:
    if _is_subagent():
        raise ToolError(
            "SUBAGENT_NO_%s: 子 Agent 不接消息、不 watch、不 claim；"
            "只执行任务卡，结果交回父会话" % action.upper(), 3
        )


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _init_console() -> None:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _win_startupinfo():
    if os.name != "nt":
        return None
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    return info


def _win_no_window() -> dict:
    if os.name != "nt":
        return {}
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
        "startupinfo": _win_startupinfo(),
    }


def git(*args: str, cwd: Path | str, check: bool = True,
        timeout: float | None = None) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            **_win_no_window(),
        )
    except subprocess.TimeoutExpired:
        raise ToolError("git %s 超时（%ss）" % (" ".join(args), timeout), 1)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ToolError("git %s 失败: %s" % (" ".join(args), detail), 1)
    return proc


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("%s.%d.%s.tmp" % (path.name, os.getpid(), secrets.token_hex(3)))
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Windows 上目标文件被其他进程打开时 os.replace 会报 PermissionError（WinError 5/32），
    # 读方关闭后即可替换；短暂重试，避免 watch 常驻进程因一次共享冲突退出。
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 19:
                tmp.unlink(missing_ok=True)
                raise
            time.sleep(0.05 * (attempt + 1))


class FileLock:
    """跨进程锁；Windows msvcrt，POSIX fcntl。"""

    def __init__(self, path: Path, timeout: float = 10.0):
        self.path = path
        self.timeout = timeout
        self.fd = None

    def __enter__(self):
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
                if time.time() >= deadline:
                    os.close(self.fd)
                    self.fd = None
                    raise ToolError("等待 claim 锁超时: %s" % self.path, 1)
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb):
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


def _find_config(args) -> Path:
    explicit = getattr(args, "config", None) or os.environ.get("AW_SINGLE_CONFIG")
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_dir():
            path = path / STATE_DIR / "config.json"
        if not path.is_file():
            raise ToolError("配置文件不存在: %s" % path, 2)
        return path.resolve()
    cur = Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        candidate = parent / STATE_DIR / "config.json"
        if candidate.is_file():
            return candidate
    raise ToolError("找不到 .aw/config.json；先运行 aw_single.py init", 2)


def load_config(args) -> tuple[Path, dict]:
    path = _find_config(args)
    data = read_json(path, None)
    if not isinstance(data, dict):
        raise ToolError("配置文件不是合法 JSON: %s" % path, 2)
    root = path.parent.parent
    required = ("code_root", "docs_root", "base_branch", "worktree_root")
    missing = [k for k in required if not str(data.get(k) or "").strip()]
    if missing:
        raise ToolError("配置缺字段: %s" % ", ".join(missing), 2)
    for key in ("code_root", "docs_root", "worktree_root"):
        value = Path(str(data[key])).expanduser()
        if not value.is_absolute():
            value = root / value
        data[key] = str(value.resolve())
    data.setdefault("branch_prefix", "feature/")
    data.setdefault("demand_dir", "demands")
    if not Path(data["code_root"]).is_dir():
        raise ToolError("code_root 不存在: %s" % data["code_root"], 2)
    if not Path(data["docs_root"]).is_dir():
        raise ToolError("docs_root 不存在: %s" % data["docs_root"], 2)
    return root, data


def _session() -> tuple[str, str]:
    for key in ("AW_SESSION_ID", "PI_SESSION_ID", "DSH_SESSION_ID", "CLAUDE_SESSION_ID"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value, key
    return "proc-%d" % os.getpid(), "generated"


def _identity(args) -> dict:
    agent = (getattr(args, "agent", None) or os.environ.get("AW_AGENT_ID") or "").strip()
    if not agent:
        raise ToolError("MISSING_AGENT_ID\n提供 --agent 或设置 AW_AGENT_ID", 2)
    sid, source = _session()
    return {"agent_id": agent, "session_id": sid, "session_source": source}


def _record_session(root: Path, ident: dict) -> None:
    path = root / STATE_DIR / "sessions" / ("%s.json" % ident["agent_id"])
    old = read_json(path, {})
    sid = ident["session_id"]
    source = ident["session_source"]
    if source == "generated" and old.get("session_id") and old.get("session_source") != "generated":
        sid = old["session_id"]
        source = old.get("session_source") or source
    record = {
        "agent_id": ident["agent_id"],
        "session_id": sid,
        "session_source": source,
        "started_at": old.get("started_at") or _now(),
        "last_seen": _now(),
        "pid": os.getpid(),
        "pid_started_at": _process_start(os.getpid()),
        "role": os.environ.get("AW_ROLE", ""),
        "host": os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME", ""),
    }
    write_json(path, record)
    _write_session_map(root, record)



def _by_session_path(root: Path, session_id: str) -> Path:
    key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
    return root / STATE_DIR / "sessions" / "by-session" / ("%s.json" % key)


def _write_session_map(root: Path, record: dict) -> None:
    """写 agent→session 权威映射和 session→agent 反向映射。失败只 warn。"""
    source = str(record.get("session_source") or "")
    if source in ("generated", "mcp"):
        return
    sid = str(record.get("session_id") or "").strip()
    if not sid or sid.startswith("proc-"):
        return
    agent = str(record.get("agent_id") or "")
    if not agent:
        return
    map_path = root / STATE_DIR / "sessions" / ("%s.map.json" % agent)
    by_path = _by_session_path(root, sid)
    old = read_json(map_path, {})
    if old.get("session_id") == sid and old.get("map_version") == 2 and by_path.exists():
        try:
            age = (_dt.datetime.now().astimezone()
                   - _dt.datetime.fromisoformat(old.get("updated_at", ""))).total_seconds()
            if age < 60:
                return
        except ValueError:
            pass
    owner = ""
    if by_path.exists():
        owner = str(read_json(by_path, {}).get("agent_id") or "").strip()
    authoritative = not owner or owner == agent
    sessions = old.get("sessions") if isinstance(old.get("sessions"), list) else []
    sessions = [s for s in sessions if isinstance(s, dict) and s.get("session_id") != sid]
    sessions.append({"session_id": sid, "source": source, "at": _now()})
    sessions = sessions[-8:]
    data = {
        "agent_id": agent,
        "session_id": sid,
        "session_source": source,
        "session_authoritative": authoritative,
        "sessions": sessions,
        "host": record.get("host", ""),
        "cwd": str(Path.cwd()),
        "pid": 0,
        "updated_at": _now(),
        "map_version": 2,
    }
    try:
        write_json(map_path, data)
        if authoritative:
            write_json(by_path, {
                "session_id": sid, "agent_id": agent, "source": source,
                "updated_at": _now(),
            })
        else:
            print("warn: session %s 已属于 %s，%s 的映射标记为非权威"
                  % (sid, owner, agent), file=sys.stderr)
    except OSError as exc:
        print("warn: 写 session map 失败（不影响命令）: %s" % exc, file=sys.stderr)

def _claims(root: Path) -> list[dict]:
    out = []
    for path in sorted((root / STATE_DIR / "claims").glob("*.json")):
        data = read_json(path, None)
        if isinstance(data, dict) and data.get("req"):
            data["_path"] = str(path)
            out.append(data)
    return out


def _holding(claims: list[dict], agent: str) -> dict | None:
    return next((c for c in claims
                 if c.get("agent_id") == agent and c.get("state") == "active"), None)


def _claim_path(root: Path, req: str) -> Path:
    return root / STATE_DIR / "claims" / ("%s.json" % req)


def _queue(root: Path) -> list[dict]:
    data = read_json(root / STATE_DIR / "queue.json", [])
    return data if isinstance(data, list) else []


def _save_queue(root: Path, queue: list[dict]) -> None:
    write_json(root / STATE_DIR / "queue.json", queue)


def _resolve_base(cfg: dict) -> str:
    proc = git("rev-parse", "--verify", cfg["base_branch"], cwd=cfg["code_root"], check=False)
    if proc.returncode != 0:
        raise ToolError("base_branch 不存在: %s" % cfg["base_branch"], 2)
    return proc.stdout.strip()


def _create_claim(root: Path, cfg: dict, ident: dict, req: str, title: str = "") -> dict:
    base_sha = _resolve_base(cfg)
    branch = "%s%s" % (cfg["branch_prefix"], req)
    worktree = str(Path(cfg["worktree_root"]) / req)
    claim = {
        "req": req,
        "title": title,
        "agent_id": ident["agent_id"],
        "session_id": ident["session_id"],
        "session_source": ident["session_source"],
        "branch": branch,
        "worktree": worktree,
        "base_branch": cfg["base_branch"],
        "base_sha": base_sha,
        "state": "active",
        "claimed_at": _now(),
    }
    write_json(_claim_path(root, req), claim)
    return claim


def _finish_claim(root: Path, cfg: dict, claim: dict) -> None:
    code = Path(cfg["code_root"])
    worktree = Path(claim["worktree"])
    branch = claim["branch"]
    if worktree.exists():
        _rollback_claim(root, claim)
        raise ToolError("worktree 已存在: %s" % worktree, 3)
    proc = git("show-ref", "--verify", "--quiet", "refs/heads/%s" % branch,
               cwd=code, check=False)
    if proc.returncode == 0:
        _rollback_claim(root, claim)
        raise ToolError("分支已存在: %s" % branch, 3)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    proc = git("worktree", "add", "-b", branch, str(worktree), cfg["base_branch"],
               cwd=code, check=False, timeout=120)
    if proc.returncode != 0:
        _rollback_claim(root, claim)
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ToolError("CLAIM_FAILED 创建 worktree 失败: %s" % detail, 1)


def _rollback_claim(root: Path, claim: dict) -> None:
    try:
        _claim_path(root, claim["req"]).unlink(missing_ok=True)
    except OSError:
        pass
    queue = _queue(root)
    if not any(q.get("req") == claim["req"] for q in queue):
        queue.append({"req": claim["req"], "title": claim.get("title", ""), "added_at": _now()})
        _save_queue(root, queue)


def _claim_next(root: Path, cfg: dict, ident: dict) -> int:
    with FileLock(root / STATE_DIR / "locks" / "claims.lock"):
        claims = _claims(root)
        mine = _holding(claims, ident["agent_id"])
        if mine:
            print("ALREADY_HOLDING %s" % mine["req"])
            return 3
        queue = _queue(root)
        taken = {c["req"] for c in claims if c.get("state") == "active"}
        candidate = next((q for q in queue if q.get("req") not in taken), None)
        if not candidate:
            print("QUEUE_EMPTY")
            return 3
        req = candidate["req"]
        claim = _create_claim(root, cfg, ident, req, candidate.get("title", ""))
        _save_queue(root, [q for q in queue if q.get("req") != req])
    _finish_claim(root, cfg, claim)
    print("CLAIMED %s" % req)
    return 0


def _claim_take(root: Path, cfg: dict, ident: dict, req: str) -> int:
    req = req.strip().upper()
    if not REQ_RE.match(req):
        raise ToolError(REQ_FORMAT_HINT, 2)
    with FileLock(root / STATE_DIR / "locks" / "claims.lock"):
        claims = _claims(root)
        mine = _holding(claims, ident["agent_id"])
        if mine:
            print("ALREADY_HOLDING %s" % mine["req"])
            return 3
        existing = next((c for c in claims
                         if c.get("req") == req and c.get("state") == "active"), None)
        if existing:
            print("TAKEN_BY %s" % existing.get("agent_id", "?"))
            return 3
        queue = _queue(root)
        title = next((q.get("title", "") for q in queue if q.get("req") == req), "")
        claim = _create_claim(root, cfg, ident, req, title)
        _save_queue(root, [q for q in queue if q.get("req") != req])
    _finish_claim(root, cfg, claim)
    print("CLAIMED %s" % req)
    return 0


def _claim_adopt(root: Path, cfg: dict, ident: dict, req: str, branch: str = "") -> int:
    req = req.strip().upper()
    if not REQ_RE.match(req):
        raise ToolError(REQ_FORMAT_HINT, 2)
    branch = (branch or ("%s%s" % (cfg["branch_prefix"], req))).strip()
    code = Path(cfg["code_root"])
    worktree = Path(cfg["worktree_root"]) / req
    with FileLock(root / STATE_DIR / "locks" / "claims.lock"):
        claims = _claims(root)
        mine = _holding(claims, ident["agent_id"])
        if mine:
            print("ALREADY_HOLDING %s" % mine["req"])
            return 3
        existing = next((c for c in claims
                         if c.get("req") == req and c.get("state") == "active"), None)
        if existing:
            print("TAKEN_BY %s" % existing.get("agent_id", "?"))
            return 3
        if git("show-ref", "--verify", "--quiet", "refs/heads/%s" % branch,
               cwd=code, check=False).returncode != 0:
            print("BRANCH_NOT_FOUND %s" % branch)
            return 3
        if worktree.exists():
            actual = git("rev-parse", "--abbrev-ref", "HEAD", cwd=worktree, check=False).stdout.strip()
            if actual != branch:
                print("WORKTREE_BRANCH_MISMATCH %s: claim=%s actual=%s" % (req, branch, actual))
                return 3
        else:
            worktree.parent.mkdir(parents=True, exist_ok=True)
            proc = git("worktree", "add", str(worktree), branch, cwd=code, check=False, timeout=120)
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "").strip()
                raise ToolError("ADOPT_FAILED 创建 worktree 失败: %s" % detail, 1)
        claim = {
            "req": req,
            "title": next((q.get("title", "") for q in _queue(root) if q.get("req") == req), ""),
            "agent_id": ident["agent_id"],
            "session_id": ident["session_id"],
            "session_source": ident["session_source"],
            "branch": branch,
            "worktree": str(worktree),
            "base_branch": cfg["base_branch"],
            "base_sha": _resolve_base(cfg),
            "state": "active",
            "adopted": True,
            "claimed_at": _now(),
        }
        write_json(_claim_path(root, req), claim)
        _save_queue(root, [q for q in _queue(root) if q.get("req") != req])
    print("ADOPTED %s %s" % (req, branch))
    return 0


def _claim_release(root: Path, cfg: dict, ident: dict, req: str,
                   force: bool = False, remove_worktree: bool = False) -> int:
    req = req.strip().upper()
    claim = read_json(_claim_path(root, req), None)
    if not isinstance(claim, dict):
        print("NOT_CLAIMED %s" % req)
        return 3
    if claim.get("agent_id") != ident["agent_id"] and not force:
        print("NOT_YOURS %s（属于 %s）" % (req, claim.get("agent_id")))
        return 3
    with FileLock(root / STATE_DIR / "locks" / "claims.lock"):
        claim["state"] = "released"
        claim["released_at"] = _now()
        archive = root / STATE_DIR / "archive"
        archive.mkdir(parents=True, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d%H%M%S")
        write_json(archive / ("%s-%s.json" % (req, stamp)), claim)
        _claim_path(root, req).unlink(missing_ok=True)
    if remove_worktree:
        wt = Path(claim["worktree"])
        if wt.exists():
            dirty = git("status", "--porcelain", cwd=wt, check=False).stdout.strip()
            if dirty and not force:
                print("RELEASED %s（worktree 有未提交改动，已保留）" % req)
                return 0
            git("worktree", "remove", str(wt), cwd=cfg["code_root"], check=False)
    print("RELEASED %s" % req)
    return 0


def _claim_list(root: Path) -> int:
    claims = _claims(root)
    if not claims:
        print("（无认领）")
        return 0
    rows = [["REQ", "agent", "state", "branch", "worktree"]]
    for c in claims:
        rows.append([c["req"], c.get("agent_id", "-"), c.get("state", "-"),
                     c.get("branch", "-"), c.get("worktree", "-")])
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    for row in rows:
        print("  ".join(str(v).ljust(widths[i]) for i, v in enumerate(row)))
    return 0


def _claim_doctor(root: Path, cfg: dict) -> int:
    claims = _claims(root)
    problems = []
    by_agent = {}
    for c in claims:
        if c.get("state") != "active":
            continue
        by_agent.setdefault(c.get("agent_id", "?"), []).append(c)
        wt = Path(c.get("worktree", ""))
        if not wt.is_dir():
            problems.append("[missing-worktree] %s %s" % (c["req"], wt))
            continue
        branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=wt, check=False).stdout.strip()
        if branch and c.get("branch") and branch != c["branch"]:
            problems.append("[branch-mismatch] %s: claim=%s actual=%s"
                            % (c["req"], c["branch"], branch))
    for agent, items in by_agent.items():
        if len(items) > 1:
            problems.append("[multi-claim] %s: %s" %
                            (agent, ", ".join(c["req"] for c in items)))
    active_names = {c["req"] for c in claims if c.get("state") == "active"}
    wt_root = Path(cfg["worktree_root"])
    if wt_root.is_dir():
        for p in wt_root.iterdir():
            if p.is_dir() and REQ_RE.match(p.name) and p.name not in active_names:
                problems.append("[orphan-worktree] %s" % p)
    if not problems:
        print("OK 没有发现问题（%d 个认领）" % len(claims))
        return 0
    for item in problems:
        print(item)
    return 1



def _process_start(pid: int) -> str:
    """返回进程创建时间（ISO 8601），用于识别 PID 复用；取不到返回空。"""
    if not pid or pid <= 0:
        return ""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", wintypes.DWORD),
                            ("dwHighDateTime", wintypes.DWORD)]

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return ""
            try:
                created = FILETIME()
                exit_t = FILETIME()
                kernel = FILETIME()
                user = FILETIME()
                ok = ctypes.windll.kernel32.GetProcessTimes(
                    handle, ctypes.byref(created), ctypes.byref(exit_t),
                    ctypes.byref(kernel), ctypes.byref(user))
                if not ok:
                    return ""
                ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
                seconds = (ticks - 116444736000000000) / 10_000_000
                return _dt.datetime.fromtimestamp(seconds, _dt.timezone.utc).isoformat(timespec="seconds")
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return ""
    try:
        stat = Path("/proc/%d/stat" % pid).read_text(encoding="utf-8")
        parts = stat.split()
        start_ticks = int(parts[21])
        btime = None
        for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                btime = int(line.split()[1])
                break
        if btime is None:
            return ""
        hz = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
        seconds = btime + start_ticks / float(hz)
        return _dt.datetime.fromtimestamp(seconds, _dt.timezone.utc).isoformat(timespec="seconds")
    except (OSError, ValueError, IndexError):
        return ""


def _same_start(a: str, b: str, tolerance: int = 5) -> bool:
    if not a or not b:
        return True
    try:
        ta = _dt.datetime.fromisoformat(a.replace("Z", "+00:00"))
        tb = _dt.datetime.fromisoformat(b.replace("Z", "+00:00"))
        return abs((ta - tb).total_seconds()) <= tolerance
    except ValueError:
        return True


def _presence_path(root: Path, agent: str) -> Path:
    return root / STATE_DIR / "presence" / ("%s.json" % agent)


def _session_alive(record: dict) -> bool:
    pid = int(record.get("pid") or 0)
    if not _pid_alive(pid):
        return False
    recorded = str(record.get("pid_started_at") or "")
    actual = _process_start(pid)
    if recorded and actual and not _same_start(recorded, actual):
        return False
    return True


def _update_presence(root: Path) -> None:
    folder = root / STATE_DIR / "sessions"
    if not folder.is_dir():
        return
    for path in folder.glob("*.json"):
        record = read_json(path, None)
        if not isinstance(record, dict) or not record.get("agent_id"):
            continue
        agent = str(record["agent_id"])
        alive = _session_alive(record)
        prev = read_json(_presence_path(root, agent), {})
        status = "online" if alive else "offline"
        if prev.get("status") == status and not alive:
            continue
        write_json(_presence_path(root, agent), {
            "agent": agent,
            "role": record.get("role", ""),
            "status": status,
            "session": record.get("session_id", ""),
            "host": record.get("host", ""),
            "pid": record.get("pid", 0),
            "pid_started_at": record.get("pid_started_at", ""),
            "last_seen": record.get("last_seen", ""),
            "updated_at": _now(),
            "ttl_s": 90,
        })



def _normalize_remote(url: str) -> str:
    """把 git remote 归一成 host/owner/repo；本地路径返回空。"""
    text = (url or "").strip()
    if not text or text.startswith("file://") or text.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", text):
        return ""
    scheme = ""
    port = None
    path = ""
    if "://" in text:
        try:
            parsed = urlparse(text)
        except ValueError:
            return ""
        scheme = (parsed.scheme or "").lower()
        host = (parsed.hostname or "").lower()
        try:
            port = parsed.port
        except ValueError:
            port = None
        path = parsed.path or ""
    else:
        match = re.match(r"^(?:[^@/]+@)?([^:/]+):(.+)$", text)
        if not match:
            return ""
        host = match.group(1).lower()
        path = match.group(2)
    if port and not (scheme == "https" and port == 443) and not (scheme == "http" and port == 80) and not (scheme in ("ssh", "git+ssh") and port == 22):
        host = "%s:%d" % (host, port)
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not host or not path:
        return ""
    return host + "/" + path


def _project_identity(code_root: Path) -> dict:
    if not code_root.is_dir():
        raise ToolError("code_root 不存在: %s" % code_root, 2)
    remotes = git("remote", cwd=code_root, check=False).stdout.split()
    name = "origin" if "origin" in remotes else (remotes[0] if remotes else "")
    if name:
        url = git("remote", "get-url", name, cwd=code_root, check=False).stdout.strip()
        alias = _normalize_remote(url)
        if alias:
            return {
                "project_id": "p-" + hashlib.sha256(alias.encode("utf-8")).hexdigest()[:12],
                "project_alias": alias,
                "project_source": "git:%s" % name,
            }
    roots = git("rev-list", "--max-parents=0", "HEAD", cwd=code_root, check=False)
    shas = [x.strip() for x in roots.stdout.splitlines() if x.strip()]
    if not shas:
        raise ToolError("无法从 remote 或根 commit 推导 project_id: %s" % code_root, 2)
    root_sha = sorted(shas)[0]
    alias = "root:" + root_sha
    return {
        "project_id": "p-" + hashlib.sha256(alias.encode("utf-8")).hexdigest()[:12],
        "project_alias": alias,
        "project_source": "git:root-commit",
    }


def cmd_project(args) -> int:
    _root, cfg = load_config(args)
    info = _project_identity(Path(cfg["code_root"]))
    action = args.action
    if action == "id":
        print(info["project_id"])
        return 0
    if action == "alias":
        print(info["project_alias"])
        return 0
    if action == "check":
        configured = str(cfg.get("project_id") or "").strip()
        if not configured:
            print("PROJECT_MISSING config.project_id")
            return 1
        if configured != info["project_id"]:
            print("PROJECT_MISMATCH config=%s current=%s" % (configured, info["project_id"]))
            return 1
        print("PROJECT_OK %s %s" % (info["project_id"], info["project_alias"]))
        return 0
    raise ToolError("未知 project 操作: %s" % action, 2)

def _active_presence(root: Path) -> list[dict]:
    _update_presence(root)
    folder = root / STATE_DIR / "presence"
    rows = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        data = read_json(path, None)
        if isinstance(data, dict) and data.get("status") == "online":
            rows.append(data)
    return rows


def cmd_presence(args) -> int:
    root, _cfg = load_config(args)
    _update_presence(root)
    folder = root / STATE_DIR / "presence"
    rows = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        data = read_json(path, None)
        if isinstance(data, dict):
            rows.append(data)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("（无 presence）")
        return 0
    for row in rows:
        print("%s\t%s\t%s\tpid=%s\t%s" % (
            row.get("agent", ""), row.get("role", ""), row.get("status", ""),
            row.get("pid", ""), row.get("updated_at", "")))
    return 0

def cmd_init(args) -> int:
    root = Path(args.root).expanduser().resolve()
    code = Path(args.code_root).expanduser().resolve()
    docs = Path(args.docs_root).expanduser().resolve()
    if not code.is_dir():
        raise ToolError("code_root 不存在: %s" % code, 2)
    if not docs.is_dir():
        raise ToolError("docs_root 不存在: %s" % docs, 2)
    proc = git("rev-parse", "--show-toplevel", cwd=code, check=False)
    if proc.returncode != 0:
        raise ToolError("code_root 不是 git 仓库: %s" % code, 2)
    top = Path(proc.stdout.strip()).resolve()
    if top != code:
        raise ToolError("code_root 必须是 git 仓库根: %s" % top, 2)
    proc = git("rev-parse", "--verify", args.base_branch, cwd=code, check=False)
    if proc.returncode != 0:
        raise ToolError("base_branch 不存在: %s" % args.base_branch, 2)
    state = root / STATE_DIR
    if (state / "config.json").exists():
        raise ToolError("已经初始化: %s" % (state / "config.json"), 2)
    for name in ("claims", "sessions", "locks", "archive"):
        (state / name).mkdir(parents=True, exist_ok=True)
    if args.worktree_root:
        wt_value = Path(args.worktree_root).expanduser()
        worktree_root = wt_value.resolve() if wt_value.is_absolute() else (root / wt_value).resolve()
    else:
        worktree_root = (root / "worktrees").resolve()
    worktree_root.mkdir(parents=True, exist_ok=True)
    project = _project_identity(code)
    mqtt = {"enabled": False}
    if args.mqtt_host.strip():
        mqtt = {
            "enabled": True,
            "host": args.mqtt_host.strip(),
            "port": args.mqtt_port,
            "tls": not args.mqtt_no_tls,
            "ca_file": args.mqtt_ca.strip(),
            "username": args.mqtt_username.strip(),
            "password_env": "AW_MQTT_PASSWORD",
            "client_id": args.mqtt_client_id.strip(),
            "keepalive": 30,
            "topic_prefix": "aw/v1",
        }
    config = {
        "profile": "single",
        "version": 1,
        "code_root": str(code),
        "project_id": project["project_id"],
        "project_alias": project["project_alias"],
        "project_source": project["project_source"],
        "docs_root": str(docs),
        "base_branch": args.base_branch,
        "worktree_root": str(worktree_root),
        "branch_prefix": args.branch_prefix,
        "demand_dir": args.demand_dir,
        "transport": {
            "mode": args.transport,
            "audit_bus": True,
            "bus": {"enabled": True, "branch": "bus", "push": True, "poll_seconds": 30},
        },
        "mqtt": mqtt,
    }
    write_json(state / "config.json", config)
    if not (state / "queue.json").exists():
        write_json(state / "queue.json", [])
    print("INITIALIZED %s" % root)
    return 0


HANDOFF_VERSION = 1


def _handoff_path(root: Path, agent: str) -> Path:
    return root / STATE_DIR / "handoff" / ("%s.json" % agent)


def _handoff_message(msg: dict, status: str) -> dict:
    fields = ("id", "from", "to", "at", "type", "expect", "subject", "ref", "thread")
    row = {k: msg.get(k) for k in fields if msg.get(k)}
    row["status"] = status
    return row


def _collect_handoff(root: Path, ident: dict) -> dict:
    """只读收集交接状态；不推进已读。"""
    agent = ident["agent_id"]
    messages = _messages(root, agent)
    read = _read_ids(root, agent)
    answered = {m.get("re") for m in messages if m.get("re")}
    unread_ids = {str(m.get("id")) for m in messages
                  if m.get("id") and str(m.get("id")) not in read}
    pending_ids = {
        str(m.get("id")) for m in messages
        if m.get("id") and m.get("from") != agent
        and m.get("expect") in ("ack", "reply")
        and str(m.get("id")) not in answered
    }
    rows = []
    for m in messages:
        mid = str(m.get("id") or "")
        if not mid:
            continue
        flags = []
        if mid in unread_ids:
            flags.append("unread")
        if mid in pending_ids:
            flags.append("pending")
        if flags:
            rows.append(_handoff_message(m, "+".join(flags)))
    rows.sort(key=lambda m: (m.get("at", ""), m.get("id", "")))

    claims = [c for c in _claims(root) if c.get("agent_id") == agent]
    claim = claims[0] if claims else None
    public_claim = ({k: v for k, v in claim.items() if k != "_path"}
                    if claim else None)
    sess = read_json(root / STATE_DIR / "sessions" / ("%s.json" % agent), {})
    return {
        "version": HANDOFF_VERSION,
        "agent_id": agent,
        "from_session_id": ident["session_id"],
        "created_at": _now(),
        "cwd": str(Path.cwd()),
        "claim": public_claim,
        "current_req": (public_claim or {}).get("req", ""),
        "unread_ids": sorted(unread_ids),
        "pending_ids": sorted(pending_ids),
        "unresolved": rows,
        "session": sess,
    }


def _reset_wake_seen_to_read(root: Path, agent: str) -> None:
    """让未读消息重新可被唤醒，已读消息不重复叫。"""
    write_json(_wake_seen_path(root, agent), {
        "ids": sorted(_read_ids(root, agent))[-2000:],
    })


def cmd_handoff(args) -> int:
    _reject_subagent("handoff")
    root, _cfg = load_config(args)
    ident = _identity(args)
    _record_session(root, ident)
    data = _collect_handoff(root, ident)
    data["reason"] = getattr(args, "note", "") or ""
    data["next_step"] = getattr(args, "next_step", "") or ""
    path = _handoff_path(root, ident["agent_id"])
    write_json(path, data)

    sess_path = root / STATE_DIR / "sessions" / ("%s.json" % ident["agent_id"])
    sess = read_json(sess_path, {})
    if sess:
        sess.update({"status": "offline", "pid": 0,
                     "ended_at": _now(), "handoff_at": _now()})
        write_json(sess_path, sess)
    _reset_wake_seen_to_read(root, ident["agent_id"])
    _update_presence(root)

    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print("HANDOFF %s" % ident["agent_id"])
        print("  file      : %s" % path)
        print("  claim     : %s" % (data["current_req"] or "-"))
        print("  unresolved: %d（unread %d / pending %d）"
              % (len(data["unresolved"]), len(data["unread_ids"]),
                 len(data["pending_ids"])))
        print("  session   : %s -> offline" % ident["session_id"])
        print("  next      : 停止本会话；新会话用同一个 AW_AGENT_ID，然后 resume")
    return 0


def cmd_resume(args) -> int:
    _reject_subagent("resume")
    root, _cfg = load_config(args)
    ident = _identity(args)
    _record_session(root, ident)
    path = _handoff_path(root, ident["agent_id"])
    data = read_json(path, None)
    if not isinstance(data, dict):
        print("NO_HANDOFF %s（先运行 handoff）" % ident["agent_id"])
        return 3
    if data.get("agent_id") and data["agent_id"] != ident["agent_id"]:
        print("HANDOFF_MISMATCH 文件属于 %s，当前是 %s"
              % (data["agent_id"], ident["agent_id"]), file=sys.stderr)
        return 3
    data["resumed_at"] = _now()
    data["resumed_session_id"] = ident["session_id"]
    write_json(path, data)
    _reset_wake_seen_to_read(root, ident["agent_id"])
    _update_presence(root)

    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        claim = data.get("claim") or {}
        print("RESUMED %s" % ident["agent_id"])
        print("  session   : %s" % ident["session_id"])
        print("  claim     : %s" % (claim.get("req") or data.get("current_req") or "-"))
        print("  unresolved: %d" % len(data.get("unresolved") or []))
        if data.get("reason"):
            print("  reason    : %s" % data["reason"])
        if data.get("next_step"):
            print("  next step : %s" % data["next_step"])
        ids = [m.get("id") for m in (data.get("unresolved") or []) if m.get("id")]
        if ids:
            print("  messages  : %s" % ", ".join(ids[:10]))
            print("  next      : msg inbox / msg ack（先别清空未处理消息）")
    return 0


def cmd_whoami(args) -> int:
    _reject_subagent("whoami")
    root, _cfg = load_config(args)
    ident = _identity(args)
    _record_session(root, ident)
    print("agent_id  : %s" % ident["agent_id"])
    print("session   : %s" % ident["session_id"])
    print("source    : %s" % ident["session_source"])
    print("repo      : %s" % root)
    return 0


def cmd_queue(args) -> int:
    _reject_subagent("queue")
    root, _cfg = load_config(args)
    action = args.action
    if action == "add":
        req = args.req.strip().upper()
        if not REQ_RE.match(req):
            raise ToolError(REQ_FORMAT_HINT, 2)
        with FileLock(root / STATE_DIR / "locks" / "claims.lock"):
            queue = _queue(root)
            if any(q.get("req") == req for q in queue):
                print("ALREADY_QUEUED %s" % req)
                return 3
            queue.append({"req": req, "title": args.title or "", "added_at": _now()})
            _save_queue(root, queue)
        print("QUEUED %s" % req)
        return 0
    if action == "list":
        queue = _queue(root)
        if not queue:
            print("（队列为空）")
            return 0
        for q in queue:
            print("%s\t%s\t%s" % (q.get("req", ""), q.get("title", ""), q.get("added_at", "")))
        return 0
    raise ToolError("未知 queue 操作: %s" % action, 2)


def cmd_claim(args) -> int:
    _reject_subagent("claim")
    root, cfg = load_config(args)
    action = args.action
    if action == "list":
        return _claim_list(root)
    if action == "doctor":
        return _claim_doctor(root, cfg)
    ident = _identity(args)
    _record_session(root, ident)
    if action == "next":
        return _claim_next(root, cfg, ident)
    if action == "take":
        if not args.req:
            raise ToolError("用法: claim take REQ-001", 2)
        return _claim_take(root, cfg, ident, args.req)
    if action == "adopt":
        if not args.req:
            raise ToolError("用法: claim adopt REQ-001 [--branch feature/REQ-001]", 2)
        return _claim_adopt(root, cfg, ident, args.req, branch=args.branch)
    if action == "release":
        if not args.req:
            raise ToolError("用法: claim release REQ-001", 2)
        return _claim_release(root, cfg, ident, args.req,
                              force=args.force, remove_worktree=args.remove_worktree)
    raise ToolError("未知 claim 操作: %s" % action, 2)



# ---------------------------------------------------------------- local messages

def _safe_agent(value: str) -> str:
    text = (value or "").strip()
    if not re.match(r"^[A-Za-z0-9._-]{1,64}$", text):
        raise ToolError("agent_id 非法: %r" % value, 2)
    return text


def _inbox_dir(root: Path, agent: str) -> Path:
    return root / STATE_DIR / "inbox" / _safe_agent(agent)


def _read_ids(root: Path, agent: str) -> set[str]:
    data = read_json(root / STATE_DIR / "msg-read" / ("%s.json" % agent), {})
    return set(str(x) for x in (data.get("ids") or []))


def _save_read_ids(root: Path, agent: str, ids: set[str]) -> None:
    write_json(root / STATE_DIR / "msg-read" / ("%s.json" % agent),
               {"ids": sorted(ids)[-5000:]})


def _messages(root: Path, agent: str) -> list[dict]:
    folder = _inbox_dir(root, agent)
    out = []
    if not folder.is_dir():
        return out
    for path in folder.glob("*.json"):
        data = read_json(path, None)
        if isinstance(data, dict) and data.get("id"):
            data["_path"] = str(path)
            out.append(data)
    out.sort(key=lambda m: (m.get("at", ""), m.get("id", "")))
    return out


def _unread(root: Path, agent: str) -> list[dict]:
    read = _read_ids(root, agent)
    return [m for m in _messages(root, agent) if str(m.get("id")) not in read]


def _default_expect(kind: str) -> str:
    if kind in ("question", "blocker", "handoff"):
        return "reply"
    return "none"



def _bus_branch(cfg: dict) -> str:
    bus = cfg.get("transport", {}).get("bus", {}) if isinstance(cfg.get("transport"), dict) else {}
    return str(bus.get("branch") or "bus")


def _bus_enabled(cfg: dict) -> bool:
    trans = cfg.get("transport", {}) if isinstance(cfg.get("transport"), dict) else {}
    if str(trans.get("mode") or "auto") == "local":
        return False
    bus = trans.get("bus", {}) if isinstance(trans.get("bus"), dict) else {}
    return bool(bus.get("enabled", True))


def _git_raw(args: list[str], cwd: Path, data: bytes | None = None,
             env: dict | None = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(cwd), input=data, capture_output=True, timeout=120,
        env=env, **_win_no_window(),
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace").strip()
        raise ToolError("git %s 失败: %s" % (" ".join(args), detail), 1)
    return proc


def _bus_write(root: Path, cfg: dict, message: dict) -> str:
    code = Path(cfg["code_root"])
    branch = _bus_branch(cfg)
    ref = "refs/heads/%s" % branch
    body = json.dumps(message, ensure_ascii=False, indent=2).encode("utf-8")
    limit = int(cfg.get("transport", {}).get("max_body_bytes", 8 * 1024 * 1024))
    if len(body) > limit:
        raise ToolError("消息过大: %d > %d" % (len(body), limit), 2)
    parent = git("rev-parse", "--verify", ref, cwd=code, check=False)
    parent_sha = parent.stdout.strip() if parent.returncode == 0 else ""
    index = root / STATE_DIR / "locks" / ("bus-index-%d-%s" % (os.getpid(), secrets.token_hex(3)))
    index.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["GIT_INDEX_FILE"] = str(index)
    try:
        if parent_sha:
            _git_raw(["read-tree", parent_sha], code, env=env)
        else:
            _git_raw(["read-tree", "--empty"], code, env=env)
        blob = _git_raw(["hash-object", "-w", "--stdin"], code, data=body).stdout.strip().decode()
        name = "messages/%s.json" % message["id"]
        _git_raw(["update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, name)], code, env=env)
        tree = _git_raw(["write-tree"], code, env=env).stdout.strip().decode()
        cmd = ["-c", "user.name=aw-single", "-c", "user.email=aw-single@local",
               "commit-tree", tree]
        if parent_sha:
            cmd += ["-p", parent_sha]
        cmd += ["-m", "[aw] %s %s -> %s %s" % (
            message["id"], message.get("from", ""), ",".join(message.get("to") or []),
            message.get("type", ""))]
        commit = _git_raw(cmd, code, env=env).stdout.strip().decode()
        old = [parent_sha] if parent_sha else []
        _git_raw(["update-ref", ref, commit, *old], code, env=env)
        return commit
    finally:
        try:
            index.unlink()
        except OSError:
            pass


def _bus_push(root: Path, cfg: dict) -> None:
    bus = cfg.get("transport", {}).get("bus", {}) if isinstance(cfg.get("transport"), dict) else {}
    if not bus.get("push", True):
        return
    code = Path(cfg["code_root"])
    if not git("remote", cwd=code, check=False).stdout.strip():
        return
    proc = git("push", "-q", "origin", "refs/heads/%s:refs/heads/%s" % (
        _bus_branch(cfg), _bus_branch(cfg)), cwd=code, check=False, timeout=30)
    if proc.returncode != 0:
        print("warn: bus push 失败，稍后重试: %s" % (proc.stderr or "").strip(), file=sys.stderr)


def _bus_ref(root: Path, cfg: dict) -> str:
    branch = _bus_branch(cfg)
    remote = "refs/remotes/origin/%s" % branch
    if git("rev-parse", "--verify", remote, cwd=Path(cfg["code_root"]), check=False).returncode == 0:
        return remote
    local = "refs/heads/%s" % branch
    if git("rev-parse", "--verify", local, cwd=Path(cfg["code_root"]), check=False).returncode == 0:
        return local
    return ""


def _bus_fetch(root: Path, cfg: dict) -> None:
    if not _bus_enabled(cfg):
        return
    code = Path(cfg["code_root"])
    if not git("remote", cwd=code, check=False).stdout.strip():
        return
    bus = cfg.get("transport", {}).get("bus", {}) if isinstance(cfg.get("transport"), dict) else {}
    interval = max(5, int(bus.get("poll_seconds", 30)))
    stamp = root / STATE_DIR / "bus-last-fetch"
    try:
        if stamp.exists() and time.time() - stamp.stat().st_mtime < interval:
            return
    except OSError:
        pass
    git("fetch", "-q", "origin", _bus_branch(cfg), cwd=code, check=False, timeout=30)
    try:
        stamp.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass


def _bus_messages(root: Path, cfg: dict) -> list[dict]:
    ref = _bus_ref(root, cfg)
    if not ref:
        return []
    code = Path(cfg["code_root"])
    names = git("ls-tree", "-r", "--name-only", ref, "messages/", cwd=code, check=False).stdout.splitlines()
    out = []
    for name in names:
        if not name.endswith(".json"):
            continue
        proc = git("show", "%s:%s" % (ref, name), cwd=code, check=False)
        try:
            data = json.loads(proc.stdout)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("id"):
            out.append(data)
    return out


def _bus_import(root: Path, cfg: dict) -> int:
    if not _bus_enabled(cfg):
        return 0
    _bus_fetch(root, cfg)
    count = 0
    for msg in _bus_messages(root, cfg):
        for target in msg.get("to") or []:
            target = _safe_agent(str(target))
            path = _inbox_dir(root, target) / ("%s.json" % msg["id"])
            if path.exists():
                continue
            write_json(path, msg)
            count += 1
    return count


def cmd_bus(args) -> int:
    _reject_subagent("bus")
    root, cfg = load_config(args)
    if args.action == "log":
        messages = _bus_messages(root, cfg)
        for msg in messages:
            print("%s\t%s\t%s\t%s\t%s" % (
                msg.get("id"), msg.get("at"), msg.get("from"),
                msg.get("type"), ",".join(msg.get("to") or [])))
        return 0
    if args.action == "show":
        if not args.id:
            raise ToolError("用法: bus show <id>", 2)
        for msg in _bus_messages(root, cfg):
            if str(msg.get("id")) == args.id:
                print(json.dumps(msg, ensure_ascii=False, indent=2))
                return 0
        print("NOT_FOUND %s" % args.id)
        return 3
    raise ToolError("未知 bus 操作: %s" % args.action, 2)


def _mqtt_config(cfg: dict) -> dict | None:
    mqtt = cfg.get("mqtt") if isinstance(cfg.get("mqtt"), dict) else {}
    if not mqtt.get("enabled") or not str(mqtt.get("host") or "").strip():
        return None
    return mqtt


def _project_ok(cfg: dict) -> bool:
    try:
        info = _project_identity(Path(cfg["code_root"]))
    except ToolError:
        return False
    return str(cfg.get("project_id") or "") == info["project_id"]


def _load_paho():
    vendor = Path(__file__).resolve().parent.parent / "vendor"
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    import paho.mqtt.client as mqtt
    return mqtt


def _mqtt_topic(cfg: dict, agent: str, suffix: str) -> str:
    mqtt = cfg.get("mqtt") or {}
    prefix = str(mqtt.get("topic_prefix") or "aw/v1").strip("/")
    project = str(cfg.get("project_id") or "")
    return "%s/%s/agent/%s/%s" % (prefix, project, agent, suffix)


def _mqtt_client(cfg: dict, suffix: str):
    mqtt = _load_paho()
    m = cfg.get("mqtt") or {}
    client_id = str(m.get("client_id") or "").strip()
    if not client_id:
        client_id = "aw-%s-%s-%s" % (
            cfg.get("project_id", ""), socket.gethostname(), suffix)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    username = str(m.get("username") or "").strip()
    password = os.environ.get(str(m.get("password_env") or "AW_MQTT_PASSWORD"), "")
    if username:
        client.username_pw_set(username, password or None)
    if m.get("tls", True):
        ca = str(m.get("ca_file") or "").strip()
        if ca:
            client.tls_set(ca_certs=ca)
        else:
            client.tls_set()
    return client


def _mqtt_connect(cfg: dict, suffix: str = "client"):
    m = cfg.get("mqtt") or {}
    client = _mqtt_client(cfg, suffix)
    client.connect(str(m["host"]), int(m.get("port", 8883)),
                   int(m.get("keepalive", 30)))
    client.loop_start()
    return client


def _mqtt_publish_message(cfg: dict, msg: dict, bus_sha: str = "") -> None:
    mqtt = _load_paho()
    client = _mqtt_connect(cfg, "send-%d" % os.getpid())
    try:
        payload = dict(msg)
        payload["project"] = cfg.get("project_id", "")
        payload["bus_sha"] = bus_sha
        for target in msg.get("to") or []:
            info = client.publish(_mqtt_topic(cfg, str(target), "inbox"),
                                  json.dumps(payload, ensure_ascii=False),
                                  qos=1, retain=False)
            info.wait_for_publish(timeout=5)
    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        client.loop_stop()


def _publish_presence(root: Path, cfg: dict, client) -> None:
    folder = root / STATE_DIR / "presence"
    if not folder.is_dir():
        return
    for path in folder.glob("*.json"):
        data = read_json(path, None)
        if not isinstance(data, dict) or not data.get("agent"):
            continue
        payload = dict(data)
        payload["project"] = cfg.get("project_id", "")
        payload["ts"] = _now()
        payload["ttl_s"] = 90
        client.publish(_mqtt_topic(cfg, str(data["agent"]), "presence"),
                       json.dumps(payload, ensure_ascii=False),
                       qos=1, retain=True)


def _start_mqtt_bridge(root: Path, cfg: dict):
    m = cfg.get("mqtt") or {}
    client = _mqtt_client(cfg, "watch")
    state_lock = threading.Lock()

    def on_connect(client, userdata, flags, reason_code, properties):
        topic = "%s/%s/agent/+/inbox" % (
            str(m.get("topic_prefix") or "aw/v1").strip("/"),
            cfg.get("project_id", ""))
        client.subscribe(topic, qos=1)

    def on_message(client, userdata, message):
        try:
            data = json.loads(message.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if data.get("project") and data["project"] != cfg.get("project_id"):
            return
        mid = str(data.get("id") or "")
        if not mid:
            return
        with state_lock:
            for target in data.get("to") or []:
                target = _safe_agent(str(target))
                path = _inbox_dir(root, target) / ("%s.json" % mid)
                if not path.exists():
                    write_json(path, data)
            _scan_wake(root)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(str(m["host"]), int(m.get("port", 8883)),
                   int(m.get("keepalive", 30)))
    client.loop_start()
    _publish_presence(root, cfg, client)
    return client

def _send_local(root: Path, ident: dict, to: list[str], kind: str, body: str,
                expect: str, subject: str = "", mid: str | None = None) -> str:
    mid = mid or secrets.token_hex(4)
    at = _now()
    for target in to:
        target = _safe_agent(target)
        msg = {
            "id": mid,
            "from": ident["agent_id"],
            "to": [target],
            "at": at,
            "type": kind,
            "expect": expect,
            "body": body,
            "subject": subject,
        }
        write_json(_inbox_dir(root, target) / ("%s.json" % mid), msg)
    return mid


def cmd_msg(args) -> int:
    _reject_subagent("msg")
    root, cfg = load_config(args)
    ident = _identity(args)
    _record_session(root, ident)
    if args.action == "report":
        rows = _active_presence(root)
        planners = [str(r["agent"]) for r in rows
                    if str(r.get("role") or "") == "planner" and str(r.get("agent")) != ident["agent_id"]]
        targets = planners or [str(r["agent"]) for r in rows
                               if str(r.get("agent")) != ident["agent_id"]]
        if not targets:
            raise ToolError("NO_ACTIVE_AGENTS: 没有可报备的 Planner 或 active agent", 3)
        args.to = ",".join(targets)
        args.action = "send"
    if args.action == "send":
        to = [x.strip() for x in (args.to or "").split(",") if x.strip()]
        if not to:
            raise ToolError("--to 不能为空", 2)
        body = (args.body or "").strip()
        if not body:
            raise ToolError("--body 不能为空", 2)
        expect = args.expect or _default_expect(args.type)
        mid = secrets.token_hex(4)
        _send_local(root, ident, to, args.type, body, expect, args.subject or "", mid=mid)
        transport = cfg.get("transport", {}) if isinstance(cfg.get("transport"), dict) else {}
        mode = str(transport.get("mode") or "auto")
        mqtt_cfg = _mqtt_config(cfg)
        if mode == "mqtt" and not mqtt_cfg:
            raise ToolError("transport.mode=mqtt，但 mqtt 未配置", 2)
        wire_msg = {
            "id": mid, "project": cfg.get("project_id", ""),
            "from": ident["agent_id"], "to": to, "at": _now(),
            "type": args.type, "expect": expect,
            "subject": args.subject or "", "body": body,
        }
        bus_sha = ""
        if _bus_enabled(cfg) and (mode in ("bus", "auto") or transport.get("audit_bus", True)):
            try:
                bus_sha = _bus_write(root, cfg, wire_msg)
                _bus_push(root, cfg)
            except ToolError as exc:
                print("warn: bus 写入失败，消息仅本地可见: %s" % exc, file=sys.stderr)
        if mqtt_cfg and mode in ("mqtt", "auto"):
            if not _project_ok(cfg):
                if mode == "mqtt":
                    raise ToolError("project_id 与 git remote 不一致，拒绝 MQTT", 1)
                print("warn: project_id 不一致，跳过 MQTT，已写 bus", file=sys.stderr)
            else:
                try:
                    _mqtt_publish_message(cfg, wire_msg, bus_sha)
                except Exception as exc:
                    if mode == "mqtt":
                        print("MQTT 发送失败: %s" % exc, file=sys.stderr)
                        return 1
                    print("warn: MQTT 发送失败，已降级 bus: %s" % exc, file=sys.stderr)
        print("SENT %s" % mid)
        return 0
    if args.action == "inbox":
        messages = _messages(root, ident["agent_id"])
        if not args.all:
            read = _read_ids(root, ident["agent_id"])
            messages = [m for m in messages if str(m.get("id")) not in read]
        if args.limit:
            messages = messages[:args.limit]
        if args.json:
            print(json.dumps([{k: v for k, v in m.items() if k != "_path"}
                              for m in messages], ensure_ascii=False, indent=2))
        else:
            if not messages:
                print("（无消息）")
            for m in messages:
                print("%s\t%s\t%s\t%s\t%s\t%s" % (
                    m.get("id"), m.get("at"), m.get("from"),
                    m.get("type"), m.get("expect"), m.get("subject") or ""))
        if messages and not args.peek:
            ids = _read_ids(root, ident["agent_id"])
            ids |= {str(m["id"]) for m in messages}
            _save_read_ids(root, ident["agent_id"], ids)
        return 0
    if args.action == "ack":
        mid = (args.id or "").strip()
        if not mid:
            raise ToolError("用法: msg ack <id>", 2)
        found = None
        for m in _messages(root, ident["agent_id"]):
            if str(m.get("id")) == mid:
                found = m
                break
        if not found:
            print("NOT_FOUND %s" % mid)
            return 3
        found["ack_at"] = _now()
        found["acked_by"] = ident["agent_id"]
        msg_path = Path(found.pop("_path"))
        write_json(msg_path, found)
        if found.get("from") and found["from"] != ident["agent_id"]:
            _send_local(root, ident, [found["from"]], "ack", "ACK %s" % mid,
                        "none", "ACK")
        print("ACKED %s" % mid)
        return 0
    if args.action == "wait":
        timeout = max(1, int(args.timeout or 120))
        deadline = time.time() + timeout
        while True:
            unread = _unread(root, ident["agent_id"])
            if unread:
                if args.json:
                    print(json.dumps(unread, ensure_ascii=False, indent=2))
                else:
                    for m in unread:
                        print("%s\t%s\t%s\t%s" % (m["id"], m["from"], m["type"],
                                                  m.get("subject") or ""))
                if args.consume:
                    ids = _read_ids(root, ident["agent_id"])
                    ids |= {str(m["id"]) for m in unread}
                    _save_read_ids(root, ident["agent_id"], ids)
                return 0
            if time.time() >= deadline:
                print("NO_MESSAGES")
                return 3
            time.sleep(1)
    raise ToolError("未知 msg 操作: %s" % args.action, 2)


# ---------------------------------------------------------------- wake

def _pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        # os.kill(pid, 0) 对已退出但句柄未释放的进程可能返回成功。
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return bool(ok) and code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _watch_state_path(root: Path) -> Path:
    return root / STATE_DIR / "watch-state.json"


def _wake_seen_path(root: Path, agent: str) -> Path:
    return root / STATE_DIR / "wake-seen" / ("%s.json" % agent)


def _scan_wake(root: Path, seed_read: bool = False) -> list[dict]:
    inbox = root / STATE_DIR / "inbox"
    if not inbox.is_dir():
        return []
    events = []
    for folder in sorted(inbox.iterdir()):
        if not folder.is_dir():
            continue
        agent = folder.name
        seen_data = read_json(_wake_seen_path(root, agent), {})
        seen = set(str(x) for x in (seen_data.get("ids") or []))
        if seed_read:
            seen |= _read_ids(root, agent)
        messages = _messages(root, agent)
        fresh = [m for m in messages if str(m.get("id")) not in seen]
        if not fresh:
            if seed_read:
                write_json(_wake_seen_path(root, agent), {"ids": sorted(seen)[-2000:]})
            continue
        summaries = [{
            "id": m.get("id"), "from": m.get("from"), "type": m.get("type"),
            "expect": m.get("expect"), "subject": m.get("subject") or "",
            "at": m.get("at"),
        } for m in fresh[-20:]]
        write_json(root / STATE_DIR / "wake" / ("%s.json" % agent),
                   {"agent": agent, "updated_at": _now(), "messages": summaries})
        seen |= {str(m.get("id")) for m in fresh}
        write_json(_wake_seen_path(root, agent), {"ids": sorted(seen)[-2000:]})
        events.append({"agent": agent, "messages": summaries})
    return events


def _watch_status(root: Path) -> int:
    data = read_json(_watch_state_path(root), {})
    pid = int(data.get("pid") or 0)
    if not _pid_alive(pid):
        print("WATCH_STOPPED")
        return 0
    age = _dt.datetime.now().timestamp() - float(data.get("heartbeat") or 0)
    print("WATCH_RUNNING pid=%s age=%ds" % (pid, max(0, int(age))))
    return 0


def _watch_stop(root: Path) -> int:
    data = read_json(_watch_state_path(root), {})
    pid = int(data.get("pid") or 0)
    stop = root / STATE_DIR / "watch.stop"
    if not _pid_alive(pid):
        stop.unlink(missing_ok=True)
        print("WATCH_STOPPED")
        return 0
    # 先请求自停，避免 Windows detach 进程 taskkill 的时序问题
    stop.write_text("stop\n", encoding="utf-8")
    for _ in range(100):
        time.sleep(0.1)
        if not _pid_alive(pid):
            stop.unlink(missing_ok=True)
            print("WATCH_STOPPED pid=%s" % pid)
            return 0
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, check=False, **_win_no_window())
        else:
            os.kill(pid, 15)
    except OSError:
        pass
    for _ in range(30):
        time.sleep(0.1)
        if not _pid_alive(pid):
            stop.unlink(missing_ok=True)
            print("WATCH_STOPPED pid=%s" % pid)
            return 0
    stop.unlink(missing_ok=True)
    print("WATCH_STOP_FAILED pid=%s" % pid, file=sys.stderr)
    return 1


def _run_watch_once(root: Path, args, seed_read: bool = False) -> int:
    _update_presence(root)
    _root_cfg = load_config(args)[1]
    try:
        _bus_import(root, _root_cfg)
    except ToolError as exc:
        print("warn: bus 同步失败: %s" % exc, file=sys.stderr)
    events = _scan_wake(root, seed_read=seed_read)
    if args.json:
        for event in events:
            print(json.dumps(event, ensure_ascii=False), flush=True)
    else:
        for event in events:
            for m in event["messages"]:
                print("WAKE %s %s %s" % (event["agent"], m.get("id"), m.get("type")),
                      flush=True)
    if args.exec:
        for event in events:
            env = dict(os.environ)
            env["AW_WAKE_AGENT"] = event["agent"]
            env["AW_WAKE_MSG_ID"] = str(event["messages"][0].get("id", ""))
            env["AW_WAKE_TYPE"] = str(event["messages"][0].get("type", ""))
            env["AW_WAKE_FROM"] = str(event["messages"][0].get("from", ""))
            subprocess.Popen(args.exec, shell=True, env=env, cwd=str(root),
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, **_win_no_window())
    return 0 if events else 3


def cmd_path(args) -> int:
    root, _cfg = load_config(args)
    target = Path(args.path).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    target = target.resolve()
    try:
        rel = target.relative_to(root.resolve())
    except ValueError:
        print("DENIED outside local-root: %s" % target, file=sys.stderr)
        return 1
    if ".git" in rel.parts:
        print("DENIED .git path: %s" % rel, file=sys.stderr)
        return 1
    print("ALLOWED %s" % (rel.as_posix() if str(rel) != "." else "."))
    return 0


def cmd_watch(args) -> int:
    _reject_subagent("watch")
    root, cfg = load_config(args)
    if args.status:
        return _watch_status(root)
    if args.stop:
        return _watch_stop(root)
    if args.ensure:
        (root / STATE_DIR / "watch.stop").unlink(missing_ok=True)
        state = read_json(_watch_state_path(root), {})
        if _pid_alive(int(state.get("pid") or 0)):
            print("WATCH_RUNNING pid=%s" % state["pid"])
            return 0
        cmd = [sys.executable, str(Path(__file__).resolve()), "watch",
               "--interval", str(args.interval)]
        if args.exec:
            cmd += ["--exec", args.exec]
        if args.json:
            cmd.append("--json")
        log = root / STATE_DIR / "watch.log"
        err = root / STATE_DIR / "watch.err.log"
        out_handle = open(log, "a", encoding="utf-8")
        err_handle = open(err, "a", encoding="utf-8")
        try:
            kwargs = {"cwd": str(root), "stdin": subprocess.DEVNULL,
                      "stdout": out_handle, "stderr": err_handle}
            if os.name == "nt":
                flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
                flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                kwargs["startupinfo"] = _win_startupinfo()
                proc = subprocess.Popen(cmd, creationflags=flags, **kwargs)
            else:
                kwargs["start_new_session"] = True
                proc = subprocess.Popen(cmd, **kwargs)
        finally:
            out_handle.close()
            err_handle.close()
        for _ in range(80):
            time.sleep(0.25)
            if proc.poll() is not None:
                break
            state = read_json(_watch_state_path(root), {})
            if _pid_alive(int(state.get("pid") or 0)):
                print("WATCH_STARTED pid=%s" % state["pid"])
                return 0
        print("WATCH_START_FAILED 见 %s" % err, file=sys.stderr)
        return 1
    transport = cfg.get("transport", {}) if isinstance(cfg.get("transport"), dict) else {}
    mode = str(transport.get("mode") or "auto")
    mqtt_cfg = _mqtt_config(cfg)
    if mode == "mqtt" and not mqtt_cfg:
        raise ToolError("transport.mode=mqtt，但 mqtt 未配置", 2)
    if args.once:
        client = None
        if mqtt_cfg and mode in ("mqtt", "auto") and _project_ok(cfg):
            try:
                client = _start_mqtt_bridge(root, cfg)
            except Exception as exc:
                if mode == "mqtt":
                    print("MQTT 连接失败: %s" % exc, file=sys.stderr)
                    return 1
                print("warn: MQTT 连接失败，使用 bus: %s" % exc, file=sys.stderr)
        result = _run_watch_once(root, args, seed_read=True)
        if client is not None:
            try:
                client.disconnect()
                client.loop_stop()
            except Exception:
                pass
        return result
    state_path = _watch_state_path(root)
    (root / STATE_DIR / "watch.stop").unlink(missing_ok=True)
    state = read_json(state_path, {})
    write_json(state_path, {"pid": os.getpid(), "started_at": _now(),
                            "heartbeat": time.time(), "interval": args.interval})
    client = None
    if mqtt_cfg and mode in ("mqtt", "auto"):
        if not _project_ok(cfg):
            if mode == "mqtt":
                print("project_id 与 git remote 不一致，拒绝 MQTT", file=sys.stderr)
                return 1
            print("warn: project_id 不一致，使用 bus", file=sys.stderr)
        else:
            try:
                client = _start_mqtt_bridge(root, cfg)
            except Exception as exc:
                if mode == "mqtt":
                    print("MQTT 连接失败: %s" % exc, file=sys.stderr)
                    return 1
                print("warn: MQTT 连接失败，使用 bus: %s" % exc, file=sys.stderr)
    error_streak = 0
    last_error = ""

    def _heartbeat() -> None:
        try:
            write_json(state_path, {
                "pid": os.getpid(),
                "started_at": state.get("started_at") or _now(),
                "heartbeat": time.time(),
                "interval": args.interval,
            })
        except OSError as exc:
            print("warn: 写 watch 心跳失败: %s" % exc, file=sys.stderr)

    def _run_cycle(seed: bool = False) -> None:
        nonlocal error_streak, last_error
        try:
            _run_watch_once(root, args, seed_read=seed)
            error_streak = 0
            last_error = ""
        except Exception as exc:
            error_streak += 1
            msg = "%s: %s" % (type(exc).__name__, exc)
            if msg != last_error or error_streak in (1, 10, 100):
                import traceback
                traceback.print_exc()
                print("warn: watch cycle failed (#%d): %s"
                      % (error_streak, msg), file=sys.stderr)
            last_error = msg
        finally:
            _heartbeat()

    try:
        _run_cycle(seed=True)
        while True:
            time.sleep(max(1, args.interval))
            if (root / STATE_DIR / "watch.stop").exists():
                (root / STATE_DIR / "watch.stop").unlink(missing_ok=True)
                return 0
            _run_cycle()
            if client is not None:
                try:
                    _publish_presence(root, cfg, client)
                except Exception as exc:
                    print("warn: presence 发布失败: %s" % exc, file=sys.stderr)
    except KeyboardInterrupt:
        return 0
    finally:
        if client is not None:
            try:
                client.disconnect()
                client.loop_stop()
            except Exception:
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aw_single.py", description="单机双仓 Agent 协作")
    parser.add_argument("--config", default=None, help=".aw/config.json 或其目录")
    parser.add_argument("--agent", default=None, help="agent_id（优先于 AW_AGENT_ID）")
    parser.add_argument("--session", default=None, help="session_id")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="初始化本地 .aw 配置")
    p_init.add_argument("--root", default=".", help="本地根目录，默认当前目录")
    p_init.add_argument("--code-root", required=True)
    p_init.add_argument("--docs-root", required=True)
    p_init.add_argument("--base-branch", default="develop")
    p_init.add_argument("--worktree-root", default=None)
    p_init.add_argument("--branch-prefix", default="feature/")
    p_init.add_argument("--demand-dir", default="demands")
    p_init.add_argument("--transport", choices=["auto", "mqtt", "bus", "local"], default="auto")
    p_init.add_argument("--mqtt-host", default="", help="MQTT broker 主机；省略=仅本地")
    p_init.add_argument("--mqtt-port", type=int, default=8883)
    p_init.add_argument("--mqtt-no-tls", action="store_true", help="不使用 TLS（不推荐）")
    p_init.add_argument("--mqtt-username", default="")
    p_init.add_argument("--mqtt-ca", default="")
    p_init.add_argument("--mqtt-client-id", default="")
    p_init.set_defaults(func=cmd_init)

    p_who = sub.add_parser("whoami")
    p_who.set_defaults(func=cmd_whoami)

    p_handoff = sub.add_parser("handoff", help="交接当前 agent：写 handoff 文件，保留 claim")
    p_handoff.add_argument("--note", default="", help="换班原因 / 上下文")
    p_handoff.add_argument("--next-step", default="", help="下一步")
    p_handoff.add_argument("--json", action="store_true")
    p_handoff.set_defaults(func=cmd_handoff)

    p_resume = sub.add_parser("resume", help="新会话恢复：读 handoff，不消费消息")
    p_resume.add_argument("--json", action="store_true")
    p_resume.set_defaults(func=cmd_resume)

    p_q = sub.add_parser("queue")
    p_q.add_argument("action", choices=["add", "list"])
    p_q.add_argument("req", nargs="?", default="")
    p_q.add_argument("--title", default="")
    p_q.set_defaults(func=cmd_queue)

    p_c = sub.add_parser("claim")
    p_c.add_argument("action", choices=["next", "take", "release", "adopt", "list", "doctor"])
    p_c.add_argument("req", nargs="?", default="")
    p_c.add_argument("--branch", default="")
    p_c.add_argument("--force", action="store_true")
    p_c.add_argument("--remove-worktree", action="store_true")
    p_c.set_defaults(func=cmd_claim)

    p_m = sub.add_parser("msg", help="本地消息")
    p_m.add_argument("action", choices=["send", "report", "inbox", "ack", "wait"])
    p_m.add_argument("id", nargs="?", default="")
    p_m.add_argument("--to", default="")
    p_m.add_argument("--type", default="fyi")
    p_m.add_argument("--body", default="")
    p_m.add_argument("--subject", default="")
    p_m.add_argument("--expect", default="")
    p_m.add_argument("--all", action="store_true")
    p_m.add_argument("--peek", action="store_true")
    p_m.add_argument("--consume", action="store_true")
    p_m.add_argument("--limit", type=int, default=0)
    p_m.add_argument("--timeout", type=int, default=120)
    p_m.add_argument("--json", action="store_true")
    p_m.set_defaults(func=cmd_msg)

    p_bus = sub.add_parser("bus", help="Git bus 审计")
    p_bus.add_argument("action", choices=["log", "show"])
    p_bus.add_argument("id", nargs="?", default="")
    p_bus.set_defaults(func=cmd_bus)

    p_project = sub.add_parser("project", help="项目身份（MQTT 用）")
    p_project.add_argument("action", choices=["id", "alias", "check"])
    p_project.set_defaults(func=cmd_project)

    p_presence = sub.add_parser("presence", help="查看本地 agent 在线状态")
    p_presence.add_argument("--json", action="store_true")
    p_presence.set_defaults(func=cmd_presence)

    p_path = sub.add_parser("path", help="写入路径边界检查")
    p_path.add_argument("action", choices=["check"])
    p_path.add_argument("path")
    p_path.set_defaults(func=cmd_path)

    p_w = sub.add_parser("watch", help="本地消息唤醒")
    p_w.add_argument("--once", action="store_true")
    p_w.add_argument("--ensure", action="store_true")
    p_w.add_argument("--status", action="store_true")
    p_w.add_argument("--stop", action="store_true")
    p_w.add_argument("--interval", type=int, default=5)
    p_w.add_argument("--exec", default="")
    p_w.add_argument("--json", action="store_true")
    p_w.set_defaults(func=cmd_watch)

    for sp in sub.choices.values():
        sp.add_argument("--agent", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--session", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        sp.add_argument("--config", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    _init_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "session", None):
        os.environ["AW_SESSION_ID"] = args.session
    try:
        return args.func(args)
    except ToolError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code
    except OSError as exc:
        print("系统错误: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
