from __future__ import annotations

import unittest
from json import loads

import httpx

from talking_telegram_bot.clients.ollama_client import OllamaClient, OllamaClientError
from talking_telegram_bot.models.messages import UserMessage


class OllamaClientTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_generate_reply_reads_message_content(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/chat")
            return httpx.Response(
                200,
                json={"message": {"role": "assistant", "content": "signal"}},
            )

        http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        )
        client = OllamaClient(
            base_url="http://ollama.local",
            model="test-model",
            timeout_seconds=10,
            http_client=http_client,
        )

        reply = await client.generate_reply(UserMessage(text="ping"))

        self.assertEqual(reply.text, "signal")
        await http_client.aclose()

    async def test_generate_reply_uses_switched_model(self) -> None:
        requested_models = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested_models.append(loads(request.content)["model"])
            return httpx.Response(
                200,
                json={"message": {"role": "assistant", "content": "ok"}},
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = OllamaClient(
            base_url="http://ollama.local",
            model="model-a",
            timeout_seconds=10,
            http_client=http_client,
        )

        client.switch_model("model-b")
        await client.generate_reply(UserMessage(text="ping"))

        self.assertEqual(requested_models, ["model-b"])
        await http_client.aclose()

    async def test_list_model_names_reads_tags_response(self) -> None:
        http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "models": [
                            {"name": "model-b"},
                            {"name": "model-a"},
                        ],
                    },
                ),
            ),
        )
        client = OllamaClient(
            base_url="http://ollama.local",
            model="test-model",
            timeout_seconds=10,
            http_client=http_client,
        )

        model_names = await client.list_model_names()

        self.assertEqual(model_names, ["model-a", "model-b"])
        await http_client.aclose()

    async def test_generate_reply_raises_for_invalid_payload(self) -> None:
        http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"message": {}}),
            ),
        )
        client = OllamaClient(
            base_url="http://ollama.local",
            model="test-model",
            timeout_seconds=10,
            http_client=http_client,
        )

        with self.assertRaises(OllamaClientError):
            await client.generate_reply(UserMessage(text="ping"))

        await http_client.aclose()
