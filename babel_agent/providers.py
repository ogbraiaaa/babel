"""Local models and the OpenRouter free-model router."""

import copy
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .ollama import Ollama

FREE_MODEL = "openrouter/free"


def cloud_messages(messages):
    """Translate persisted Ollama-style tool calls, including older sessions."""
    result = copy.deepcopy(messages)
    pending = []
    for index, message in enumerate(result):
        if message.get("tool_calls"):
            pending = []
            for offset, call in enumerate(message["tool_calls"]):
                call["id"] = call.get("id") or f"call_{index}_{offset}"
                call["type"] = "function"
                arguments = call["function"].get("arguments", {})
                if not isinstance(arguments, str):
                    call["function"]["arguments"] = json.dumps(arguments)
                pending.append(call["id"])
        if message["role"] == "tool":
            if not pending:
                raise ValueError("Histórico de ferramentas incompleto. Inicie uma nova conversa.")
            message["tool_call_id"] = pending.pop(0)
            message.pop("tool_name", None)
    return result


class Providers:
    def __init__(self):
        self.local = Ollama()
        self.key = os.environ.get("OPENROUTER_API_KEY", "").strip()

    def models(self):
        try:
            models = self.local.models()
        except ValueError:
            if not self.key:
                raise ValueError("Abra o Ollama ou configure OPENROUTER_API_KEY para modelos gratuitos online.")
            models = []
        if self.key:
            models.append(FREE_MODEL)
        return models

    def chat(self, model, messages, tools):
        if model != FREE_MODEL:
            return self.local.chat(model, messages, tools)
        if not self.key:
            raise ValueError("Configure OPENROUTER_API_KEY e reinicie a Babel.")
        payload = {"model": FREE_MODEL, "messages": cloud_messages(messages),
                   "tools": tools, "stream": False, "provider": {"require_parameters": True}}
        request = Request("https://openrouter.ai/api/v1/chat/completions",
                          data=json.dumps(payload).encode(),
                          headers={"Authorization": "Bearer " + self.key,
                                   "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=180) as response:
                result = json.load(response)
        except HTTPError as exc:
            messages_by_code = {
                401: "Chave OpenRouter inválida. Confira OPENROUTER_API_KEY.",
                402: "O provedor recusou a cota gratuita. Confira sua conta OpenRouter.",
                429: "Limite gratuito atingido. Aguarde ou selecione um modelo local.",
            }
            raise ValueError(messages_by_code.get(exc.code, f"OpenRouter indisponível (HTTP {exc.code}). Tente novamente mais tarde.")) from exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            raise ValueError("Não foi possível conectar ao OpenRouter. Tente novamente.") from exc
        try:
            message = result["choices"][0]["message"]
            normalized = {"role": "assistant", "content": message.get("content") or ""}
            calls = copy.deepcopy(message.get("tool_calls") or [])
            for call in calls:
                arguments = call["function"].get("arguments", "{}")
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if not isinstance(arguments, dict):
                    raise ValueError("Argumentos de ferramenta inválidos.")
                call["function"]["arguments"] = arguments
            if calls:
                normalized["tool_calls"] = calls
            return normalized
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError("Resposta inválida do OpenRouter. Tente novamente.") from exc
