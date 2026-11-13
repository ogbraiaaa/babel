import json
import tempfile
import unittest
from pathlib import Path

from babel_agent.agent import Agent
from babel_agent.tools import Workspace


def call(name, **args):
    return {"function": {"name": name, "arguments": args}}


class FakeModel:
    def __init__(self, calls):
        self.calls = calls

    def models(self):
        return ["test-local"]

    def chat(self, model, messages, tools):
        if messages[-1]["role"] == "tool":
            return {"role": "assistant", "content": "Resultado recebido."}
        return {"role": "assistant", "content": "", "tool_calls": self.calls}


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = Workspace(self.root / "files")

    def agent(self, calls):
        return Agent(self.root / "test.sqlite3", self.workspace, FakeModel(calls))

    def test_write_requires_approval_and_cannot_be_replayed(self):
        agent = self.agent([call("create_file", path="notes/hello.md", content="Olá")])
        session = agent.chat(agent.new()["id"], "Crie uma nota", "test-local")
        self.assertFalse((self.workspace.root / "notes/hello.md").exists())
        approval = session["pending"]["id"]
        result = agent.approve(session["id"], approval, True)
        self.assertIsNone(result["pending"])
        self.assertEqual((self.workspace.root / "notes/hello.md").read_text(encoding="utf-8"), "Olá")
        with self.assertRaises(ValueError):
            agent.approve(session["id"], approval, True)

    def test_denial_cancels_remaining_actions(self):
        agent = self.agent([call("create_file", path="a.md", content="a"), call("create_file", path="b.md", content="b")])
        session = agent.chat(agent.new()["id"], "Crie", "test-local")
        result = agent.approve(session["id"], session["pending"]["id"], False)
        self.assertFalse(list(self.workspace.root.iterdir()))
        self.assertIsNone(result["pending"])

    def test_pending_survives_restart_and_blocks_new_chat(self):
        agent = self.agent([call("create_file", path="a.md", content="a")])
        session = agent.chat(agent.new()["id"], "Crie", "test-local")
        restarted = self.agent([])
        self.assertEqual(restarted.get(session["id"])["pending"], session["pending"])
        with self.assertRaises(ValueError):
            restarted.chat(session["id"], "Outro pedido", "test-local")

    def test_multiple_writes_need_individual_approval(self):
        agent = self.agent([call("create_file", path="a.md", content="a"), call("create_file", path="b.md", content="b")])
        session = agent.chat(agent.new()["id"], "Crie", "test-local")
        session = agent.approve(session["id"], session["pending"]["id"], True)
        self.assertTrue((self.workspace.root / "a.md").exists())
        self.assertFalse((self.workspace.root / "b.md").exists())
        session = agent.approve(session["id"], session["pending"]["id"], True)
        self.assertIsNone(session["pending"])

    def test_traversal_absolute_paths_and_streams_blocked(self):
        for path in ("../escape", "/etc/passwd", "C:/Windows/win.ini", "file.txt:secret", "..\\escape"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.workspace.execute("read_file", {"path": path})

    def test_existing_file_is_never_overwritten(self):
        self.workspace.execute("create_file", {"path": "a", "content": "original"}, approved=True)
        result = self.workspace.result("create_file", {"path": "a", "content": "replace"}, approved=True)
        self.assertIn("error", json.loads(result))
        self.assertEqual((self.workspace.root / "a").read_text(), "original")

    def test_move_is_approved_and_preserves_existing_destination(self):
        for name in ("a", "b"):
            (self.workspace.root / name).write_text(name)
        with self.assertRaises(ValueError):
            self.workspace.execute("move_file", {"source": "a", "destination": "c"})
        self.assertIn("error", json.loads(self.workspace.result("move_file", {"source": "a", "destination": "b"}, approved=True)))
        self.assertEqual((self.workspace.root / "b").read_text(), "b")
        self.workspace.execute("move_file", {"source": "a", "destination": "notes/c"}, approved=True)
        self.assertFalse((self.workspace.root / "a").exists())
        self.assertEqual((self.workspace.root / "notes/c").read_text(), "a")

    def test_large_file_and_unknown_tool_rejected(self):
        (self.workspace.root / "large").write_bytes(b"x" * 65537)
        with self.assertRaises(ValueError):
            self.workspace.execute("read_file", {"path": "large"})
        with self.assertRaises(ValueError):
            self.workspace.execute("shell", {"command": "echo test"})

    def test_symlink_escape_rejected(self):
        outside = self.root / "outside.txt"
        outside.write_text("secret")
        try:
            (self.workspace.root / "link").symlink_to(outside)
        except OSError:
            self.skipTest("System does not permit symlink creation")
        with self.assertRaises(ValueError):
            self.workspace.execute("read_file", {"path": "link"})


if __name__ == "__main__":
    unittest.main()
