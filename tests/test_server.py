import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from babel_agent.agent import Agent
from babel_agent.server import make_handler
from babel_agent.tools import Workspace


class Offline:
    def models(self):
        raise ValueError("Ollama offline")


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        agent = Agent(root / "test.db", Workspace(root / "files"), Offline())
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(agent, "test-token"))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def test_requires_token_and_rejects_foreign_origin(self):
        for headers in ({}, {"X-Babel-Token": "test-token", "Origin": "https://evil.example"},
                        {"X-Babel-Token": "test-token", "Host": "evil.example"}):
            with self.subTest(headers=headers), self.assertRaises(HTTPError) as error:
                urlopen(Request(self.url + "/api/status", headers=headers))
            self.assertEqual(error.exception.code, 403)
            error.exception.close()

    def test_offline_status_and_session_creation(self):
        headers = {"X-Babel-Token": "test-token", "Content-Type": "application/json"}
        with urlopen(Request(self.url + "/api/status", headers=headers)) as response:
            data = json.load(response)
        self.assertEqual(data["models"], [])
        self.assertEqual(data["error"], "Ollama offline")
        with urlopen(Request(self.url + "/api/sessions", data=b"{}", headers=headers)) as response:
            self.assertIsNone(json.load(response)["pending"])

    def test_ui_and_security_headers(self):
        with urlopen(self.url) as response:
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            self.assertIn(b"test-token", response.read())
