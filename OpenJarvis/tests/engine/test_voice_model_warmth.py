"""Verify local model retention reaches every actual Ollama request path."""

import json

import httpx
import pytest
from openjarvis.core.types import Message, Role
from openjarvis.engine.ollama import OllamaEngine


def test_sync_chat_sends_retention_and_respects_explicit_unload(monkeypatch):
    monkeypatch.setenv("JARVIS_KEEP_ALIVE", "30m")
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "ok"}})

    engine = OllamaEngine(host="http://local")
    engine._client.close()
    engine._client = httpx.Client(
        base_url="http://local", transport=httpx.MockTransport(handle)
    )
    try:
        engine.generate([Message(role=Role.USER, content="Hi")], model="local")
        engine.generate(
            [Message(role=Role.USER, content="Hi")], model="local", keep_alive=0
        )
    finally:
        engine.close()
    assert seen[0]["keep_alive"] == "30m"
    assert seen[1]["keep_alive"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["stream", "stream_full"])
async def test_both_stream_paths_retain_the_local_model(monkeypatch, method):
    monkeypatch.setenv("JARVIS_KEEP_ALIVE", "30m")
    seen = []

    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(
            200, text=json.dumps({"message": {"content": "ok"}, "done": True}) + "\n"
        )

    engine = OllamaEngine(host="http://local")
    engine._async_transport = httpx.MockTransport(handle)
    try:
        async for _ in getattr(engine, method)(
            [Message(role=Role.USER, content="Hi")], model="local"
        ):
            pass
    finally:
        engine.close()
    assert seen[0]["keep_alive"] == "30m"
