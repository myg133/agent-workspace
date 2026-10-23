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

import json
import os
import subprocess
import sys
from pathlib import Path

AW = Path(__file__).resolve().parent / "aw.py"
AGENT = (os.environ.get("AW_AGENT_ID") or "").strip()
VERSION = "1.0.0"
PROTOCOL = "2024-11-05"


def log(*args) -> None:
    print(*args, file=sys.stderr, flush=True)


def run_aw(argv: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if AGENT:
        env["AW_AGENT_ID"] = AGENT
    env.setdefault("AW_AGENT_PID", str(os.getpid()))
    env.setdefault("AW_SESSION_ID", "proc-%d" % os.getpid())
    return subprocess.run(
        [sys.executable, str(AW), *argv],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, timeout=timeout, cwd=os.getcwd(),
    )


def tool(name: str, description: str, props: dict, required: list[str] | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": props,
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
    tool("claim_next", "原子认领队首需求；已有认领或存在未读消息时拒绝",
         {"ignore_unread": {**BOOL, "description": "忽略未读消息强制认领"}}),
    tool("claim_take", "认领指定需求（同样受 WIP=1 限制）", {"req": STR}, ["req"]),
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
    tool("contract_check", "检查契约版本 pin、consumer 覆盖与未 ack 变更",
         {"strict": BOOL, "no_fetch": BOOL, "json": BOOL}),
    tool("verify", "校验 workspace 硬约束", {"strict": BOOL, "json": BOOL}),
    tool("audit", "只读巡检：拓扑、僵尸 worktree、stale session",
         {"stale_minutes": INT}),
    tool("queue_add", "把需求加入待认领队列", {"req": STR, "title": STR}, ["req"]),
    tool("queue_list", "查看待认领队列", {}),
    tool("queue_sync", "从 BA/demands 扫描“已就绪”入队", {}),
]


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
    if name == "claim_next":
        return ["claim", "next"] + (["--ignore-unread"] if a.get("ignore_unread") else [])
    if name == "claim_take":
        return ["claim", "take", a["req"]]
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
        for key in ("cc", "subject", "ref", "contract", "version", "deadline", "thread", "priority"):
            if a.get(key):
                argv += ["--" + key, str(a[key])]
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


def call_tool(name: str, args: dict) -> dict:
    if not AGENT:
        return {
            "content": [{"type": "text", "text":
                         "MISSING_AGENT_ID\n"
                         "本 MCP 服务没有收到 AW_AGENT_ID。\n"
                         "请在每个 agent 的启动环境里设置：AW_AGENT_ID=pcA-ba-1"}],
            "isError": True,
        }
    try:
        argv = build_argv(name, args)
    except (KeyError, ValueError) as exc:
        return {"content": [{"type": "text", "text": "参数错误: %s" % exc}], "isError": True}
    try:
        proc = run_aw(argv)
    except subprocess.TimeoutExpired:
        return {"content": [{"type": "text", "text": "命令超时: %s" % name}], "isError": True}

    payload = {
        "ok": proc.returncode in (0, 3, 4),
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "agent": AGENT,
    }
    # 3/4 是业务状态（ALREADY_HOLDING / UNREAD_MESSAGES），当作正常返回
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "isError": proc.returncode not in (0, 3, 4),
    }


def reply(msg_id, result=None, error=None) -> None:
    body = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        body["error"] = error
    else:
        body["result"] = result
    sys.stdout.write(json.dumps(body, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(msg: dict) -> None:
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        reply(msg_id, {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "aw-mcp", "version": VERSION},
        })
        return
    if method in ("notifications/initialized", "notifications/cancelled"):
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
    log("aw-mcp %s starting; agent=%s pid=%d" % (VERSION, AGENT or "(missing)", os.getpid()))
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
