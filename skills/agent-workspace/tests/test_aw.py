#!/usr/bin/env python3
"""Agent Workspace 自测套件。

运行：
    python -m unittest discover -s skills/agent-workspace/tests -v
只依赖 git 与 Python 标准库；全部在临时目录里跑，不碰当前仓库。
"""

from __future__ import annotations

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
            env = dict(os.environ, AW_AGENT_ID="slot-%d" % i, AW_SESSION_ID="s%d" % i)
            procs.append(subprocess.Popen(
                [sys.executable, str(AW), "claim", "next"], cwd=str(self.repo),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", env=env))
        outs = [p.communicate()[0] for p in procs]
        claimed = sorted(line.split()[1] for line in outs for line in [line] if "CLAIMED" in line)
        self.assertEqual(len(claimed), 3, outs)
        self.assertEqual(len(set(claimed)), 3, outs)

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
