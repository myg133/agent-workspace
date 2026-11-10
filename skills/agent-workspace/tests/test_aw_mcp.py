#!/usr/bin/env python3
"""aw_mcp.py 身份绑定与主动通知的自测。

运行：
    python -m unittest discover -s skills/agent-workspace/tests -v
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

MCP = Path(__file__).resolve().parent.parent / "scripts" / "aw_mcp.py"


def send(proc, obj):
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def _lines(proc) -> "queue.Queue[str]":
    """每个进程只起一个读线程，避免超时后残留的 reader 抢走下一行。"""
    box = getattr(proc, "_lines", None)
    if box is None:
        box = queue.Queue()
        setattr(proc, "_lines", box)

        def reader():
            try:
                for line in proc.stdout:
                    box.put(line)
            except Exception:
                pass
            box.put("")

        threading.Thread(target=reader, daemon=True).start()
    return box


def read_line(proc, timeout):
    try:
        line = _lines(proc).get(timeout=timeout)
    except queue.Empty:
        return None
    return line.strip() or None


def spawn(wake_dir, agent=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith("AW_")}
    env["AW_WAKE_DIR"] = str(wake_dir)
    if agent:
        env["AW_AGENT_ID"] = agent
    proc = subprocess.Popen(
        [sys.executable, str(MCP)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        cwd=str(wake_dir), env=env,
    )
    send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"}}})
    assert read_line(proc, 10) is not None, "initialize 无响应"
    send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    return proc


def shutdown(proc):
    proc.kill()
    proc.wait(timeout=10)
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        try:
            stream.close()
        except Exception:
            pass


def write_wake(wake_dir, agent, msg_id):
    path = Path(wake_dir) / ("%s.json" % agent)
    path.write_text(json.dumps({"agent": agent, "messages": [
        {"id": msg_id, "from": "peer", "type": "question", "expect": "reply",
         "at": "2026-11-10T00:00:00Z"}]}), encoding="utf-8")


def call_schema(proc, agent):
    send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "schema", "arguments": {"agent_id": agent}}})
    return json.loads(read_line(proc, 30))


class McpNotifyTest(unittest.TestCase):
    def test_identity_from_env_starts_watch(self):
        with tempfile.TemporaryDirectory() as dirname:
            proc = spawn(dirname, agent="ba-env")
            try:
                time.sleep(1)
                write_wake(dirname, "ba-env", "m-env")
                frame = read_line(proc, 8)
                self.assertIsNotNone(frame, "env 身份未收到通知")
                self.assertEqual(json.loads(frame)["params"]["data"]["id"], "m-env")
            finally:
                shutdown(proc)

    def test_identity_from_first_call_starts_watch(self):
        """没有 AW_AGENT_ID 时，首次 tools/call 的 agent_id 应绑定为通知身份。"""
        with tempfile.TemporaryDirectory() as dirname:
            proc = spawn(dirname)  # 无 env 身份
            try:
                time.sleep(1)
                result = call_schema(proc, "ba-lazy")
                self.assertFalse(result["result"].get("isError"), result)
                self.assertEqual(json.loads(result["result"]["content"][0]["text"])["agent"],
                                 "ba-lazy")
                write_wake(dirname, "ba-lazy", "m-lazy")
                frame = read_line(proc, 8)
                self.assertIsNotNone(frame, "首次调用未启动通知线程")
                self.assertEqual(json.loads(frame)["params"]["data"]["id"], "m-lazy")
            finally:
                shutdown(proc)

    def test_no_identity_means_no_notify(self):
        with tempfile.TemporaryDirectory() as dirname:
            proc = spawn(dirname)
            try:
                time.sleep(1)
                write_wake(dirname, "ba-none", "m-none")
                self.assertIsNone(read_line(proc, 3), "无身份不应发通知")
            finally:
                proc.kill()
                proc.wait(timeout=10)
                err = proc.stderr.read()
                shutdown(proc)
            self.assertIn("未绑定身份", err)

    def test_late_different_agent_keeps_binding(self):
        """同进程换 agent_id 只影响该次调用，不改绑通知身份。"""
        with tempfile.TemporaryDirectory() as dirname:
            proc = spawn(dirname)
            try:
                time.sleep(1)
                call_schema(proc, "ba-first")
                result = call_schema(proc, "ba-second")
                self.assertEqual(json.loads(result["result"]["content"][0]["text"])["agent"],
                                 "ba-second")
                write_wake(dirname, "ba-second", "m-second")
                self.assertIsNone(read_line(proc, 3), "不应给第二个身份发通知")
                write_wake(dirname, "ba-first", "m-first")
                frame = read_line(proc, 8)
                self.assertIsNotNone(frame, "原绑定身份应继续收到通知")
                self.assertEqual(json.loads(frame)["params"]["data"]["id"], "m-first")
            finally:
                shutdown(proc)


if __name__ == "__main__":
    unittest.main()
