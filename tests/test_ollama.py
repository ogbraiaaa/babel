import unittest
from babel_agent.ollama import Ollama


class ClientTests(unittest.TestCase):
    def test_legacy_reasoning_is_not_displayed(self):
        client = Ollama()
        client.request = lambda *args, **kwargs: {"message": {
            "role": "assistant", "content": "internal reasoning</think>Olá!", "thinking": "internal"}}
        self.assertEqual(client.chat("qwen3:4b", [], []), {"role": "assistant", "content": "Olá!"})

    def test_cloud_model_rejected(self):
        with self.assertRaises(ValueError):
            Ollama().chat("model-cloud", [], [])
