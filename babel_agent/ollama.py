"""Small Ollama HTTP client using only the Python standard library."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


class Ollama:
    def __init__(self, base="http://127.0.0.1:11434"):
        self.base = base
        self.opener = build_opener(ProxyHandler({}))

    def request(self, path, payload=None, timeout=180):
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                result = json.load(response)
            if "error" in result:
                raise ValueError(result["error"])
            return result
        except HTTPError as exc:
            raise ValueError(f"Ollama retornou HTTP {exc.code}. Verifique o modelo e seu suporte a ferramentas.") from exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            raise ValueError("Ollama indisponível ou demorou demais. Abra o Ollama e tente novamente.") from exc

    def models(self):
        return [m["name"] for m in self.request("/api/tags", timeout=3).get("models", [])
                if "cloud" not in m["name"].lower() and not m.get("remote_host")]

    def chat(self, model, messages, tools):
        if not model or "cloud" in model.lower():
            raise ValueError("Escolha um modelo local instalado.")
        message = self.request("/api/chat", {"model": model, "messages": messages,
                               "tools": tools, "stream": False, "think": False})["message"]
        # Older model templates can place reasoning in content instead of thinking.
        content = message.get("content", "")
        if "</think>" in content:
            content = content.rsplit("</think>", 1)[-1].strip()
        elif "<think>" in content:
            content = content.split("<think>", 1)[0].strip()
        message["content"] = content
        message.pop("thinking", None)
        return message
