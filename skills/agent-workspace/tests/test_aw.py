#!/usr/bin/env python3
"""Agent Workspace 自测套件。

运行：
    python -m unittest discover -s skills/agent-workspace/tests -v
只依赖 git 与 Python 标准库；全部在临时目录里跑，不碰当前仓库。
"""

from __future__ import annotations

import json
import os
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
            call = mcp_exchange(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                       "params": {"name": "agent_whoami", "arguments": {}}})
            payload = json.loads(call["result"]["content"][0]["text"])
            self.assertEqual(payload["exit_code"], 0)
            self.assertIn("ba-1", payload["stdout"])
            self.assertFalse(call["result"]["isError"])
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
