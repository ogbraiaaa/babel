"""Loopback-only web application. Run with python -m babel_agent."""

import argparse
import json
import mimetypes
import secrets
import sqlite3
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .agent import Agent
from .ollama import Ollama
from .tools import Workspace

WEB = Path(__file__).parent / "web"


def make_handler(agent, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Do not log prompts or file contents.

        def reply(self, status, data, content_type="application/json; charset=utf-8"):
            body = json.dumps(data, ensure_ascii=False).encode() if not isinstance(data, bytes) else data
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def allowed(self, api=False):
            expected = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != expected:
                self.reply(403, {"error": "Host não permitido. Use o endereço 127.0.0.1 informado no terminal."})
                return False
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + expected:
                self.reply(403, {"error": "Origem não permitida."})
                return False
            if api and not secrets.compare_digest(self.headers.get("X-Babel-Token", ""), token):
                self.reply(403, {"error": "Sessão inválida. Recarregue a página."})
                return False
            return True

        def do_GET(self):
            path = urlparse(self.path).path
            if not self.allowed(path.startswith("/api/")):
                return
            try:
                if path == "/api/status":
                    try:
                        models, error = agent.client.models(), None
                    except ValueError as exc:
                        models, error = [], str(exc)
                    root = agent.workspace.root
                    display = "~/" + root.relative_to(Path.home()).as_posix() if root.is_relative_to(Path.home()) else str(root)
                    self.reply(200, {"models": models, "error": error, "workspace": display})
                elif path == "/api/sessions":
                    self.reply(200, agent.sessions())
                elif path.startswith("/api/sessions/"):
                    self.reply(200, agent.get(path.rsplit("/", 1)[-1]))
                elif path in ("/", "/app.js", "/style.css", "/favicon.svg"):
                    file = WEB / ("index.html" if path == "/" else path[1:])
                    data = file.read_bytes().replace(b"__BABEL_TOKEN__", token.encode())
                    self.reply(200, data, mimetypes.guess_type(str(file))[0] or "text/plain")
                else:
                    self.reply(404, {"error": "Não encontrado."})
            except (ValueError, OSError, sqlite3.Error) as exc:
                self.reply(400, {"error": str(exc)})

        def do_POST(self):
            if not self.allowed(True):
                return
            try:
                if self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Envie JSON.")
                size = int(self.headers.get("Content-Length", 0))
                if size < 2 or size > 100000:
                    raise ValueError("Requisição fora do limite de tamanho.")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("Objeto JSON esperado.")
                if self.path == "/api/sessions":
                    result = agent.new()
                elif self.path == "/api/chat":
                    result = agent.chat(data["session"], data["message"], data["model"])
                elif self.path == "/api/approve":
                    if type(data.get("approved")) is not bool:
                        raise ValueError("Decisão inválida.")
                    result = agent.approve(data["session"], data["approval"], data["approved"])
                else:
                    self.reply(404, {"error": "Não encontrado."})
                    return
                self.reply(200, result)
            except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
                self.reply(400, {"error": str(exc)})
    return Handler


def main():
    parser = argparse.ArgumentParser(description="Babel — seu agente pessoal de IA local")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=Path.home() / ".babel")
    parser.add_argument("--workspace", type=Path, help="Pasta que o agente pode acessar")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    workspace = Workspace(args.workspace or args.data_dir / "workspace")
    agent = Agent(args.data_dir / "babel.sqlite3", workspace, Ollama())
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(agent, secrets.token_urlsafe(32)))
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"\n  BABEL · Seu agente local\n\n  Painel: {url}\n  Arquivos: {workspace.root}\n\n  Ctrl+C para encerrar.\n", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
