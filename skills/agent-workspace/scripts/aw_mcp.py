#!/usr/bin/env python3
"""aw-mcp：把 aw.py 暴露成 stdio MCP 工具。

身份来自环境变量 AW_AGENT_ID（每个 agent 进程一个终端）。
本进程启动时会：
  - 记录自己的 pid 作为 agent 进程（AW_AGENT_PID）
  - 把 session 固定为 proc-<pid>（一个进程 = 一个会话）

用法（客户端配置）：
  command: python
  args: [<skill>/scripts/aw_mcp.py]
  env:  AW_AGENT_ID=pcA-ba-1

只依赖 Python 标准库；stdout 只输出 JSON-RPC，日志走 stderr。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

AW = Path(__file__).resolve().parent / "aw.py"


def _arg_value(flag: str) -> str:
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == flag and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith(flag + "="):
            return arg.split("=", 1)[1]
    return ""


AGENT = (_arg_value("--agent") or os.environ.get("AW_AGENT_ID") or "").strip()
VERSION = "1.4.0"
PROTOCOL = "2024-11-05"
_NOTIFY_FLAG = (os.environ.get("AW_MCP_NOTIFY") or "").strip().lower()
# 默认开启；AW_MCP_NOTIFY=0 / --no-notify 关闭
NOTIFY = ("--no-notify" not in sys.argv
          and _NOTIFY_FLAG not in ("0", "false", "off", "no"))
WRITE_LOCK = threading.Lock()
READY = threading.Event()
_AGENT_LOCK = threading.Lock()
_NOTIFY_STARTED = threading.Event()
_NOTIFY_SEEN: set[str] = set()


def _bind_agent(identity: str) -> None:
    """一个进程 = 一个身份。

    优先 env AW_AGENT_ID / --agent；都没有时取首次 tools/call 的 agent_id。
    这样多个 BA 共用一个 .mcp.json 也能各用各的身份（每个会话各起一个 aw_mcp 进程）。
    """
    global AGENT
    if not identity:
        return
    with _AGENT_LOCK:
        if not AGENT:
            AGENT = identity
            log("notify: 身份绑定 %s" % identity)
        elif AGENT != identity:
            log("notify: 本进程已绑定 %s，忽略 %s" % (AGENT, identity))
            return
        start = NOTIFY and not _NOTIFY_STARTED.is_set()
        if start:
            _seed_notify(AGENT)
            _NOTIFY_STARTED.set()
    if start:
        threading.Thread(target=notify_loop, daemon=True).start()


def log(*args) -> None:
    print(*args, file=sys.stderr, flush=True)


def run_aw(argv: list[str], agent: str | None = None, token: str | None = None,
           timeout: int = 180) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    identity = (agent or AGENT or "").strip()
    if identity:
        env["AW_AGENT_ID"] = identity
    if token:
        env["AW_AGENT_TOKEN"] = token
    env.setdefault("AW_AGENT_PID", str(os.getpid()))
    env["AW_FROM_MCP"] = "1"
    if not (os.environ.get("AW_SESSION_ID") or "").strip():
        for key, label in (("PI_SESSION_ID", "PI_SESSION_ID"),
                           ("DSH_SESSION_ID", "DSH_SESSION_ID"),
                           ("CLAUDE_SESSION_ID", "CLAUDE_SESSION_ID")):
            value = (os.environ.get(key) or "").strip()
            if value:
                env["AW_SESSION_ID"] = value
                env["AW_SESSION_SOURCE"] = label
                break
        else:
            env["AW_SESSION_ID"] = "proc-%d" % os.getpid()
            env["AW_SESSION_SOURCE"] = "generated"
    else:
        env["AW_SESSION_ID"] = os.environ["AW_SESSION_ID"]
        env.setdefault("AW_SESSION_SOURCE",
                       os.environ.get("AW_SESSION_SOURCE") or "AW_SESSION_ID")
    extra = {}
    if os.name == "nt":
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return subprocess.run(
        [sys.executable, str(AW), *argv],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=timeout, cwd=os.getcwd(), **extra,
    )


def tool(name: str, description: str, props: dict, required: list[str] | None = None) -> dict:
    # 每个工具都可以显式带 agent_id：桌面端没有环境变量时靠它认人
    properties = {
        "agent_id": {
            "type": "string",
            "description": "调用者身份；未设置 AW_AGENT_ID 时必填（如 pcA-ba-1）",
        },
        "token": {
            "type": "string",
            "description": "agent 令牌；注册时由 agent register 一次性打印，用于证明身份",
        },
        "session": {
            "type": "string",
            "description": "会话 id；透传给 aw.py --session（不写映射）",
        },
    }
    properties.update(props)
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


STR = {"type": "string"}
BOOL = {"type": "boolean"}
INT = {"type": "integer"}

TOOLS = [
    tool("agent_whoami", "查看当前 agent 身份、终端锚点与 roster 状态", {}),
    tool("agent_roster", "列出仓库名册中的 agent 及本地会话状态（JSON）", {}),
    tool("agent_register", "注册 agent 到仓库名册 BA/plan/agents.json",
         {"name": STR, "role": STR, "host": STR}, ["name"]),
    tool("agent_activate", "重新激活名册中的 agent", {"name": STR}, ["name"]),
    tool("agent_deactivate", "停用名册中的 agent（不再接收消息）", {"name": STR}, ["name"]),
    tool("agent_publish", "提交并推送名册到 demand 分支，让其他机器可见",
         {"message": STR}),
    tool("agent_exit", "退出：session 置 offline、解绑终端",
         {"force": BOOL, "keep_binding": BOOL}),
    tool("next_req", "计算下一个 REQ 编号；reserve=true 时在 demand 上占位",
         {"reserve": BOOL}),
    tool("claim_next", "原子认领队首需求；已有认领、未读或欠回复时拒绝",
         {"ignore_unread": {**BOOL, "description": "忽略未读消息强制认领"},
          "ignore_pending": {**BOOL, "description": "忽略未回复消息强制认领"}}),
    tool("claim_take", "认领指定需求（同样受 WIP=1 限制）",
         {"req": STR, "ignore_pending": BOOL}, ["req"]),
    tool("claim_release", "释放认领；可选回收 worktree",
         {"req": STR, "remove_worktree": BOOL, "force": BOOL}, ["req"]),
    tool("claim_list", "列出当前所有认领", {}),
    tool("claim_doctor", "巡检认领：多领、死会话、缺 worktree；可修复",
         {"repair": BOOL}),
    tool("msg_send", "发送 BA 间消息（走后端 bus 空 commit）",
         {"to": {**STR, "description": "agent_id / all / role:ba，逗号分隔"},
          "body": STR, "type": {**STR, "enum": ["fyi", "question", "blocker", "handoff",
                                                "contract-change", "contract-ack", "decision"]},
          "cc": STR, "subject": STR, "ref": STR, "contract": STR, "version": STR,
          "deadline": STR, "thread": STR, "priority": STR,
          "expect": {**STR, "enum": ["none", "ack", "reply"]},
          "reply_by": STR,
          "force": {**BOOL, "description": "跳过收件人注册校验"}},
         ["to", "body"]),
    tool("msg_inbox", "读取发给我的未读消息", {"all": BOOL, "limit": INT, "full": BOOL,
                                              "no_advance": BOOL, "json": BOOL}),
    tool("msg_wait", "阻塞等待发给我的新消息（默认 120 秒，不消费）",
         {"timeout": {**INT, "minimum": 1, "maximum": 120},
          "interval": INT, "thread": STR, "contract": STR, "type": STR,
          "sender": STR, "consume": BOOL, "json": BOOL}),
    tool("msg_show", "按 id 查看单条消息", {"id": STR}, ["id"]),
    tool("msg_ack", "对契约变更回执", {"id": STR, "reject": BOOL, "note": STR}, ["id"]),
    tool("msg_list", "列出 bus 上的消息（含已读，用于审计）",
         {"all": BOOL, "limit": INT, "json": BOOL}),
    tool("msg_pending", "列出等我还账的消息（expect=ack/reply 且尚未回复）",
         {"overdue": {**INT, "description": "只看超过 N 小时的消息"}}),
    tool("msg_reply", "回复某条消息；自动带 re / thread / 收件人",
         {"id": STR, "body": STR, "type": STR}, ["id", "body"]),
    tool("msg_flush", "把离线队列推到 bus 分支", {}),
    tool("contract_check", "检查契约版本 pin、consumer 覆盖与未 ack 变更",
         {"strict": BOOL, "no_fetch": BOOL, "json": BOOL}),
    tool("verify", "校验 workspace 硬约束", {"strict": BOOL, "json": BOOL}),
    tool("doctor", "一页巡检：workspace / 拓扑 / 认领 / 队列 / 契约", {}),
    tool("stats", "运营指标（JSON）：WIP、队列年龄、ack 中位数", {}),
    tool("agent_check", "检查当前身份、绑定与工作区是否一致", {}),
    tool("hook_install", "安装 pre-push 校验（bus 消息格式；本机一次即可）",
         {"force": BOOL}),
    tool("hook_status", "查看 pre-push 是否已安装", {}),
    tool("schema", "工具清单（JSON）：MCP 工具 + 仅 CLI 命令；不要读源码", {}),
    tool("onboard", "首次接入检查：模式 / 身份 / 名册 / hook / 待问问题", {}),
    tool("audit", "只读巡检：拓扑、僵尸 worktree、stale session",
         {"stale_minutes": INT}),
    tool("queue_add", "把需求加入待认领队列", {"req": STR, "title": STR}, ["req"]),
    tool("queue_list", "查看待认领队列", {}),
    tool("queue_sync", "从 BA/demands 扫描“已就绪”入队", {}),
]


def _pick(args: dict, *names: str):
    for name in names:
        value = args.get(name)
        if value:
            return value
    return None


def build_argv(name: str, args: dict) -> list[str]:
    a = args or {}
    if name == "agent_whoami":
        return ["agent", "whoami"]
    if name == "agent_roster":
        return ["agent", "roster", "--json"]
    if name == "agent_register":
        argv = ["agent", "register", a["name"]]
        if a.get("role"):
            argv += ["--role", a["role"]]
        if a.get("host"):
            argv += ["--host", a["host"]]
        return argv
    if name in ("agent_activate", "agent_deactivate"):
        return ["agent", "activate" if name == "agent_activate" else "deactivate", a["name"]]
    if name == "agent_publish":
        argv = ["agent", "publish"]
        if a.get("message"):
            argv += ["--message", a["message"]]
        return argv
    if name == "agent_exit":
        argv = ["agent", "exit"]
        if a.get("force"):
            argv.append("--force")
        if a.get("keep_binding"):
            argv.append("--keep-binding")
        return argv
    if name == "next_req":
        return ["next-req"] + (["--reserve"] if a.get("reserve") else [])
    if name == "claim_next":
        argv = ["claim", "next"]
        if a.get("ignore_unread"):
            argv.append("--ignore-unread")
        if a.get("ignore_pending"):
            argv.append("--ignore-pending")
        return argv
    if name == "claim_take":
        argv = ["claim", "take", a["req"]]
        if a.get("ignore_pending"):
            argv.append("--ignore-pending")
        return argv
    if name == "claim_release":
        argv = ["claim", "release", a["req"]]
        if a.get("remove_worktree"):
            argv.append("--remove-worktree")
        if a.get("force"):
            argv.append("--force")
        return argv
    if name == "claim_list":
        return ["claim", "list"]
    if name == "claim_doctor":
        return ["claim", "doctor"] + (["--repair"] if a.get("repair") else [])
    if name == "msg_send":
        argv = ["msg", "send", "--to", a["to"], "--body", a["body"]]
        if a.get("type"):
            argv += ["--type", a["type"]]
        for key in ("cc", "subject", "ref", "contract", "version", "deadline",
                    "thread", "priority"):
            if a.get(key):
                argv += ["--" + key, str(a[key])]
        reply_by = _pick(a, "reply_by", "replyBy")
        if reply_by:
            argv += ["--reply-by", str(reply_by)]
        if a.get("expect"):
            argv += ["--expect", a["expect"]]
        if a.get("force"):
            argv.append("--force")
        return argv
    if name == "msg_inbox":
        argv = ["msg", "inbox"]
        for key in ("all", "full", "no_advance", "json"):
            if a.get(key):
                argv.append("--" + key.replace("_", "-"))
        if a.get("limit"):
            argv += ["--limit", str(a["limit"])]
        return argv
    if name == "msg_wait":
        timeout = min(120, max(1, int(a.get("timeout", 120))))
        argv = ["msg", "wait", "--timeout", str(timeout), "--json"]
        if a.get("interval"):
            argv += ["--interval", str(a["interval"])]
        for key in ("thread", "contract", "type", "sender"):
            if a.get(key):
                argv += ["--" + key, str(a[key])]
        if a.get("consume"):
            argv.append("--consume")
        return argv
    if name == "msg_show":
        return ["msg", "show", a["id"], "--json"]
    if name == "msg_list":
        argv = ["msg", "list"]
        if a.get("all"):
            argv.append("--all")
        if a.get("limit"):
            argv += ["--limit", str(a["limit"])]
        argv.append("--json")
        return argv
    if name == "msg_pending":
        argv = ["msg", "pending", "--json"]
        if a.get("overdue"):
            argv += ["--overdue", str(a["overdue"])]
        return argv
    if name == "msg_reply":
        argv = ["msg", "reply", a["id"], "--body", a["body"]]
        if a.get("type"):
            argv += ["--type", a["type"]]
        return argv
    if name == "msg_flush":
        return ["msg", "flush"]
    if name == "msg_ack":
        argv = ["msg", "ack", a["id"]]
        if a.get("reject"):
            argv.append("--reject")
        if a.get("note"):
            argv += ["--note", a["note"]]
        return argv
    if name == "contract_check":
        argv = ["contract", "check"]
        for key in ("strict", "no_fetch", "json"):
            if a.get(key):
                argv.append("--" + key.replace("_", "-"))
        return argv
    if name == "doctor":
        return ["doctor"]
    if name == "stats":
        return ["stats", "--json"]
    if name == "agent_check":
        return ["agent", "check"]
    if name == "hook_install":
        return ["hook", "install"] + (["--force"] if a.get("force") else [])
    if name == "hook_status":
        return ["hook", "status"]
    if name == "schema":
        return ["schema"]
    if name == "onboard":
        return ["onboard", "--json"]
    if name == "verify":
        argv = ["verify"]
        for key in ("strict", "json"):
            if a.get(key):
                argv.append("--" + key)
        return argv
    if name == "audit":
        argv = ["audit"]
        if a.get("stale_minutes"):
            argv += ["--stale-minutes", str(a["stale_minutes"])]
        return argv
    if name == "queue_add":
        argv = ["queue", "add", a["req"]]
        if a.get("title"):
            argv += ["--title", a["title"]]
        return argv
    if name == "queue_list":
        return ["queue", "list"]
    if name == "queue_sync":
        return ["queue", "sync"]
    raise ValueError("unknown tool: %s" % name)


def _repo_root() -> Path | None:
    try:
        extra = {}
        if os.name == "nt":
            extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        out = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=os.getcwd(), capture_output=True, text=True,
            encoding="utf-8", errors="replace", **extra,
        ).stdout.strip()
        if not out:
            return None
        if os.name == "nt":
            import re
            match = re.match(r"^/([A-Za-z])/(.*)$", out)
            if match:
                return Path("%s:/%s" % (match.group(1).upper(), match.group(2))).resolve().parent
        return Path(out).resolve().parent
    except Exception:
        return None


def _roster_entry(agent: str) -> dict | None:
    root = _repo_root()
    if root is None:
        return None
    try:
        data = json.loads((root / "BA" / "plan" / "agents.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for entry in data.get("agents") or []:
        if entry.get("id") == agent:
            return entry
    return None


def _wake_path(agent: str) -> Path | None:
    env = (os.environ.get("AW_WAKE_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve() / ("%s.json" % agent)
    root = _repo_root()
    if root is None:
        return None
    return root / ".aw" / "wake" / ("%s.json" % agent)


def _wake_ids(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(m.get("id")) for m in data.get("messages") or [] if m.get("id")}


def _seed_notify(agent: str) -> None:
    """在发 initialize 之前同步 seed，避免“线程还没 seed 就来了新消息”被吞掉。"""
    path = _wake_path(agent)
    _NOTIFY_SEEN.update(_wake_ids(path) if path and path.exists() else set())


def notify_loop() -> None:
    if not NOTIFY:
        return
    if not AGENT:
        log("notify: 没有身份（env AW_AGENT_ID / --agent / 首次调用 agent_id 均未提供），通知已禁用")
        return
    path = _wake_path(AGENT)
    seen: set[str] = set(_NOTIFY_SEEN)
    if not READY.wait(timeout=30):
        log("notify: 等待 initialize 超时，通知未启动")
        return
    log("notify: watching %s" % path)
    while True:
        if path is None:
            path = _wake_path(AGENT)
        if path and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            for msg in data.get("messages") or []:
                mid = str(msg.get("id") or "")
                if not mid or mid in seen:
                    continue
                seen.add(mid)
                notify_message({
                    "agent": msg.get("agent") or AGENT,
                    "id": mid,
                    "from": msg.get("from", ""),
                    "type": msg.get("type", ""),
                    "subject": msg.get("subject", ""),
                    "expect": msg.get("expect", "none"),
                    "at": msg.get("at", ""),
                })
            if len(seen) > 1000:
                seen = set(list(seen)[-500:])
        time.sleep(2)


def call_tool(name: str, args: dict) -> dict:
    identity = (str(args.get("agent_id") or "").strip()) or AGENT
    if not identity:
        return {
            "content": [{"type": "text", "text":
                         "MISSING_AGENT_ID\n"
                         "没有 agent 身份。二选一：\n"
                         "  1) 每次调用带参数 agent_id（桌面端推荐）\n"
                         "  2) 启动环境设置 AW_AGENT_ID=pcA-ba-1"}],
            "isError": True,
        }
    _bind_agent(identity)
    entry = _roster_entry(identity) or {}
    auth_token = (str(args.get("token") or "").strip()
                  or (os.environ.get("AW_AGENT_TOKEN") or "").strip())
    if entry.get("token_hash"):
        supplied = auth_token
        if not supplied or hashlib.sha256(supplied.encode("utf-8")).hexdigest() != entry["token_hash"]:
            return {
                "content": [{"type": "text", "text":
                             "BAD_TOKEN\n"
                             "该 agent 已启用令牌校验。请带上注册时打印的 token，"
                             "或设置 AW_AGENT_TOKEN。"}],
                "isError": True,
            }
    try:
        argv = build_argv(name, args)
        prefix = ["--agent", identity]
        session = str(args.get("session") or "").strip()
        if session:
            prefix += ["--session", session]
        argv = [*prefix, *argv]
    except (KeyError, ValueError) as exc:
        return {"content": [{"type": "text", "text": "参数错误: %s" % exc}], "isError": True}
    try:
        proc = run_aw(argv, agent=identity, token=auth_token)
    except subprocess.TimeoutExpired:
        return {"content": [{"type": "text", "text": "命令超时: %s" % name}], "isError": True}

    payload = {
        "ok": proc.returncode in (0, 3, 4),
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "agent": identity,
    }
    # 3/4 是业务状态（ALREADY_HOLDING / UNREAD_MESSAGES），当作正常返回
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "isError": proc.returncode not in (0, 3, 4),
    }


def _write(obj: dict) -> None:
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    with WRITE_LOCK:
        sys.stdout.write(line)
        sys.stdout.flush()


def reply(msg_id, result=None, error=None) -> None:
    body = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        body["error"] = error
    else:
        body["result"] = result
    _write(body)


def notify_message(data: dict) -> None:
    _write({
        "jsonrpc": "2.0",
        "method": "notifications/message",
        "params": {"level": "info", "logger": "aw", "data": data},
    })


def handle(msg: dict) -> None:
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        reply(msg_id, {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL,
            "capabilities": {"tools": {}, "logging": {}},
            "serverInfo": {"name": "aw-mcp", "version": VERSION},
        })
        READY.set()
        return
    if method == "notifications/initialized":
        READY.set()
        return
    if method == "notifications/cancelled":
        return
    if method == "ping":
        reply(msg_id, {})
        return
    if method == "tools/list":
        reply(msg_id, {"tools": TOOLS})
        return
    if method == "tools/call":
        name = params.get("name")
        result = call_tool(name, params.get("arguments") or {})
        reply(msg_id, result)
        return
    if msg_id is not None:
        reply(msg_id, error={"code": -32601, "message": "method not found: %s" % method})


def main() -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    log("aw-mcp %s starting; agent=%s pid=%d notify=%s"
        % (VERSION, AGENT or "(missing)", os.getpid(), NOTIFY))
    if NOTIFY and AGENT:
        _seed_notify(AGENT)
        _NOTIFY_STARTED.set()
        threading.Thread(target=notify_loop, daemon=True).start()
    elif NOTIFY:
        log("notify: 未绑定身份，等首次 tools/call 的 agent_id 后再启动")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" not in msg:
            continue  # notification
        try:
            handle(msg)
        except Exception as exc:  # 不让单条请求打死服务
            log("error:", exc)
            reply(msg.get("id"), error={"code": -32603, "message": str(exc)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
