import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "aw_single.py"


def run(args, cwd, env=None):
    full = dict(os.environ)
    full.update(env or {})
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=full)


def git(args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


class SingleCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="awsingle-"))
        self.code = self.tmp / "app"
        self.docs = self.tmp / "docs"
        self.code.mkdir()
        self.docs.mkdir()
        (self.docs / "demands").mkdir()
        git(["init", "-q", "-b", "main"], self.code)
        git(["config", "user.name", "t"], self.code)
        git(["config", "user.email", "t@t"], self.code)
        (self.code / "README.md").write_text("x\n", encoding="utf-8")
        git(["add", "."], self.code)
        git(["commit", "-q", "-m", "init"], self.code)
        self.env = {"AW_AGENT_ID": "ba-1", "AW_SESSION_ID": "sess-1"}
        out = run(["init", "--root", str(self.tmp), "--code-root", str(self.code),
                   "--docs-root", str(self.docs), "--base-branch", "main"], self.tmp)
        self.assertEqual(out.returncode, 0, out.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_whoami_writes_session_map(self):
        env = dict(self.env)
        env["AW_SESSION_ID"] = ""
        env["DSH_SESSION_ID"] = "sess-map-1"
        out = run(["whoami"], self.tmp, env)
        self.assertEqual(out.returncode, 0, out.stderr)
        map_path = self.tmp / ".aw" / "sessions" / "ba-1.map.json"
        data = json.loads(map_path.read_text(encoding="utf-8"))
        self.assertEqual(data["session_id"], "sess-map-1")
        self.assertEqual(data["session_source"], "DSH_SESSION_ID")
        self.assertTrue(data["session_authoritative"])
        self.assertEqual(data["map_version"], 2)
        key = hashlib.sha256(b"sess-map-1").hexdigest()[:16]
        reverse = json.loads((self.tmp / ".aw" / "sessions" / "by-session" / (key + ".json"))
                             .read_text(encoding="utf-8"))
        self.assertEqual(reverse["agent_id"], "ba-1")

    def test_project_id_remote_normalization(self):
        git(["remote", "add", "origin", "https://github.com/Example/Demo.git"], self.code)
        first = run(["project", "id"], self.tmp)
        alias = run(["project", "alias"], self.tmp)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("github.com/Example/Demo", alias.stdout)
        git(["remote", "set-url", "origin", "git@github.com:Example/Demo.git"], self.code)
        second = run(["project", "id"], self.tmp)
        self.assertEqual(first.stdout.strip(), second.stdout.strip())

    def test_project_check_detects_mismatch(self):
        out = run(["project", "check"], self.tmp)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("PROJECT_OK", out.stdout)
        cfg_path = self.tmp / ".aw" / "config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["project_id"] = "p-wrong"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        bad = run(["project", "check"], self.tmp)
        self.assertEqual(bad.returncode, 1)
        self.assertIn("PROJECT_MISMATCH", bad.stdout)

    def test_init_mqtt_config(self):
        root2 = self.tmp / "root2"
        out = run(["init", "--root", str(root2), "--code-root", str(self.code),
                   "--docs-root", str(self.docs), "--base-branch", "main",
                   "--mqtt-host", "broker.example.com", "--mqtt-port", "8883",
                   "--mqtt-username", "aw"], self.tmp)
        self.assertEqual(out.returncode, 0, out.stderr)
        cfg = json.loads((root2 / ".aw" / "config.json").read_text(encoding="utf-8"))
        self.assertTrue(cfg["mqtt"]["enabled"])
        self.assertEqual(cfg["mqtt"]["host"], "broker.example.com")
        self.assertEqual(cfg["mqtt"]["password_env"], "AW_MQTT_PASSWORD")
        self.assertNotIn("password", cfg["mqtt"])

    def test_git_timeout_raises_tool_error(self):
        spec = importlib.util.spec_from_file_location("aw_single_timeout", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaises(module.ToolError) as ctx:
            module.git("-c", "alias.slp=!sleep 5", "slp",
                       cwd=self.tmp, timeout=0.2)
        self.assertIn("超时", str(ctx.exception))

    def test_vendored_paho_import(self):
        vendor = str(ROOT / "vendor")
        sys.path.insert(0, vendor)
        self.addCleanup(lambda: sys.path.remove(vendor) if vendor in sys.path else None)
        import paho.mqtt.client as mqtt
        self.assertIn(str(ROOT / "vendor"), str(Path(mqtt.__file__).resolve()))

    def test_init_and_whoami(self):
        cfg = json.loads((self.tmp / ".aw" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["profile"], "single")
        out = run(["whoami"], self.tmp, self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("ba-1", out.stdout)
        session = json.loads((self.tmp / ".aw" / "sessions" / "ba-1.json")
                             .read_text(encoding="utf-8"))
        self.assertEqual(session["session_id"], "sess-1")

    def test_handoff_and_resume(self):
        send_env = dict(self.env)
        send_env.update({"AW_AGENT_ID": "ba-2", "AW_SESSION_ID": "sess-2"})
        sent = run(["msg", "send", "--to", "ba-1", "--type", "question",
                    "--body", "handoff-test"], self.tmp, send_env)
        self.assertEqual(sent.returncode, 0, sent.stderr)

        old = run(["handoff", "--note", "shift end",
                   "--next-step", "answer the question", "--json"],
                  self.tmp, self.env)
        self.assertEqual(old.returncode, 0, old.stderr)
        data = json.loads(old.stdout)
        self.assertEqual(data["agent_id"], "ba-1")
        self.assertGreaterEqual(len(data["unresolved"]), 1)
        handoff_path = self.tmp / ".aw" / "handoff" / "ba-1.json"
        self.assertTrue(handoff_path.exists())
        session = json.loads((self.tmp / ".aw" / "sessions" / "ba-1.json")
                             .read_text(encoding="utf-8"))
        self.assertEqual(session.get("status"), "offline")

        new_env = dict(self.env)
        new_env["AW_SESSION_ID"] = "sess-1-new"
        new = run(["resume", "--json"], self.tmp, new_env)
        self.assertEqual(new.returncode, 0, new.stderr)
        resumed = json.loads(new.stdout)
        self.assertEqual(resumed["resumed_session_id"], "sess-1-new")
        self.assertTrue(resumed["unresolved"])

        inbox = run(["msg", "inbox", "--json"], self.tmp, new_env)
        self.assertEqual(inbox.returncode, 0, inbox.stderr)
        messages = json.loads(inbox.stdout)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["body"], "handoff-test")

    def test_claim_adopt_existing_branch_worktree(self):
        run(["queue", "add", "REQ-001"], self.tmp, self.env)
        branch = "feature/REQ-001"
        git(["branch", branch], self.code)
        worktree = self.tmp / "worktrees" / "REQ-001"
        worktree.parent.mkdir(parents=True, exist_ok=True)
        out = git(["worktree", "add", str(worktree), branch], self.code)
        self.assertEqual(out.returncode, 0, out.stderr)
        (worktree / "wip.txt").write_text("wip\n", encoding="utf-8")
        adopted = run(["claim", "adopt", "REQ-001"], self.tmp, self.env)
        self.assertEqual(adopted.returncode, 0, adopted.stderr)
        self.assertIn("ADOPTED REQ-001", adopted.stdout)
        claim = json.loads((self.tmp / ".aw" / "claims" / "REQ-001.json").read_text(encoding="utf-8"))
        self.assertEqual(claim["agent_id"], "ba-1")
        self.assertEqual(claim["branch"], branch)
        self.assertEqual(claim["worktree"], str(worktree))
        self.assertTrue(claim.get("adopted"))

    def test_path_check_boundaries(self):
        inside = run(["path", "check", str(self.tmp / "tmp.txt")], self.tmp, self.env)
        self.assertEqual(inside.returncode, 0, inside.stderr)
        self.assertIn("ALLOWED", inside.stdout)
        outside = run(["path", "check", str(Path.home() / "escape.txt")], self.tmp, self.env)
        self.assertNotEqual(outside.returncode, 0)
        self.assertIn("DENIED", outside.stderr)

    def test_subagent_blocks_messages_watch_claim(self):
        env = dict(self.env)
        env["AW_SUBAGENT"] = "1"
        for args in (["msg", "inbox"], ["watch", "--status"],
                     ["claim", "next"], ["whoami"]):
            out = run(args, self.tmp, env)
            self.assertNotEqual(out.returncode, 0, args)
            self.assertIn("SUBAGENT_NO_", out.stderr, args)

    def test_handoff_keeps_claim(self):
        self.assertEqual(run(["queue", "add", "REQ-001", "--title", "x"],
                             self.tmp, self.env).returncode, 0)
        claimed = run(["claim", "next"], self.tmp, self.env)
        self.assertEqual(claimed.returncode, 0, claimed.stderr)
        out = run(["handoff", "--json"], self.tmp, self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["current_req"], "REQ-001")
        claims = run(["claim", "list"], self.tmp, self.env)
        self.assertIn("REQ-001", claims.stdout)

    def test_resume_without_handoff(self):
        out = run(["resume", "--json"], self.tmp, self.env)
        self.assertEqual(out.returncode, 3)
        self.assertIn("NO_HANDOFF", out.stdout)

    def test_queue_and_claim_next(self):
        self.assertEqual(run(["queue", "add", "REQ-001", "--title", "x"],
                             self.tmp).returncode, 0)
        out = run(["claim", "next"], self.tmp, self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("CLAIMED REQ-001", out.stdout)
        wt = self.tmp / "worktrees" / "REQ-001"
        self.assertTrue(wt.is_dir())
        self.assertEqual(git(["branch", "--show-current"], wt).stdout.strip(),
                         "feature/REQ-001")
        again = run(["claim", "next"], self.tmp, self.env)
        self.assertEqual(again.returncode, 3)
        self.assertIn("ALREADY_HOLDING REQ-001", again.stdout)

    def test_take_and_release(self):
        self.assertEqual(run(["queue", "add", "REQ-002"], self.tmp).returncode, 0)
        out = run(["claim", "take", "REQ-002"], self.tmp, self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        rel = run(["claim", "release", "REQ-002"], self.tmp, self.env)
        self.assertEqual(rel.returncode, 0, rel.stderr)
        self.assertIn("RELEASED REQ-002", rel.stdout)
        self.assertFalse((self.tmp / ".aw" / "claims" / "REQ-002.json").exists())
        self.assertTrue(list((self.tmp / ".aw" / "archive").glob("REQ-002-*.json")))
        self.assertTrue((self.tmp / "worktrees" / "REQ-002").is_dir())

    def test_doctor_detects_missing_worktree(self):
        run(["queue", "add", "REQ-003"], self.tmp)
        self.assertEqual(run(["claim", "next"], self.tmp, self.env).returncode, 0)
        shutil.rmtree(self.tmp / "worktrees" / "REQ-003")
        out = run(["claim", "doctor"], self.tmp)
        self.assertEqual(out.returncode, 1)
        self.assertIn("missing-worktree", out.stdout)

    def test_missing_config(self):
        other = Path(tempfile.mkdtemp(prefix="awsingle-other-"))
        self.addCleanup(shutil.rmtree, other, True)
        out = run(["whoami"], other, self.env)
        self.assertEqual(out.returncode, 2)
        self.assertIn("找不到 .aw/config.json", out.stderr)

    def test_duplicate_queue(self):
        self.assertEqual(run(["queue", "add", "REQ-004"], self.tmp).returncode, 0)
        out = run(["queue", "add", "REQ-004"], self.tmp)
        self.assertEqual(out.returncode, 3)
        self.assertIn("ALREADY_QUEUED", out.stdout)

    def test_msg_send_inbox_ack(self):
        sent = run(["msg", "send", "--to", "ba-2", "--type", "question",
                    "--body", "ping"], self.tmp, self.env)
        self.assertEqual(sent.returncode, 0, sent.stderr)
        mid = sent.stdout.split()[1]
        inbox = run(["msg", "inbox"], self.tmp,
                    {"AW_AGENT_ID": "ba-2"})
        self.assertEqual(inbox.returncode, 0, inbox.stderr)
        self.assertIn(mid, inbox.stdout)
        ack = run(["msg", "ack", mid], self.tmp,
                  {"AW_AGENT_ID": "ba-2"})
        self.assertEqual(ack.returncode, 0, ack.stderr)
        self.assertIn("ACKED", ack.stdout)
        back = run(["msg", "inbox"], self.tmp, self.env)
        self.assertEqual(back.returncode, 0, back.stderr)
        self.assertIn("ACK", back.stdout)

    def test_write_json_retries_windows_sharing(self):
        spec = importlib.util.spec_from_file_location("aw_single_test", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        target = self.tmp / "retry.json"
        real_replace = mod.os.replace
        calls = []

        def flaky_replace(*args, **kwargs):
            calls.append(args)
            if len(calls) < 3:
                raise PermissionError("busy")
            return real_replace(*args, **kwargs)

        with mock.patch.object(mod.os, "name", "nt"), \
                mock.patch.object(mod.os, "replace", side_effect=flaky_replace) as replace:
            mod.write_json(target, {"ok": 1})
        self.assertEqual(replace.call_count, 3)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["ok"], 1)

    def test_req_format_relaxed(self):
        accepted = ["REQ-001", "REQ-ONT-C1", "REQ-ONT-B2", "REQ-ONT-1D"]
        for req in accepted:
            out = run(["queue", "add", req], self.tmp)
            self.assertEqual(out.returncode, 0, (req, out.stderr))
        for req in ["REQ-", "REQ--X", "REQ-ONT-", "FOO-1"]:
            out = run(["queue", "add", req], self.tmp)
            self.assertEqual(out.returncode, 2, (req, out.stdout, out.stderr))
            self.assertIn("REQ 格式", out.stderr)
        bad = run(["claim", "take", "REQ--X"], self.tmp, self.env)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("REQ 格式", bad.stderr)

    def test_bus_send_and_read(self):
        sent = run(["msg", "send", "--to", "ba-2", "--type", "fyi",
                    "--body", "bus-body"], self.tmp, self.env)
        self.assertEqual(sent.returncode, 0, sent.stderr)
        mid = sent.stdout.split()[1]
        log = run(["bus", "log"], self.tmp)
        self.assertEqual(log.returncode, 0, log.stderr)
        self.assertIn(mid, log.stdout)
        show = run(["bus", "show", mid], self.tmp)
        self.assertEqual(show.returncode, 0, show.stderr)
        self.assertIn("bus-body", show.stdout)
        branch = git(["show-ref", "--verify", "refs/heads/bus"], self.code)
        self.assertEqual(branch.returncode, 0)

    def test_msg_report_prefers_planner_then_broadcasts(self):
        presence = self.tmp / ".aw" / "presence"
        presence.mkdir(parents=True, exist_ok=True)

        def put(agent, role):
            (presence / (agent + ".json")).write_text(json.dumps({
                "agent": agent, "role": role, "status": "online",
                "session": "s-" + agent, "pid": os.getpid(),
            }), encoding="utf-8")

        put("ba-1", "ba")
        put("planner-1", "planner")
        put("ba-2", "ba")
        out = run(["msg", "report", "--subject", "new task", "--body", "REQ-001"], self.tmp, self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        planner_inbox = list((self.tmp / ".aw" / "inbox" / "planner-1").glob("*.json"))
        ba2_inbox = list((self.tmp / ".aw" / "inbox" / "ba-2").glob("*.json"))
        self.assertEqual(len(planner_inbox), 1)
        self.assertEqual(len(ba2_inbox), 0)

        (presence / "planner-1.json").unlink()
        out = run(["msg", "report", "--subject", "new task", "--body", "REQ-002"], self.tmp, self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        ba2_inbox = list((self.tmp / ".aw" / "inbox" / "ba-2").glob("*.json"))
        self.assertGreaterEqual(len(ba2_inbox), 1)

    def test_msg_wait_timeout(self):
        out = run(["msg", "wait", "--timeout", "1"], self.tmp, self.env)
        self.assertEqual(out.returncode, 3)
        self.assertIn("NO_MESSAGES", out.stdout)

    def test_watch_once_writes_wake(self):
        sent = run(["msg", "send", "--to", "ba-1", "--type", "question",
                    "--body", "wake-me"], self.tmp, {"AW_AGENT_ID": "ba-2"})
        mid = sent.stdout.split()[1]
        first = run(["watch", "--once"], self.tmp)
        self.assertEqual(first.returncode, 0, first.stderr)
        wake = self.tmp / ".aw" / "wake" / "ba-1.json"
        self.assertTrue(wake.is_file())
        self.assertIn(mid, wake.read_text(encoding="utf-8"))
        second = run(["watch", "--once"], self.tmp)
        self.assertEqual(second.returncode, 3)

    def test_presence_online_offline(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            sessions = self.tmp / ".aw" / "sessions"
            sessions.mkdir(parents=True, exist_ok=True)
            (sessions / "ba-9.json").write_text(json.dumps({
                "agent_id": "ba-9", "role": "ba", "session_id": "s-9",
                "pid": proc.pid, "host": "test", "last_seen": "2026-11-16T00:00:00+00:00",
            }), encoding="utf-8")
            online = run(["presence", "--json"], self.tmp)
            data = json.loads(online.stdout)
            self.assertEqual(data[0]["status"], "online")
        finally:
            proc.terminate()
            proc.wait(timeout=5)
        time.sleep(0.3)
        offline = run(["presence", "--json"], self.tmp)
        data = json.loads(offline.stdout)
        self.assertEqual(data[0]["status"], "offline")

    def test_watch_ensure_start_stop(self):
        started = run(["watch", "--ensure", "--interval", "1"], self.tmp)
        self.assertEqual(started.returncode, 0, started.stderr)
        status = run(["watch", "--status"], self.tmp)
        self.assertIn("WATCH_RUNNING", status.stdout)
        stopped = run(["watch", "--stop"], self.tmp)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertIn("WATCH_STOPPED", stopped.stdout)

    def test_watch_status_stopped(self):
        out = run(["watch", "--status"], self.tmp)
        self.assertIn("WATCH_STOPPED", out.stdout)


if __name__ == "__main__":
    unittest.main()
