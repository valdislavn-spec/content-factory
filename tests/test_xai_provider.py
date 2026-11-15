"""xAI/Grok подключён как именованный OpenAI-совместимый провайдер."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest import mock

from content_factory.nlp.llm import OpenAICompatibleLLM, _build_llm, _named_provider_config


def test_xai_defaults() -> None:
    config = _named_provider_config(None, "xai")
    assert config["base_url"] == "https://api.x.ai/v1"
    assert config["api_key_env"] == "XAI_API_KEY"
    assert config["model"] == "grok-4.7"


def test_xai_client_uses_key_and_openai_compatible_endpoint() -> None:
    settings = SimpleNamespace(llm={"providers": {}})
    with mock.patch.dict(os.environ, {"XAI_API_KEY": "test-key"}, clear=True):
        client = _build_llm("xai", settings)
    assert isinstance(client, OpenAICompatibleLLM)
    assert client.name == "xai"
    assert client.available is True
    assert client.base_url == "https://api.x.ai/v1"
    assert client.model == "grok-4.7"
