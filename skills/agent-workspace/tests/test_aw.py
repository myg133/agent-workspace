#!/usr/bin/env python3
"""Agent Workspace 自测套件。

运行：
    python -m unittest discover -s skills/agent-workspace/tests -v
只依赖 git 与 Python 标准库；全部在临时目录里跑，不碰当前仓库。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AW = Path(__file__).resolve().parent.parent / "scripts" / "aw.py"


def run(args, cwd, agent="ba-test", extra_env=None):
    env = dict(os.environ)
    env.pop("AW_AGENT_ID", None)
    env.pop("AW_SESSION_ID", None)
    for key in ("WT_SESSION", "TERM_SESSION_ID", "TMUX_PANE", "SSH_TTY", "TTY"):
        env.pop(key, None)
    if agent:
        env["AW_AGENT_ID"] = agent
        env["AW_SESSION_ID"] = "sess-" + agent
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(AW), *args],
        cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env,
    )


def git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


MCP = AW.parent / "aw_mcp.py"


def mcp_exchange(proc, payload):
    proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


class WorkspaceCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awtest-"))
        self.repo = self.tmp / "proj"
        out = run(["init", str(self.repo), "--name", "Test"], self.tmp)
        self.assertEqual(out.returncode, 0, out.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- 基础布局 ----
    def test_init_layout(self):
        files = git(["ls-files"], self.repo).stdout.split()
        self.assertEqual(sorted(files), [".gitignore", "README.md"])
        wt = git(["worktree", "list", "--porcelain"], self.repo).stdout
        self.assertIn("branch refs/heads/develop", wt)
        self.assertIn("branch refs/heads/demand", wt)
        self.assertIn("branch refs/heads/deploy", wt)
        self.assertTrue((self.repo / "BA" / "dispatch" / "agent-registry.md").exists())

    @staticmethod
    def _stop_mcp(proc):
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                stream.close()
            except Exception:
                pass

    def _mcp(self, agent="ba-1"):
        env = {k: v for k, v in os.environ.items()
               if k not in ("AW_AGENT_ID", "AW_SESSION_ID", "AW_AGENT_PID")}
        if agent:
            env["AW_AGENT_ID"] = agent
        return subprocess.Popen(
            [sys.executable, str(MCP)], cwd=str(self.repo), env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )

    def test_mcp_handshake_and_whoami(self):
        proc = self._mcp()
        try:
            init = mcp_exchange(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                       "params": {"protocolVersion": "2024-11-05"}})
            self.assertEqual(init["result"]["serverInfo"]["name"], "aw-mcp")
            tools = mcp_exchange(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            names = {t["name"] for t in tools["result"]["tools"]}
            self.assertIn("claim_next", names)
            self.assertIn("msg_send", names)
            self.assertIn("msg_wait", names)
            self.assertIn("msg_list", names)
            self.assertIn("doctor", names)
            self.assertIn("stats", names)
            self.assertIn("schema", names)
            call = mcp_exchange(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                       "params": {"name": "agent_whoami", "arguments": {}}})
            payload = json.loads(call["result"]["content"][0]["text"])
            self.assertEqual(payload["exit_code"], 0)
            self.assertIn("ba-1", payload["stdout"])
            self.assertFalse(call["result"]["isError"])
        finally:
            self._stop_mcp(proc)

    def test_schema_lists_tools(self):
        out = run(["schema"], self.repo, agent=None)
        data = json.loads(out.stdout)
        self.assertIn("version", data)
        names = {t["name"] for t in data["mcp_tools"]}
        self.assertIn("claim_next", names)
        self.assertIn("schema", names)
        cli = {c["name"] for c in data["cli_only"]}
        self.assertIn("watch", cli)

    def test_doctor_and_stats(self):
        clean = run(["doctor"], self.repo, agent=None)
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        run(["queue", "add", "REQ-001"], self.repo, agent="ba-1")
        run(["claim", "next"], self.repo, agent="ba-1")
        run(["msg", "send", "--to", "all", "--type", "question",
             "--ref", "REQ-001", "--body", "这样拆行不行？"], self.repo, agent="ba-1")
        out = run(["stats", "--json"], self.repo, agent=None)
        data = json.loads(out.stdout)
        self.assertEqual(data["claims_active"], 1)
        self.assertEqual(data["worktrees"], 5)
        self.assertEqual(data["questions_total"], 1)
        self.assertEqual(data["questions_by_req"]["REQ-001"], 1)
        self.assertEqual(data["questions_per_req"], 1.0)

    def test_roster_mode_solo_and_team(self):
        run(["agent", "register", "ba-1", "--role", "ba"], self.repo / "BA", agent=None)
        solo = run(["agent", "roster", "--json"], self.repo, agent=None)
        self.assertEqual(json.loads(solo.stdout)["mode"], "solo")
        run(["agent", "register", "planner-1", "--role", "planner"],
            self.repo / "BA", agent=None)
        team = run(["agent", "roster", "--json"], self.repo, agent=None)
        self.assertEqual(json.loads(team.stdout)["mode"], "team")

    def test_self_register_pending_until_activated(self):
        boot = run(["agent", "bootstrap", "planner-1"], self.repo / "BA", agent=None)
        token = re.search(r"TOKEN planner-1 ([0-9a-f]+)", boot.stdout).group(1)
        reg = run(["agent", "register", "ba-1", "--role", "ba"],
                  self.repo / "BA", agent=None)
        self.assertIn("pending", reg.stdout)
        blocked = run(["msg", "send", "--to", "all", "--body", "x"], self.repo, agent="ba-1")
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("尚未激活", blocked.stderr)
        act = run(["agent", "activate", "ba-1", "--agent-token", token],
                  self.repo / "BA", agent=None)
        self.assertEqual(act.returncode, 0, act.stderr)
        ok = run(["msg", "send", "--to", "all", "--body", "x"], self.repo, agent="ba-1")
        self.assertEqual(ok.returncode, 0, ok.stderr)

    def test_agent_register_issues_token(self):
        out = run(["agent", "register", "ba-1", "--issue-token"], self.repo / "BA", agent=None)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("TOKEN ba-1", out.stdout)
        data = json.loads((self.repo / "BA" / "plan" / "agents.json").read_text(encoding="utf-8"))
        self.assertTrue(data["agents"][0]["token_hash"])

    def test_cli_requires_token(self):
        run(["agent", "register", "ba-1", "--token", "s3cret"], self.repo / "BA", agent=None)
        blocked = run(["agent", "whoami"], self.repo, agent="ba-1")
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("BAD_TOKEN", blocked.stderr)
        ok = run(["agent", "whoami", "--agent-token", "s3cret"], self.repo, agent="ba-1")
        self.assertEqual(ok.returncode, 0, ok.stderr)

    def test_mcp_requires_valid_token(self):
        run(["agent", "register", "ba-1", "--token", "s3cret"],
            self.repo / "BA", agent=None)
        proc = self._mcp(agent=None)
        try:
            bad = self._mcp_tool(proc, "agent_whoami", {"agent_id": "ba-1"})
            self.assertTrue(bad["result"]["isError"])
            self.assertIn("BAD_TOKEN", bad["result"]["content"][0]["text"])
            good = self._mcp_tool(proc, "agent_whoami",
                                  {"agent_id": "ba-1", "token": "s3cret"}, rid=12)
            payload = json.loads(good["result"]["content"][0]["text"])
            self.assertEqual(payload["exit_code"], 0, payload)
            self.assertFalse(good["result"]["isError"])
        finally:
            self._stop_mcp(proc)

    def test_mcp_doctor_tool(self):
        proc = self._mcp()
        try:
            call = self._mcp_tool(proc, "doctor", {})
            payload = json.loads(call["result"]["content"][0]["text"])
            self.assertEqual(payload["exit_code"], 0, payload)
            self.assertIn("workspace", payload["stdout"])
        finally:
            self._stop_mcp(proc)

    def test_mcp_per_call_agent_id(self):
        proc = self._mcp(agent=None)
        try:
            call = self._mcp_tool(proc, "agent_whoami", {"agent_id": "pcA-ba-1"})
            payload = json.loads(call["result"]["content"][0]["text"])
            self.assertEqual(payload["exit_code"], 0, payload)
            self.assertIn("pcA-ba-1", payload["stdout"])
            self.assertEqual(payload["agent"], "pcA-ba-1")
        finally:
            self._stop_mcp(proc)

    def test_mcp_requires_agent_id(self):
        proc = self._mcp(agent=None)
        try:
            call = mcp_exchange(proc, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                       "params": {"name": "agent_whoami", "arguments": {}}})
            self.assertTrue(call["result"]["isError"])
            self.assertIn("MISSING_AGENT_ID", call["result"]["content"][0]["text"])
        finally:
            self._stop_mcp(proc)

    def _mcp_tool(self, proc, name, args, rid=10):
        return mcp_exchange(proc, {"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                                   "params": {"name": name, "arguments": args}})

    def test_mcp_install_config(self):
        cfg = self.tmp / "claude.json"
        out = run(["mcp", "install", "--client", "claude", "--path", str(cfg)], self.repo, agent=None)
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(cfg.read_text(encoding="utf-8"))
        entry = data["mcpServers"]["aw"]
        self.assertTrue(Path(entry["command"]).exists())
        again = run(["mcp", "install", "--client", "claude", "--path", str(cfg)], self.repo, agent=None)
        self.assertEqual(again.returncode, 0)
        self.assertIn("ALREADY", again.stdout)

    def test_mcp_install_dry_run(self):
        cfg = self.tmp / "dry.json"
        out = run(["mcp", "install", "--client", "claude", "--path", str(cfg), "--dry-run"],
                  self.repo, agent=None)
        self.assertEqual(out.returncode, 0)
        self.assertIn("WOULD INSTALL", out.stdout)
        self.assertFalse(cfg.exists())

    def test_mcp_register_and_roster(self):
        proc = self._mcp()
        try:
            reg = self._mcp_tool(proc, "agent_register", {"name": "pcA-ba-1", "role": "ba"})
            payload = json.loads(reg["result"]["content"][0]["text"])
            self.assertEqual(payload["exit_code"], 0, payload)
            roster = self._mcp_tool(proc, "agent_roster", {}, rid=11)
            data = json.loads(json.loads(roster["result"]["content"][0]["text"])["stdout"])
            self.assertEqual(data["agents"][0]["id"], "pcA-ba-1")
        finally:
            self._stop_mcp(proc)

    def test_agent_publish_commits_roster(self):
        run(["agent", "register", "pcA-ba-1"], self.repo / "BA", agent=None)
        out = run(["agent", "publish"], self.repo, agent=None)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("COMMITTED_LOCAL", out.stdout)
        log = git(["log", "--oneline", "-1"], self.repo / "BA").stdout
        self.assertIn("agent 名册", log)

    def test_verify_clean(self):
        out = run(["verify"], self.repo)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_verify_detects_pollution(self):
        (self.repo / "leak.md").write_text("x", encoding="utf-8")
        git(["add", "-f", "leak.md"], self.repo)
        out = run(["verify"], self.repo)
        self.assertEqual(out.returncode, 1)
        self.assertIn("FAIL", out.stdout)

    # ---- 认领 ----
    def test_claim_wip_is_one(self):
        run(["queue", "add", "REQ-001"], self.repo)
        run(["queue", "add", "REQ-002"], self.repo)
        first = run(["claim", "next"], self.repo, agent="ba-1")
        self.assertIn("CLAIMED", first.stdout)
        second = run(["claim", "next"], self.repo, agent="ba-1")
        self.assertEqual(second.returncode, 3)
        self.assertIn("ALREADY_HOLDING", second.stdout)

    def test_claim_survives_restart(self):
        run(["queue", "add", "REQ-001"], self.repo)
        run(["claim", "next"], self.repo, agent="ba-1")
        again = run(["claim", "next"], self.repo, agent="ba-1",
                    extra_env={"AW_SESSION_ID": "restarted-session"})
        self.assertIn("ALREADY_HOLDING", again.stdout)

    def test_claim_concurrent_distinct(self):
        for i in range(1, 4):
            run(["queue", "add", "REQ-%03d" % i], self.repo)
        procs = []
        for i in range(1, 4):
            env = {k: v for k, v in os.environ.items()
                   if k not in ("WT_SESSION", "TERM_SESSION_ID", "TMUX_PANE", "SSH_TTY", "TTY")}
            env.update(AW_AGENT_ID="slot-%d" % i, AW_SESSION_ID="s%d" % i,
                       WT_SESSION="test-term-%d" % i)
            procs.append(subprocess.Popen(
                [sys.executable, str(AW), "claim", "next"], cwd=str(self.repo),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", env=env))
        results = [(p.communicate(), p.returncode) for p in procs]
        outs = [r[0][0] for r in results]
        claimed = sorted(line.split()[1] for line in outs for line in [line] if "CLAIMED" in line)
        self.assertEqual(len(claimed), 3, [(o, e, rc) for ((o, e), rc) in results])
        self.assertEqual(len(set(claimed)), 3, outs)

    # ---- 身份 ----
    def test_missing_agent_id(self):
        out = run(["claim", "next"], self.repo, agent=None)
        self.assertEqual(out.returncode, 2, out.stdout)
        self.assertIn("MISSING_AGENT_ID", out.stderr)

    def _register(self, *names):
        for name in names:
            out = run(["agent", "register", name], self.repo / "BA", agent=None)
            self.assertEqual(out.returncode, 0, out.stderr)

    def test_bus_rejects_subagent_send(self):
        run(["agent", "register", "dev-1", "--role", "dev"], self.repo / "BA", agent=None)
        bad = run(["msg", "send", "--to", "all", "--body", "x"], self.repo, agent="dev-1")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("不能使用 bus", bad.stderr)

    def test_bus_rejects_aw_role_dev(self):
        bad = run(["msg", "send", "--to", "all", "--body", "x"], self.repo,
                  agent="ba-1", extra_env={"AW_ROLE": "dev"})
        self.assertEqual(bad.returncode, 1)
        self.assertIn("只允许 BA", bad.stderr)

    def test_bus_allows_planner(self):
        self._register("planner-1")
        run(["agent", "register", "planner-1", "--role", "planner"], self.repo / "BA", agent=None)
        out = run(["msg", "send", "--to", "all", "--body", "plan"], self.repo, agent="planner-1")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("SENT", out.stdout)

    def test_roster_rejects_unknown_recipient(self):
        self._register("ba-1")
        bad = run(["msg", "send", "--to", "ghost", "--body", "x"], self.repo, agent="ba-1")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("未注册", bad.stderr)

    def test_roster_rejects_inactive(self):
        self._register("ba-1", "ba-2")
        run(["agent", "deactivate", "ba-2"], self.repo / "BA", agent=None)
        bad = run(["msg", "send", "--to", "ba-2", "--body", "x"], self.repo, agent="ba-1")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("不是 active", bad.stderr)

    def test_agent_exit_unbinds(self):
        env = {"WT_SESSION": "term-exit"}
        run(["agent", "bind", "ba-1"], self.repo, agent=None, extra_env=env)
        out = run(["agent", "exit"], self.repo, agent=None, extra_env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        again = run(["agent", "whoami"], self.repo, agent=None, extra_env=env)
        self.assertEqual(again.returncode, 2)

    def test_agent_exit_refuses_with_claims(self):
        run(["queue", "add", "REQ-001"], self.repo, agent="ba-1")
        run(["claim", "next"], self.repo, agent="ba-1")
        out = run(["agent", "exit"], self.repo, agent="ba-1")
        self.assertEqual(out.returncode, 3)
        self.assertIn("认领", out.stderr)

    def test_terminal_binding_resolves(self):
        env = {"WT_SESSION": "term-test-1"}
        run(["agent", "bind", "ba-1"], self.repo, agent=None, extra_env=env)
        out = run(["agent", "whoami"], self.repo, agent=None, extra_env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ba-1", out.stdout)
        self.assertIn("terminal", out.stdout)

    def test_terminal_binding_blocks_rename(self):
        env = {"WT_SESSION": "term-test-2"}
        run(["agent", "bind", "ba-1"], self.repo, agent=None, extra_env=env)
        bad = run(["agent", "whoami", "--agent", "ba-2"], self.repo, agent=None, extra_env=env)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("已经绑定", bad.stderr)

    def test_terminal_isolated(self):
        run(["agent", "bind", "ba-1"], self.repo, agent=None, extra_env={"WT_SESSION": "term-A"})
        other = run(["agent", "whoami"], self.repo, agent=None, extra_env={"WT_SESSION": "term-B"})
        self.assertEqual(other.returncode, 2)

    def test_no_bind_allows_explicit(self):
        env = {"WT_SESSION": "term-shared"}
        run(["agent", "bind", "ba-1"], self.repo, agent=None, extra_env=env)
        out = run(["agent", "whoami", "--agent", "ba-2", "--no-bind"], self.repo, agent=None, extra_env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ba-2", out.stdout)

    def test_agent_flag_without_env(self):
        out = run(["agent", "whoami", "--agent", "ba-x"], self.repo, agent=None)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ba-x", out.stdout)

    # ---- 消息 ----
    def _make_pair(self):
        remote = self.tmp / "remote.git"
        git(["init", "-q", "--bare", str(remote)], self.tmp)
        git(["remote", "add", "origin", str(remote)], self.repo)
        git(["push", "-q", "origin", "--all"], self.repo)
        a, b = self.tmp / "A", self.tmp / "B"
        git(["clone", "-q", str(remote), str(a)], self.tmp)
        git(["clone", "-q", str(remote), str(b)], self.tmp)
        return a, b

    def test_msg_addressing(self):
        a, b = self._make_pair()
        sent = run(["msg", "send", "--to", "pcB", "--type", "fyi", "--body", "hi"], a, agent="pcA")
        self.assertEqual(sent.returncode, 0, sent.stderr)
        inbox_b = run(["msg", "inbox"], b, agent="pcB")
        self.assertIn("→ me", inbox_b.stdout)
        inbox_a = run(["msg", "inbox"], a, agent="pcA")
        self.assertNotIn("fyi", inbox_a.stdout)
        all_a = run(["msg", "list", "--all"], a, agent="pcA")
        self.assertIn("pcB", all_a.stdout)

    def test_msg_cursor(self):
        a, b = self._make_pair()
        run(["msg", "send", "--to", "pcB", "--body", "one"], a, agent="pcA")
        first = run(["msg", "inbox"], b, agent="pcB")
        self.assertIn("→ me", first.stdout)
        second = run(["msg", "inbox"], b, agent="pcB")
        self.assertIn("无消息", second.stdout)

    def test_msg_wait_immediate(self):
        run(["msg", "send", "--to", "ba-1", "--body", "ping"], self.repo, agent="ba-1")
        out = run(["msg", "wait", "--timeout", "3", "--json"], self.repo, agent="ba-1")
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertTrue(data["found"])
        self.assertEqual(data["messages"][0]["body"], "ping")

    def test_msg_wait_timeout(self):
        out = run(["msg", "wait", "--timeout", "2", "--interval", "1"], self.repo, agent="ba-1")
        self.assertEqual(out.returncode, 3)
        self.assertIn("WAIT_TIMEOUT", out.stdout)

    def test_msg_ack(self):
        a, b = self._make_pair()
        run(["msg", "send", "--to", "pcB", "--type", "contract-change",
             "--contract", "api", "--version", "2", "--body", "v2"], a, agent="pcA")
        full = run(["msg", "inbox", "--full"], b, agent="pcB").stdout
        mid = full.split("id=")[1].split()[0]
        ack = run(["msg", "ack", mid, "--ok"], b, agent="pcB")
        self.assertEqual(ack.returncode, 0, ack.stderr)
        inbox_a = run(["msg", "inbox"], a, agent="pcA")
        self.assertIn("contract-ack", inbox_a.stdout)

    def test_inbox_json(self):
        run(["msg", "send", "--to", "all", "--body", "x"], self.repo, agent="ba-1")
        out = run(["msg", "inbox", "--json", "--no-advance"], self.repo, agent="ba-1")
        data = json.loads(out.stdout)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["messages"][0]["body"], "x")
        again = run(["msg", "inbox", "--json"], self.repo, agent="ba-1")
        self.assertEqual(json.loads(again.stdout)["count"], 1)
        empty = run(["msg", "inbox", "--json"], self.repo, agent="ba-1")
        self.assertEqual(json.loads(empty.stdout)["count"], 0)

    def test_unread_gate_blocks_claim(self):
        run(["queue", "add", "REQ-001"], self.repo, agent="ba-1")
        run(["msg", "send", "--to", "ba-1", "--body", "look"], self.repo, agent="ba-1")
        blocked = run(["claim", "next"], self.repo, agent="ba-1")
        self.assertEqual(blocked.returncode, 4, blocked.stdout)
        self.assertIn("UNREAD_MESSAGES", blocked.stdout)
        run(["msg", "inbox"], self.repo, agent="ba-1")
        ok = run(["claim", "next"], self.repo, agent="ba-1")
        self.assertIn("CLAIMED", ok.stdout)

    def _inject(self, text, name="injected.md"):
        outbox = self.repo / ".aw" / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        (outbox / name).write_text(text, encoding="utf-8")
        run(["msg", "flush"], self.repo, agent="ba-1")

    def test_inbox_out_of_order_not_lost(self):
        run(["msg", "send", "--to", "ba-1", "--body", "first"], self.repo, agent="ba-1")
        run(["msg", "inbox"], self.repo, agent="ba-1")
        text = "\n".join([
            "[msg] fyi clock-skew -> ba-1", "", "---", "id: deadbeef",
            "from: ba-2", "to: [ba-1]", "at: 2026-10-20T00:00:00Z", "type: fyi",
            "---", "older but later",
        ])
        self._inject(text)
        out = run(["msg", "inbox", "--full"], self.repo, agent="ba-1")
        self.assertIn("deadbeef", out.stdout)

    def test_inbox_limit_shows_oldest_first(self):
        for body in ("m1", "m2", "m3"):
            run(["msg", "send", "--to", "ba-1", "--body", body], self.repo, agent="ba-1")
        first = run(["msg", "inbox", "--limit", "2", "--full"], self.repo, agent="ba-1")
        self.assertIn("m1", first.stdout)
        self.assertIn("m2", first.stdout)
        self.assertNotIn("m3", first.stdout)
        second = run(["msg", "inbox", "--limit", "2", "--full"], self.repo, agent="ba-1")
        self.assertIn("m3", second.stdout)

    def test_read_state_is_per_agent(self):
        run(["msg", "send", "--to", "all", "--body", "broadcast"], self.repo, agent="ba-1")
        run(["msg", "inbox"], self.repo, agent="ba-1")
        other = run(["msg", "inbox", "--full"], self.repo, agent="ba-2")
        self.assertIn("broadcast", other.stdout)

    def test_msg_ref_must_be_relative(self):
        bad = run(["msg", "send", "--to", "all", "--body", "x",
                   "--ref", "C:\\proj\\BA\\a.md"], self.repo, agent="ba-1")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("绝对路径", bad.stderr)

    def test_msg_ref_normalizes_repo_root(self):
        run(["msg", "send", "--to", "all", "--body", "x",
             "--ref", "<repo-root>/BA/contracts/a.md"], self.repo, agent="ba-1")
        out = run(["msg", "list", "--all", "--json"], self.repo, agent="ba-1")
        self.assertIn('"ref": "BA/contracts/a.md"', out.stdout)

    def _with_remote(self):
        bare = self.tmp / "origin.git"
        git(["init", "--bare", "-q", str(bare)], self.repo)
        git(["remote", "add", "origin", str(bare)], self.repo)
        git(["push", "-q", "origin", "--all"], self.repo)
        return bare

    def test_watch_wakes_only_new(self):
        run(["msg", "send", "--to", "ba-2", "--type", "fyi", "--body", "old"],
            self.repo, agent="ba-1")
        seed = run(["watch", "--once", "--json"], self.repo, agent=None)
        self.assertEqual(seed.returncode, 0, seed.stderr)
        self.assertEqual(seed.stdout.strip(), "")
        run(["msg", "send", "--to", "ba-2", "--type", "question", "--body", "new"],
            self.repo, agent="ba-1")
        woke = run(["watch", "--once", "--json"], self.repo, agent=None)
        self.assertIn('"agent": "ba-2"', woke.stdout)
        self.assertIn('"type": "question"', woke.stdout)

    def test_next_req_sees_remote_demand(self):
        bare = self._with_remote()
        other = self.tmp / "other"
        git(["clone", "-q", str(bare), str(other)], self.repo)
        git(["checkout", "-q", "demand"], other)
        (other / "demands" / "REQ-007-x").mkdir(parents=True)
        (other / "demands" / "REQ-007-x" / "demand.md").write_text("# x", encoding="utf-8")
        git(["add", "."], other)
        git(["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "REQ-007"], other)
        git(["push", "-q", "origin", "demand"], other)
        out = run(["next-req"], self.repo, agent="ba-1")
        self.assertEqual(out.stdout.strip(), "REQ-008", out.stderr)

    def test_next_req_reserve_remote(self):
        self._with_remote()
        first = run(["next-req", "--reserve"], self.repo, agent="ba-1")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout.strip(), "REQ-001")
        reg = git(["show", "origin/demand:dispatch/req-registry.md"], self.repo).stdout
        self.assertIn("REQ-001 | _reserved_", reg)
        second = run(["next-req", "--reserve"], self.repo, agent="ba-1")
        self.assertEqual(second.stdout.strip(), "REQ-002", second.stderr)

    def test_claim_blocked_by_pending_reply(self):
        run(["msg", "send", "--to", "ba-2", "--type", "question",
             "--body", "行不行"], self.repo, agent="ba-1")
        run(["queue", "add", "REQ-001"], self.repo, agent="ba-1")
        blocked = run(["claim", "next"], self.repo, agent="ba-2")
        self.assertEqual(blocked.returncode, 4)
        self.assertIn("PENDING_REPLIES", blocked.stdout)
        run(["msg", "inbox"], self.repo, agent="ba-2")
        ok = run(["claim", "next", "--ignore-pending"], self.repo, agent="ba-2")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("CLAIMED", ok.stdout)

    def test_exit_blocked_by_pending_reply(self):
        run(["msg", "send", "--to", "ba-2", "--type", "question",
             "--body", "行不行"], self.repo, agent="ba-1")
        blocked = run(["agent", "exit"], self.repo, agent="ba-2")
        self.assertEqual(blocked.returncode, 3)
        self.assertIn("未回复", blocked.stderr)
        forced = run(["agent", "exit", "--force"], self.repo, agent="ba-2")
        self.assertEqual(forced.returncode, 0, forced.stderr)

    def test_msg_expect_pending_reply(self):
        sent = run(["msg", "send", "--to", "ba-2", "--type", "question",
                    "--body", "这样拆行不行？"], self.repo, agent="ba-1")
        mid = re.search(r"SENT(?:_LOCAL)? ([0-9a-f]+)", sent.stdout).group(1)
        show = json.loads(run(["msg", "show", mid], self.repo, agent="ba-1").stdout)
        self.assertEqual(show["expect"], "reply")
        pend = json.loads(run(["msg", "pending", "--json"], self.repo, agent="ba-2").stdout)
        self.assertEqual(pend["count"], 1)
        reply = run(["msg", "reply", mid, "--body", "可以，按这个拆"], self.repo, agent="ba-2")
        self.assertEqual(reply.returncode, 0, reply.stderr)
        pend2 = json.loads(run(["msg", "pending", "--json"], self.repo, agent="ba-2").stdout)
        self.assertEqual(pend2["count"], 0)

    def test_msg_fyi_expects_none(self):
        sent = run(["msg", "send", "--to", "ba-2", "--type", "fyi",
                    "--body", "知会一下"], self.repo, agent="ba-1")
        mid = re.search(r"SENT(?:_LOCAL)? ([0-9a-f]+)", sent.stdout).group(1)
        show = json.loads(run(["msg", "show", mid], self.repo, agent="ba-1").stdout)
        self.assertEqual(show["expect"], "none")

    def test_msg_doctor_and_lint_bad(self):
        run(["msg", "send", "--to", "ba-2", "--type", "fyi", "--body", "ok"],
            self.repo, agent="ba-1")
        tip = git(["rev-parse", "bus"], self.repo).stdout.strip()
        bad = ("id: deadbeef\nfrom: x\nto: [y]\nat: 2026-10-29T00:00:00Z\n"
               "type: status\n---\nbody")
        sha = git(["commit-tree", "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
                   "-p", tip, "-m", bad], self.repo).stdout.strip()
        git(["update-ref", "refs/heads/bus", sha], self.repo)
        doctor = run(["msg", "doctor"], self.repo, agent=None)
        self.assertEqual(doctor.returncode, 1)
        self.assertIn("invalid", doctor.stdout)
        lint = run(["msg", "lint", "--rev", sha], self.repo, agent=None)
        self.assertEqual(lint.returncode, 1)
        self.assertIn("INVALID", lint.stdout)

    def test_msg_flush_idempotent(self):
        run(["msg", "send", "--to", "ba-2", "--type", "fyi", "--body", "x"],
            self.repo, agent="ba-1")
        text = git(["log", "-1", "bus", "--format=%B"], self.repo).stdout
        outbox = self.repo / ".aw" / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        (outbox / "dup.md").write_text(text, encoding="utf-8")
        out = run(["msg", "flush"], self.repo, agent="ba-1")
        self.assertEqual(out.returncode, 0, out.stderr)
        count = git(["rev-list", "--count", "bus"], self.repo).stdout.strip()
        self.assertEqual(count, "1")

    def test_hook_install(self):
        out = run(["hook", "install"], self.repo, agent=None)
        self.assertEqual(out.returncode, 0, out.stderr)
        status = run(["hook", "status"], self.repo, agent=None)
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        rel = git(["rev-parse", "--git-path", "hooks/pre-push"], self.repo).stdout.strip()
        hook = Path(rel)
        if not hook.is_absolute():
            hook = self.repo / hook
        self.assertTrue(hook.exists())

    def test_msg_pending_groups_and_override(self):
        run(["msg", "send", "--to", "ba-2", "--type", "fyi", "--expect", "ack",
             "--body", "请确认"], self.repo, agent="ba-1")
        run(["msg", "send", "--to", "ba-2", "--type", "question",
             "--body", "怎么拆"], self.repo, agent="ba-1")
        data = json.loads(run(["msg", "pending", "--json"], self.repo, agent="ba-2").stdout)
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["groups"]["reply"], 1)
        self.assertEqual(data["groups"]["ack"], 1)
        fyi = next(m for m in data["messages"] if m["type"] == "fyi")
        self.assertTrue(fyi["override"])
        self.assertEqual(fyi["expect_default"], "none")

    def test_msg_send_downgrade_warning(self):
        out = run(["msg", "send", "--to", "ba-2", "--type", "handoff",
                   "--expect", "ack", "--body", "交接"], self.repo, agent="ba-1")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("降级", out.stderr)

    def test_msg_body_too_large_hint(self):
        bad = run(["msg", "send", "--to", "all", "--body", "x" * 2001], self.repo, agent="ba-1")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("2001", bad.stderr)
        self.assertIn("BA/demands", bad.stderr)

    def test_msg_body_ignores_fenced_paths(self):
        body = "看日志：\n\n```text\nC:\\Users\\me\\a.txt\n```\n\n是啥问题？"
        out = run(["msg", "send", "--to", "all", "--body", body], self.repo, agent="ba-1")
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_msg_body_rejects_abs_path(self):
        bad = run(["msg", "send", "--to", "all",
                   "--body", "见 C:\\Users\\me\\proj\\a.md"], self.repo, agent="ba-1")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("绝对路径", bad.stderr)

    def test_manifest_demand_dir_is_relative(self):
        run(["queue", "add", "REQ-001"], self.repo, agent="ba-1")
        run(["claim", "next"], self.repo, agent="ba-1")
        manifest = json.loads((self.repo / "feature-REQ-001" / ".feature" / "manifest.json")
                              .read_text(encoding="utf-8"))
        self.assertTrue(manifest["demand_dir"].startswith("BA/demands/"), manifest["demand_dir"])
        self.assertNotIn(":", manifest["demand_dir"])

    def test_bus_has_no_files(self):
        a, _ = self._make_pair()
        run(["msg", "send", "--to", "all", "--body", "x"], a, agent="pcA")
        tree = git(["ls-tree", "-r", "--name-only", "origin/bus"], a).stdout.strip()
        self.assertEqual(tree, "")

    def test_msg_offline_queue(self):
        a, _ = self._make_pair()
        git(["remote", "set-url", "origin", (self.tmp / "missing.git").as_uri()], a)
        out = run(["msg", "send", "--to", "all", "--body", "offline"], a, agent="pcA")
        self.assertEqual(out.returncode, 3)
        self.assertIn("QUEUED", out.stdout)
        git(["remote", "set-url", "origin", str(self.tmp / "remote.git")], a)
        flush = run(["msg", "flush"], a, agent="pcA")
        self.assertEqual(flush.returncode, 0, flush.stderr)

    # ---- 契约 ----
    def _contract(self, version="2", consumers="[pcB]"):
        base = self.repo / "BA" / "contracts" / "api"
        base.mkdir(parents=True, exist_ok=True)
        (base / "v1.md").write_text("# api v1\n- owner: pcA\n- consumers: %s\n" % consumers, encoding="utf-8")
        (base / ("v%s.md" % version)).write_text(
            "# api v%s\n- owner: pcA\n- consumers: %s\n- status: ratified\n" % (version, consumers),
            encoding="utf-8")
        (base / "CURRENT").write_text("v%s" % version, encoding="utf-8")

    def _feature(self, name="feature-REQ-001", agent="pcB", pins=None):
        git(["worktree", "add", name, "-b", "feature/%s" % name.replace("feature-", ""), "develop"], self.repo)
        d = self.repo / name / ".feature"
        d.mkdir(parents=True, exist_ok=True)
        payload = {"req": name.replace("feature-", ""), "agent_id": agent}
        if pins is not None:
            payload["contracts"] = pins
        (d / "manifest.json").write_text(__import__("json").dumps(payload), encoding="utf-8")

    def test_contract_pin_behind(self):
        self._contract("2")
        self._feature(pins={"api": 1})
        out = run(["contract", "check", "--no-fetch"], self.repo)
        self.assertEqual(out.returncode, 1)
        self.assertIn("pin v1 < current v2", out.stdout)

    def test_contract_clean(self):
        self._contract("2")
        self._feature(pins={"api": 2})
        out = run(["contract", "check", "--no-fetch"], self.repo)
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_contract_missing_pin(self):
        self._contract("2")
        self._feature(pins={})
        out = run(["contract", "check", "--no-fetch"], self.repo)
        self.assertEqual(out.returncode, 1)
        self.assertIn("未在 manifest 里 pin", out.stdout)

    def test_contract_missing_version_file(self):
        self._contract("2")
        (self.repo / "BA" / "contracts" / "api" / "v2.md").unlink()
        out = run(["contract", "check", "--no-fetch"], self.repo)
        self.assertEqual(out.returncode, 1)
        self.assertIn("不存在", out.stdout)

    # ---- 升级检查 ----
    def test_upgrade_clean(self):
        out = run(["upgrade"], self.repo)
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_upgrade_detects_missing(self):
        (self.repo / "BA" / "dispatch" / "rules.md").unlink()
        (self.repo / "workspaces").mkdir()
        out = run(["upgrade"], self.repo)
        self.assertEqual(out.returncode, 1)
        self.assertIn("workspaces/", out.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
