import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from babel_agent.providers import FREE_MODEL, Providers, cloud_messages


class ProviderTests(unittest.TestCase):
    def test_legacy_history_and_multiple_calls(self):
        messages = [{"role": "assistant", "tool_calls": [
            {"function": {"name": "list_files", "arguments": {}}},
            {"function": {"name": "read_file", "arguments": {"path": "note.md"}}}]},
            {"role": "tool", "tool_name": "list_files", "content": "[]"},
            {"role": "tool", "tool_name": "read_file", "content": "hello"}]
        converted = cloud_messages(messages)
        self.assertEqual(converted[1]["tool_call_id"], converted[0]["tool_calls"][0]["id"])
        self.assertEqual(converted[2]["tool_call_id"], converted[0]["tool_calls"][1]["id"])
        self.assertIsInstance(converted[0]["tool_calls"][1]["function"]["arguments"], str)
        self.assertNotIn("id", messages[0]["tool_calls"][0])

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"})
    def test_free_router_without_ollama(self):
        client = Providers()
        with patch.object(client.local, "models", side_effect=ValueError("Offline")):
            self.assertEqual(client.models(), [FREE_MODEL])
        response = {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "abc", "function": {"name": "list_files", "arguments": "{}"}}]}}]}
        with patch("babel_agent.providers.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as request:
            result = client.chat(FREE_MODEL, [{"role": "user", "content": "oi"}], [])
        self.assertEqual(result["tool_calls"][0]["function"]["arguments"], {})
        self.assertEqual(json.loads(request.call_args.args[0].data)["model"], FREE_MODEL)

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"})
    def test_quota_error(self):
        with patch("babel_agent.providers.urlopen", side_effect=HTTPError("url", 429, "limit", {}, None)):
            with self.assertRaisesRegex(ValueError, "Limite gratuito"):
                Providers().chat(FREE_MODEL, [], [])


if __name__ == "__main__":
    unittest.main()
