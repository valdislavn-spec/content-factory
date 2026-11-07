"""Провайдеры моделей: mock, Ollama, OpenAI-совместимые, Gemini, GigaChat, Dify.

Все провайдеры возвращают Completion и не зависят друг от друга. Выбор
провайдера и модели для роли делает ModelRouter (см. router.py).
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .utils import approx_tokens

Message = Dict[str, str]


class ProviderError(RuntimeError):
    """Провайдер недоступен, вернул ошибку или некорректный ответ."""


@dataclass
class Completion:
    """Результат одного вызова модели."""

    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class Provider:
    """Базовый интерфейс провайдера."""

    name = "provider"

    def complete(
        self,
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 800,
        json_mode: bool = False,
    ) -> Completion:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def _post_json(
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 120,
) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(
        url, data=data, headers=request_headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise ProviderError("HTTP {}: {}".format(exc.code, detail)) from exc
    except urllib.error.URLError as exc:
        raise ProviderError("сеть недоступна: {}".format(exc.reason)) from exc
    except OSError as exc:
        raise ProviderError("ошибка соединения: {}".format(exc)) from exc
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise ProviderError("ответ не JSON: {}".format(body[:300])) from exc
    if not isinstance(parsed, dict):
        raise ProviderError("неожиданный формат ответа: {}".format(type(parsed)))
    return parsed


# ---------------------------------------------------------------------------
# Mock: детерминированная модель для демо и тестов
# ---------------------------------------------------------------------------


class MockProvider(Provider):
    """Не обращается к сети. Полезен для демо, тестов и отладки пайплайна.

    Поведение выбирается по имени модели: mock-classifier, mock-researcher,
    mock-writer, mock-critic, mock-editor.
    """

    name = "mock"

    def __init__(self, name: str = "mock"):
        self.name = name

    def complete(
        self,
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 800,
        json_mode: bool = False,
    ) -> Completion:
        started = time.time()
        role = model
        for prefix in ("mock-", "mock_"):
            if role.startswith(prefix):
                role = role[len(prefix) :]
        text = self._render(role, messages)
        prompt = "\n".join(str(m.get("content", "")) for m in messages)
        return Completion(
            text=text,
            provider=self.name,
            model=model,
            prompt_tokens=approx_tokens(prompt),
            completion_tokens=approx_tokens(text),
            latency_ms=int((time.time() - started) * 1000),
            meta={"mock": True, "role": role},
        )

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _text(messages: List[Message]) -> str:
        return "\n".join(str(m.get("content", "")) for m in messages)

    @staticmethod
    def _titles(text: str) -> List[str]:
        titles = [t.strip() for t in re.findall(r"«([^»]{8,180})»", text)]
        return [
            title
            for title in titles
            if not title.upper().startswith(("ЗАГОЛОВОК", "TITLE", "DRAFT"))
        ]

    @staticmethod
    def _indices(text: str) -> List[int]:
        seen: List[int] = []
        for value in re.findall(r"\[(\d{1,3})\]", text):
            number = int(value)
            if number not in seen:
                seen.append(number)
        return seen

    @staticmethod
    def _draft(text: str) -> str:
        match = re.search(r"DRAFT START\s*(.*?)\s*DRAFT END", text, re.S)
        if match:
            return match.group(1).strip()
        return ""

    # -- role renderers ---------------------------------------------------

    def _render(self, role: str, messages: List[Message]) -> str:
        text = self._text(messages)
        titles = self._titles(text)
        if role in ("classifier", "classify"):
            return self._classifier(text, titles)
        if role in ("researcher", "research"):
            return self._researcher(text, titles)
        if role in ("writer", "write"):
            return self._writer(text, titles)
        if role in ("critic", "critique"):
            return self._critic(text)
        if role in ("editor", "edit"):
            return self._editor(text, titles)
        return "Черновик: {}".format(titles[0] if titles else "новость дня")

    def _classifier(self, text: str, titles: List[str]) -> str:
        entities = [t.split(" ")[0] for t in titles[:3] if t]
        return json.dumps(
            {
                "topic": "технологии и ИИ",
                "tone": "нейтральный",
                "audience": "профессионалы и владельцы медиа",
                "key_entities": entities or ["ИИ", "MCP", "автоматизация"],
            },
            ensure_ascii=False,
        )

    def _researcher(self, text: str, titles: List[str]) -> str:
        available = [i for i in self._indices(text) if 1 <= i <= 50]
        if not available:
            available = [1]
        if len(available) >= 3:
            used = [available[0], available[len(available) // 2], available[-1]]
        else:
            used = available[:3]
        used = sorted(set(used))
        chosen = [
            titles[index - 1]
            for index in used
            if 0 <= index - 1 < len(titles)
        ]
        if not chosen:
            chosen = titles[:3] or ["Новости об ИИ и автоматизации"]
        numbers = re.findall(r"\d[\d\s.,]*(?:%|ГБ|ТБ|млн|млрд|тыс)", text)[:3]
        facts = [
            "{} — сюжет подтверждён как минимум одним источником.".format(t)
            for t in chosen
        ]
        return json.dumps(
            {
                "facts": facts,
                "numbers": numbers or ["38%", "10 ГБ"],
                "angles": [
                    "что это меняет для редакций и медиа",
                    "экономика производства контента",
                    "риски автоматизации без проверки фактов",
                ],
                "used": used,
                "confidence": 0.78,
            },
            ensure_ascii=False,
        )

    def _writer(self, text: str, titles: List[str]) -> str:
        title = titles[0] if titles else "ИИ-агенты меняют производство контента"
        second = titles[1] if len(titles) > 1 else "участники рынка отмечают рост автоматизации"
        body = (
            "Сегодня главное — {}. Событие выглядит частью более широкого сдвига: "
            "компании всё чаще собирают контент-процессы из нескольких моделей и "
            "инструментов, а не из одного сервиса.".format(title)
        )
        body += (
            "\n\nПо данным источников, {}. Важна не сама генерация текста, а связка: "
            "сбор данных, проверка фактов, маршрутизация задач между моделями и "
            "контроль публикации.".format(second)
        )
        body += (
            "\n\nЧто это значит для редакции: выигрывают те, кто строит проверяемый "
            "процесс, а не гонится за одной «лучшей» моделью. Разные модели закрывают "
            "разные роли — исследование, черновик, критику и редактуру."
        )
        return "ЗАГОЛОВОК: {}\n\n{}".format(title[:140], body)

    def _critic(self, text: str) -> str:
        draft = self._draft(text)
        issues: List[str] = []
        if "http" not in draft:
            issues.append("В черновике нет ссылок на источники.")
        if len(draft) < 500:
            issues.append("Черновик короткий: не хватает контекста и цифр.")
        issues.append("Первый абзац почти дублирует заголовок.")
        return json.dumps(
            {
                "verdict": "revise",
                "issues": issues,
                "fact_checks": [
                    {"claim": "событие произошло", "status": "supported"},
                    {"claim": "цифры из источников", "status": "needs_human_check"},
                ],
            },
            ensure_ascii=False,
        )

    def _editor(self, text: str, titles: List[str]) -> str:
        draft = self._draft(text)
        title = ""
        for line in draft.splitlines():
            if line.strip().upper().startswith("ЗАГОЛОВОК:"):
                title = line.split(":", 1)[1].strip()
                break
        if not title:
            title = titles[0] if titles else "ИИ-агенты меняют производство контента"
        second = titles[1] if len(titles) > 1 else "источники подтверждают тренд"
        body = (
            "Главное: {}. В фокусе — не отдельная модель, а связка MCP-инструментов "
            "и нескольких LLM, которые делят роли в контент-процессе.".format(title)
        )
        body += (
            "\n\nКонтекст: {}. Оркестратор собирает новости, исследователь выделяет "
            "факты, автор пишет черновик, критик ищет слабые места, редактор "
            "полирует текст. Каждый шаг можно проверить по логу.".format(second)
        )
        body += (
            "\n\nЧто дальше: запускать такой процесс стоит в режиме dry-run, с "
            "обязательной ссылкой на первоисточник и человеком на финальном "
            "подтверждении. Тогда автоматизация ускоряет работу, а не заменяет "
            "редакционную ответственность."
        )
        return "ЗАГОЛОВОК: {}\n\n{}".format(title[:140], body)


# ---------------------------------------------------------------------------
# Ollama (локальные модели)
# ---------------------------------------------------------------------------


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, name: str = "ollama", base_url: str = "http://127.0.0.1:11434", timeout: float = 120):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 800,
        json_mode: bool = False,
    ) -> Completion:
        started = time.time()
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        data = _post_json(self.base_url + "/api/chat", payload, timeout=self.timeout)
        message = data.get("message") or {}
        text = str(message.get("content") or "")
        if not text:
            raise ProviderError("Ollama вернула пустой ответ")
        return Completion(
            text=text,
            provider=self.name,
            model=model,
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            completion_tokens=int(data.get("eval_count") or 0),
            latency_ms=int((time.time() - started) * 1000),
            meta={"done_reason": data.get("done_reason")},
        )


# ---------------------------------------------------------------------------
# OpenAI-совместимые API (OpenAI, Together, vLLM, LM Studio, прокси)
# ---------------------------------------------------------------------------


class OpenAICompatibleProvider(Provider):
    name = "openai"

    def __init__(
        self,
        name: str = "openai",
        base_url: str = "https://api.openai.com/v1",
        api_key_env: Optional[str] = "OPENAI_API_KEY",
        timeout: float = 120,
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.extra_headers = dict(extra_headers or {})

    def complete(
        self,
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 800,
        json_mode: bool = False,
    ) -> Completion:
        started = time.time()
        headers = dict(self.extra_headers)
        if self.api_key_env:
            api_key = os.environ.get(self.api_key_env, "")
            if not api_key:
                raise ProviderError("не задана переменная окружения {}".format(self.api_key_env))
            headers["Authorization"] = "Bearer " + api_key
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = _post_json(
            self.base_url + "/chat/completions", payload, headers=headers, timeout=self.timeout
        )
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("в ответе нет choices")
        message = choices[0].get("message") or {}
        text = str(message.get("content") or "")
        if not text:
            raise ProviderError("провайдер вернул пустой текст")
        usage = data.get("usage") or {}
        return Completion(
            text=text,
            provider=self.name,
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=int((time.time() - started) * 1000),
            meta={"finish_reason": choices[0].get("finish_reason")},
        )


# ---------------------------------------------------------------------------
# Gemini API
# ---------------------------------------------------------------------------


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(
        self,
        name: str = "gemini",
        api_key_env: str = "GEMINI_API_KEY",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout: float = 120,
    ):
        self.name = name
        self.api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 800,
        json_mode: bool = False,
    ) -> Completion:
        started = time.time()
        api_key = os.environ.get(self.api_key_env, "")
        if not api_key:
            raise ProviderError("не задана переменная окружения {}".format(self.api_key_env))

        system_parts: List[str] = []
        contents: List[Dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role", "user"))
            content = str(message.get("content", ""))
            if role == "system":
                system_parts.append(content)
                continue
            contents.append(
                {
                    "role": "user" if role == "user" else "model",
                    "parts": [{"text": content}],
                }
            )
        generation_config: Dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

        url = "{}/models/{}:generateContent?key={}".format(
            self.base_url, urllib.parse.quote(model), urllib.parse.quote(api_key)
        )
        data = _post_json(url, payload, timeout=self.timeout)
        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError("Gemini не вернула candidates")
        parts = ((candidates[0].get("content") or {}).get("parts")) or []
        text = "".join(str(part.get("text", "")) for part in parts)
        if not text:
            raise ProviderError("Gemini вернула пустой ответ")
        usage = data.get("usageMetadata") or {}
        return Completion(
            text=text,
            provider=self.name,
            model=model,
            prompt_tokens=int(usage.get("promptTokenCount") or 0),
            completion_tokens=int(usage.get("candidatesTokenCount") or 0),
            latency_ms=int((time.time() - started) * 1000),
            meta={"finish_reason": candidates[0].get("finishReason")},
        )


# ---------------------------------------------------------------------------
# GigaChat (экспериментально)
# ---------------------------------------------------------------------------


class GigaChatProvider(Provider):
    """GigaChat API: OAuth + OpenAI-подобный /chat/completions.

    Экспериментальный провайдер: не покрыт тестами, потому что требует
    корпоративного аккаунта. В конфиге включайте осознанно.
    """

    name = "gigachat"

    def __init__(
        self,
        name: str = "gigachat",
        credentials_env: str = "GIGACHAT_CREDENTIALS",
        scope: str = "GIGACHAT_API_PERS",
        base_url: str = "https://gigachat.devices.sberbank.ru/api/v1",
        oauth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        timeout: float = 120,
    ):
        self.name = name
        self.credentials_env = credentials_env
        self.scope = scope
        self.base_url = base_url.rstrip("/")
        self.oauth_url = oauth_url
        self.timeout = timeout
        self._token: Optional[str] = None
        self._expires_at: float = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token
        credentials = os.environ.get(self.credentials_env, "")
        if not credentials:
            raise ProviderError("не задана переменная окружения {}".format(self.credentials_env))
        if ":" in credentials and not credentials.endswith("="):
            # По документации GigaChat ожидает base64(client_id:client_secret).
            credentials = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        body = urllib.parse.urlencode({"scope": self.scope}).encode("utf-8")
        request = urllib.request.Request(
            self.oauth_url,
            data=body,
            headers={
                "Authorization": "Basic " + credentials,
                "RqUID": str(uuid.uuid4()),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise ProviderError("GigaChat OAuth HTTP {}: {}".format(exc.code, detail)) from exc
        except urllib.error.URLError as exc:
            raise ProviderError("GigaChat OAuth: {}".format(exc.reason)) from exc
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise ProviderError("GigaChat OAuth: ответ не JSON") from exc
        token = data.get("access_token")
        if not token:
            raise ProviderError("GigaChat OAuth: нет access_token")
        self._token = str(token)
        expires_at_ms = data.get("expires_at")
        if isinstance(expires_at_ms, (int, float)):
            self._expires_at = float(expires_at_ms) / 1000.0 - 60
        else:
            self._expires_at = time.time() + 25 * 60
        return self._token

    def complete(
        self,
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 800,
        json_mode: bool = False,
    ) -> Completion:
        started = time.time()
        token = self._get_token()
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = _post_json(
            self.base_url + "/chat/completions",
            payload,
            headers={"Authorization": "Bearer " + token},
            timeout=self.timeout,
        )
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("GigaChat: в ответе нет choices")
        message = choices[0].get("message") or {}
        text = str(message.get("content") or "")
        if not text:
            raise ProviderError("GigaChat вернул пустой текст")
        usage = data.get("usage") or {}
        return Completion(
            text=text,
            provider=self.name,
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            latency_ms=int((time.time() - started) * 1000),
            meta={"finish_reason": choices[0].get("finish_reason")},
        )


# ---------------------------------------------------------------------------
# Dify (приложение Dify Cloud / self-hosted как провайдер)
# ---------------------------------------------------------------------------


class DifyProvider(Provider):
    """Приложение Dify как провайдер: Service API ``/chat-messages`` / ``/completion-messages``.

    Dify не принимает ``model``, ``temperature`` и ``max_tokens`` — они заданы в
    приложении, поэтому ``model`` из маршрута используется только как метка в
    логах и ``Completion.model``. ``messages`` склеиваются в один текст запроса:
    system-сообщения идут первыми, затем user/assistant. При ``json_mode`` к
    запросу добавляется требование вернуть валидный JSON.

    Ответ запрашивается в streaming-режиме (SSE): Agent-приложения Dify
    поддерживают только его, а blocking-запрос на Dify Cloud может оборваться
    на долгой генерации.
    """

    name = "dify"

    def __init__(
        self,
        name: str = "dify",
        base_url: str = "https://api.dify.ai/v1",
        api_key_env: str = "DIFY_API_KEY",
        app_mode: str = "chat",
        user: str = "mcp-content-factory",
        timeout: float = 180,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.app_mode = app_mode if app_mode in ("chat", "completion") else "chat"
        self.user = user
        self.timeout = timeout

    # -- запрос ----------------------------------------------------------
    @staticmethod
    def _build_query(messages: List[Message], json_mode: bool) -> str:
        system_parts: List[str] = []
        other_parts: List[str] = []
        for message in messages:
            content = str(message.get("content", ""))
            if str(message.get("role", "user")) == "system":
                system_parts.append(content)
            else:
                other_parts.append(content)
        query = "\n\n".join(part for part in system_parts + other_parts if part)
        if json_mode:
            query += (
                "\n\nВерни ответ строго в виде валидного JSON без markdown-обёрток "
                "и пояснений."
            )
        return query

    def _payload(self, query: str) -> Dict[str, Any]:
        if self.app_mode == "completion":
            return {
                "inputs": {"query": query},
                "response_mode": "streaming",
                "user": self.user,
            }
        return {
            "inputs": {},
            "query": query,
            "response_mode": "streaming",
            "user": self.user,
        }

    # -- HTTP ------------------------------------------------------------
    def _request_stream(
        self, url: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None
    ) -> str:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(
            url, data=body, headers=request_headers, method="POST"
        )
        try:
            response = urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:500]
            except Exception:  # pragma: no cover - тело ошибки может быть недоступно
                pass
            raise ProviderError("Dify HTTP {}: {}".format(exc.code, detail)) from exc
        except urllib.error.URLError as exc:
            raise ProviderError("Dify: сеть недоступна: {}".format(exc.reason)) from exc
        except OSError as exc:
            raise ProviderError("Dify: ошибка соединения: {}".format(exc)) from exc
        try:
            return self._read_stream(response)
        finally:
            try:
                response.close()
            except Exception:  # pragma: no cover
                pass

    def _read_stream(self, response: Any) -> str:
        content_type = ""
        try:
            content_type = str(response.headers.get("Content-Type") or "")
        except AttributeError:  # pragma: no cover - защита от нестандартного ответа
            content_type = ""
        if "application/json" in content_type:
            # Прокси/сервер может проигнорировать streaming и ответить JSON.
            try:
                data = json.loads(response.read().decode("utf-8", "replace"))
            except ValueError as exc:
                raise ProviderError("Dify: ответ не JSON и не SSE") from exc
            answer = str((data or {}).get("answer") or "")
            if not answer:
                raise ProviderError("Dify вернул пустой ответ")
            return answer

        message_parts: List[str] = []
        agent_parts: List[str] = []
        saw_message = False
        saw_agent = False
        finished = False
        for raw_line in response:
            try:
                line = raw_line.decode("utf-8", "replace").strip()
            except AttributeError:  # pragma: no cover
                line = str(raw_line).strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                event = json.loads(payload)
            except ValueError as exc:
                raise ProviderError("Dify: некорректный JSON в SSE-потоке") from exc
            if not isinstance(event, dict):
                continue
            kind = str(event.get("event") or "")
            if kind == "error":
                raise ProviderError(
                    "Dify: {} — {}".format(
                        event.get("code") or "error", event.get("message") or ""
                    ).rstrip(" —")
                )
            if kind == "message":
                message_parts.append(str(event.get("answer") or ""))
                saw_message = True
            elif kind == "agent_message":
                agent_parts.append(str(event.get("answer") or ""))
                saw_agent = True
            elif kind == "message_replace":
                message_parts = [str(event.get("answer") or "")]
                saw_message = True
            elif kind == "message_end":
                finished = True
                break
            elif kind == "workflow_finished":
                data = event.get("data") or {}
                status = str(data.get("status") or "")
                if status and status not in ("succeeded", "partial-succeeded"):
                    raise ProviderError("Dify workflow: {}".format(status))
        if not finished:
            raise ProviderError("Dify: поток завершился без message_end")
        if saw_agent and saw_message:
            # У Agent-приложений финальный message содержит полный ответ.
            text = "".join(message_parts)
        elif saw_message:
            text = "".join(message_parts)
        else:
            text = "".join(agent_parts)
        if not text.strip():
            raise ProviderError("Dify вернул пустой ответ")
        return text

    # -- интерфейс провайдера -------------------------------------------
    def complete(
        self,
        model: str,
        messages: List[Message],
        temperature: float = 0.3,
        max_tokens: int = 800,
        json_mode: bool = False,
    ) -> Completion:
        api_key = os.environ.get(self.api_key_env, "")
        if not api_key:
            raise ProviderError("не задана переменная окружения {}".format(self.api_key_env))
        started = time.time()
        query = self._build_query(messages, json_mode)
        endpoint = "/chat-messages" if self.app_mode == "chat" else "/completion-messages"
        text = self._request_stream(
            self.base_url + endpoint,
            self._payload(query),
            headers={
                "Authorization": "Bearer " + api_key,
                "Accept": "text/event-stream",
            },
        )
        return Completion(
            text=text,
            provider=self.name,
            model=model or "dify-app",
            latency_ms=int((time.time() - started) * 1000),
            meta={"app_mode": self.app_mode},
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_provider(name: str, config: Dict[str, Any]) -> Provider:
    """Создать провайдер по секции config.providers.<name>."""
    provider_type = str(config.get("type", "")).lower()
    if provider_type == "mock":
        return MockProvider(name)
    if provider_type == "ollama":
        return OllamaProvider(
            name=name,
            base_url=str(config.get("base_url", "http://127.0.0.1:11434")),
            timeout=float(config.get("timeout", 120)),
        )
    if provider_type in ("openai", "openai_compatible", "openai-compatible"):
        return OpenAICompatibleProvider(
            name=name,
            base_url=str(config.get("base_url", "https://api.openai.com/v1")),
            api_key_env=str(config.get("api_key_env", "OPENAI_API_KEY")),
            timeout=float(config.get("timeout", 120)),
            extra_headers=config.get("headers") or {},
        )
    if provider_type == "gemini":
        return GeminiProvider(
            name=name,
            api_key_env=str(config.get("api_key_env", "GEMINI_API_KEY")),
            base_url=str(config.get("base_url", "https://generativelanguage.googleapis.com/v1beta")),
            timeout=float(config.get("timeout", 120)),
        )
    if provider_type == "dify":
        return DifyProvider(
            name=name,
            base_url=str(config.get("base_url", "https://api.dify.ai/v1")),
            api_key_env=str(config.get("api_key_env", "DIFY_API_KEY")),
            app_mode=str(config.get("app_mode", "chat")),
            user=str(config.get("user", "mcp-content-factory")),
            timeout=float(config.get("timeout", 180)),
        )
    if provider_type == "gigachat":
        return GigaChatProvider(
            name=name,
            credentials_env=str(config.get("credentials_env", "GIGACHAT_CREDENTIALS")),
            scope=str(config.get("scope", "GIGACHAT_API_PERS")),
            base_url=str(config.get("base_url", "https://gigachat.devices.sberbank.ru/api/v1")),
            oauth_url=str(config.get("oauth_url", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")),
            timeout=float(config.get("timeout", 120)),
        )
    raise ProviderError("неизвестный тип провайдера: {!r}".format(provider_type))
