"""LLM-провайдеры контент-завода: локальные и российские API.

Все запросы — только ``urllib`` из стандартной библиотеки, без SDK.
Главное правило: сбой LLM никогда не ломает конвейер. При любой сетевой
ошибке, таймауте или неожиданном ответе клиент пишет предупреждение в лог,
помечает себя недоступным и возвращает пустую строку — генератор продолжит
работу на шаблонах и экстрактивной суммаризации.

Поддерживаются провайдеры:
* ``extractive`` — без LLM, шаблоны и TextRank (по умолчанию);
* ``ollama`` — локальная бесплатная модель (qwen3.5:9b и т.п.);
* ``openai_compatible`` — llama.cpp / LM Studio / vLLM с OpenAI-совместимым API;
* ``gigachat`` — GigaChat API (Сбер), OAuth + chat/completions;
* ``yandexgpt`` — YandexGPT API (Yandex Cloud);
* ``dify`` — приложение Dify (cloud.dify.ai или self-hosted) через Service API.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, Optional

from ..utils import DEFAULT_USER_AGENT, env, normalize_space
from .budget import DailyBudget
from .llm_cache import LLMCache, make_key
from .tokens import configure as configure_tokens
from .tokens import get_tracker, record_usage

LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120.0
DEFAULT_MAX_TOKENS = 700
DEFAULT_TEMPERATURE = 0.3
_OAUTH_MIN_TIMEOUT = 30.0
_DEFAULT_PROVIDER = "extractive"


class LLMError(RuntimeError):
    """Внутренняя ошибка провайдера; наружу не выходит (клиент её гасит)."""


def clean_llm_output(text: str) -> str:
    """Чистит ответ LLM: markdown-заборы, служебные префиксы, кавычки, пробелы."""
    if not text:
        return ""
    cleaned = str(text).strip()
    # ```json ... ``` и ``` ... ```
    cleaned = re.sub(r"^```[A-Za-zА-Яа-я0-9_+-]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip().strip('"').strip("«»").strip("'").strip()
    cleaned = re.sub(r"^(?:ответ|резюме|summary|заголовок|headline|conclusion|вывод)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*[-—•*]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = normalize_space(cleaned)
    return cleaned


def clean_llm_output_lines(text: str) -> str:
    """Чистит ответ LLM, сохраняя переводы строк (для списков/резюме+тезисы).

    ``clean_llm_output`` схлопывает всё в один абзац — это ломает форматы
    «РЕЗЮМЕ: … / ТЕЗИСЫ: …» и дайджесты. Здесь чистим построчно, не трогая
    маркеры строк.
    """
    if not text:
        return ""
    cleaned = str(text).strip()
    cleaned = re.sub(r"^```[A-Za-zА-Яа-я0-9_+-]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    lines = [normalize_space(line) for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line)


def _post_json(
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """POST JSON через urllib; сетевые ошибки оборачиваются в LLMError."""
    if not url:
        raise LLMError("пустой URL запроса")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        # Cloudflare-провайдеры (Groq/Cohere/OpenRouter) режут запросы без
        # браузерного User-Agent (Error 1010) — шлём как обычный клиент.
        "User-Agent": DEFAULT_USER_AGENT,
    }
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=max(5.0, float(timeout))) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # pragma: no cover - защита от нечитаемого тела ошибки
            detail = ""
        raise LLMError(f"HTTP {exc.code} от {url}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise LLMError(f"сеть недоступна ({url}): {exc}") from exc
    if not raw:
        raise LLMError(f"пустой ответ от {url}")
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except ValueError as exc:
        raise LLMError(f"не JSON в ответе {url}") from exc
    if isinstance(data, dict) and data.get("error"):
        raise LLMError(f"ошибка провайдера: {data.get('error')}")
    if not isinstance(data, dict):
        raise LLMError(f"неожиданный формат ответа {url}")
    return data


class LLMClient:
    """Базовый клиент LLM.

    Контракт для конвейера: ``name`` (str), ``available`` (bool) и
    ``generate(prompt, system="", max_tokens=None, temperature=None) -> str``.
    Недоступный клиент всегда возвращает пустую строку и не бросает исключений.
    """

    def __init__(
        self,
        name: str = _DEFAULT_PROVIDER,
        available: bool = False,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name = str(name or _DEFAULT_PROVIDER)
        self.available = bool(available)
        self.config: Dict[str, Any] = dict(config or {})
        self.timeout = float(self.config.get("timeout", DEFAULT_TIMEOUT))
        self.max_tokens = int(self.config.get("max_tokens", DEFAULT_MAX_TOKENS))
        self.temperature = float(self.config.get("temperature", DEFAULT_TEMPERATURE))
        # Фактический usage последнего ответа провайдера (если он его отдаёт):
        # {"prompt_tokens": int, "completion_tokens": int, "cached": bool?}
        self.last_usage: Optional[Dict[str, Any]] = None

    # -- публичный интерфейс -------------------------------------------------
    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        keep_lines: bool = False,
    ) -> str:
        if not self.available or not prompt:
            return ""
        self.last_usage = None
        try:
            result = self._generate(
                str(prompt),
                system=str(system or ""),
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:  # любая ошибка провайдера не должна ломать конвейер
            LOGGER.warning("LLM %s недоступна: %s", self.name, exc)
            self.available = False
            return ""
        cleaned = clean_llm_output_lines(result or "") if keep_lines else clean_llm_output(result or "")
        if not cleaned:
            LOGGER.warning("LLM %s вернула пустой ответ", self.name)
            self.available = False
            return ""
        record_usage(
            self.name,
            usage=self.last_usage,
            prompt=str(prompt or ""),
            completion=cleaned,
        )
        return cleaned

    def _generate(
        self,
        prompt: str,
        system: str,
        max_tokens: Optional[int],
        temperature: Optional[float],
    ) -> str:
        return ""

    def __repr__(self) -> str:  # pragma: no cover - отладочное представление
        return f"LLMClient(name={self.name!r}, available={self.available!r})"


class ExtractiveLLM(LLMClient):
    """Режим без LLM: клиент намеренно недоступен, работают TextRank и шаблоны."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(name="extractive", available=False, config=config)


class OllamaLLM(LLMClient):
    """Локальная Ollama через ``/api/generate`` (бесплатно, офлайн)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(name="ollama", available=True, config=config)
        self.base_url = str(config.get("base_url") if config else "") or "http://127.0.0.1:11434"
        # OLLAMA_HOST из .env имеет приоритет над yaml.
        env_host = env("OLLAMA_HOST", "") or ""
        if env_host:
            self.base_url = env_host
        self.base_url = self.base_url.rstrip("/")
        self.model = str((config or {}).get("model") or "qwen3.5:9b")
        # Размер контекста: Ollama по умолчанию может взять 4K, а статьи в конвейере
        # бывают до 15k символов — задаём явно, если настроено (0 = не передавать).
        try:
            self.num_ctx = int((config or {}).get("num_ctx") or 0)
        except (TypeError, ValueError):
            self.num_ctx = 0
        # «Размышления» reasoning-моделей: для постов они не нужны и лишь
        # растягивают генерацию (qwen3.5 по умолчанию «думает»). False = выключить.
        think = (config or {}).get("think")
        self.think = think if isinstance(think, bool) else None
        # Держим модель в памяти между прогонами (демон ходит раз в 10 минут):
        # без keep_alive Ollama выгружает её через 5 минут и тратит время на загрузку.
        self.keep_alive = str((config or {}).get("keep_alive") or "").strip()

    def _generate(
        self,
        prompt: str,
        system: str,
        max_tokens: Optional[int],
        temperature: Optional[float],
    ) -> str:
        payload: Dict[str, Any] = {"model": self.model, "prompt": prompt, "stream": False}
        if self.think is not None:
            payload["think"] = self.think
        if self.keep_alive:
            payload["keep_alive"] = self.keep_alive
        if system:
            payload["system"] = system
        options: Dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = float(temperature)
        if max_tokens:
            options["num_predict"] = int(max_tokens)
        if self.num_ctx > 0:
            options["num_ctx"] = self.num_ctx
        if options:
            payload["options"] = options
        data = _post_json(self.base_url + "/api/generate", payload, timeout=self.timeout)
        text = data.get("response", "")
        self.last_usage = {
            "prompt_tokens": int(data.get("prompt_eval_count") or 0),
            "completion_tokens": int(data.get("eval_count") or 0),
        }
        if not text:
            raise LLMError("Ollama не вернула поле response")
        return str(text)


class OpenAICompatibleLLM(LLMClient):
    """OpenAI-совместимый сервер (llama.cpp, LM Studio, vLLM, Ollama /v1)."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        # Ключ не обязателен для локальных серверов, поэтому клиент доступен сразу.
        super().__init__(name="openai_compatible", available=True, config=config)
        self.base_url = str((config or {}).get("base_url") or "http://127.0.0.1:11434/v1").rstrip("/")
        self.model = str((config or {}).get("model") or "qwen3.5:9b")
        self.api_key_env = str((config or {}).get("api_key_env") or "OPENAI_COMPAT_API_KEY")
        self.api_key = env(self.api_key_env, "") or ""
        # Доп. поля тела запроса (reasoning_effort, thinking budget и т.п.).
        self.extra_body = dict((config or {}).get("extra_body") or {})

    def _generate(
        self,
        prompt: str,
        system: str,
        max_tokens: Optional[int],
        temperature: Optional[float],
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": float(temperature if temperature is not None else self.temperature),
            # max_tokens иногда не поддерживается старыми серверами — отправляем только если задан.
        }
        if max_tokens:
            payload["max_tokens"] = int(max_tokens)
        if self.extra_body:
            payload.update(self.extra_body)
        headers = dict((self.config.get("headers") or {}))
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = _post_json(
            self.base_url + "/chat/completions", payload, headers=headers, timeout=self.timeout
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("неожиданный формат ответа chat/completions") from exc
        usage = data.get("usage") if isinstance(data, dict) else None
        if isinstance(usage, dict):
            self.last_usage = {
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
            }
        return str(text or "")


class GigaChatLLM(LLMClient):
    """GigaChat API: OAuth-токен с кешем в памяти + chat/completions."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        credentials = env(str(cfg.get("credentials_env") or "GIGACHAT_CREDENTIALS"), "") or ""
        super().__init__(name="gigachat", available=bool(credentials), config=config)
        self.base_url = str(cfg.get("base_url") or "https://gigachat.devices.sberbank.ru/api/v1").rstrip("/")
        self.oauth_url = str(cfg.get("oauth_url") or "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
        self.model = str(cfg.get("model") or "GigaChat")
        self.scope = str(cfg.get("scope") or "GIGACHAT_API_PERS")
        self._credentials = credentials
        self._token = ""
        self._token_expires_at = 0.0

    def _fetch_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        if not self._credentials:
            raise LLMError("не задан GIGACHAT_CREDENTIALS")
        body = urllib.parse.urlencode({"scope": self.scope}).encode("utf-8")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Authorization": "Basic " + self._credentials,
            "RqUID": str(uuid.uuid4()),
        }
        request = urllib.request.Request(self.oauth_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(
                request, timeout=max(_OAUTH_MIN_TIMEOUT, min(self.timeout, 60.0))
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise LLMError(f"OAuth GigaChat: HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise LLMError(f"OAuth GigaChat: сеть недоступна ({exc})") from exc
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise LLMError("OAuth GigaChat: не JSON") from exc
        token = str(data.get("access_token") or "")
        if not token:
            raise LLMError("OAuth GigaChat: нет access_token")
        expires_at = data.get("expires_at")
        try:
            expires = float(expires_at) / 1000.0 if expires_at else time.time() + 1500
        except (TypeError, ValueError):
            expires = time.time() + 1500
        self._token = token
        self._token_expires_at = expires
        return token

    def _generate(
        self,
        prompt: str,
        system: str,
        max_tokens: Optional[int],
        temperature: Optional[float],
    ) -> str:
        token = self._fetch_token()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": float(temperature if temperature is not None else self.temperature),
            "max_tokens": int(max_tokens or self.max_tokens),
        }
        data = _post_json(
            self.base_url + "/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
        )
        try:
            return str(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("неожиданный формат ответа GigaChat") from exc


class YandexGPTLLM(LLMClient):
    """YandexGPT: Api-Key + folderId, эндпоинт ``/completion``."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = config or {}
        self.api_key = env(str(cfg.get("api_key_env") or "YANDEXGPT_API_KEY"), "") or ""
        self.folder_id = env(str(cfg.get("folder_id_env") or "YANDEX_FOLDER_ID"), "") or ""
        super().__init__(
            name="yandexgpt", available=bool(self.api_key and self.folder_id), config=config
        )
        self.base_url = str(
            cfg.get("base_url") or "https://llm.api.cloud.yandex.net/foundationModels/v1"
        ).rstrip("/")
        self.model = str(cfg.get("model") or "yandexgpt-lite/latest")

    def _generate(
        self,
        prompt: str,
        system: str,
        max_tokens: Optional[int],
        temperature: Optional[float],
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "text": system})
        messages.append({"role": "user", "text": prompt})
        model_uri = self.model if self.model.startswith("gpt://") else f"gpt://{self.folder_id}/{self.model}"
        payload: Dict[str, Any] = {
            "modelUri": model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": float(temperature if temperature is not None else self.temperature),
                "maxTokens": str(int(max_tokens or self.max_tokens)),
            },
            "messages": messages,
        }
        data = _post_json(
            self.base_url + "/completion",
            payload,
            headers={"Authorization": f"Api-Key {self.api_key}", "x-folder-id": self.folder_id},
            timeout=self.timeout,
        )
        try:
            return str(data["result"]["alternatives"][0]["message"]["text"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("неожиданный формат ответа YandexGPT") from exc


_DIFY_APP_MODES = ("chat", "completion")


def _dify_error_detail(exc: urllib.error.HTTPError) -> str:
    """Достаёт ``code``/``message`` из JSON-ошибки Dify — иначе код ошибки бесполезен."""
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - тело ошибки может быть недоступно
        return ""
    detail = raw[:500].strip()
    try:
        data = json.loads(raw)
    except ValueError:
        return detail
    if not isinstance(data, dict):
        return detail
    code = str(data.get("code") or "").strip()
    message = str(data.get("message") or "").strip()
    text = " — ".join(part for part in (code, message) if part) or detail
    if code == "not_chat_app":
        text += (
            " (проверьте llm.dify.app_mode: chat — для Chatbot/Agent/Chatflow, "
            "completion — для Text Generator; приложение типа Workflow "
            "использует /workflows/run и для фабрики не подходит)"
        )
    return text


class DifyLLM(LLMClient):
    """Приложение Dify как LLM: Service API ``/chat-messages`` или ``/completion-messages``.

    Работает и с Dify Cloud (``https://api.dify.ai/v1``), и с self-hosted
    инстансом: адрес задаётся в ``llm.dify.base_url``. Ответ всегда
    запрашивается в streaming-режиме — Dify Cloud не любит долгие
    blocking-запросы (edge-прокси может оборвать соединение), а Agent-приложения
    вообще поддерживают только streaming. Поток SSE разбирается вручную,
    поэтому SDK не нужен.

    Важно: ``temperature``/``max_tokens`` применяются к модели в самом
    приложении Dify, а аргументы ``generate()`` здесь игнорируются. Промпты
    фабрики всё равно передаются: ``system`` склеивается с ``prompt`` в текст
    запроса (``include_system: false`` отключает это, если инструкции уже
    зашиты в приложении).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = dict(config or {})
        self._api_key = env(str(cfg.get("api_key_env") or "DIFY_API_KEY"), "") or ""
        super().__init__(name="dify", available=bool(self._api_key), config=cfg)
        self.base_url = str(
            env("DIFY_BASE_URL", "") or cfg.get("base_url") or "https://api.dify.ai/v1"
        ).rstrip("/")
        app_mode = str(cfg.get("app_mode") or "chat").strip().lower()
        if app_mode not in _DIFY_APP_MODES:
            LOGGER.warning("Dify: неизвестный app_mode=%r, используем chat", app_mode)
            app_mode = "chat"
        self.app_mode = app_mode
        self.user = str(cfg.get("user") or "content-factory")
        query_input = cfg.get("query_input", "query")
        # Пустая строка = отправить текст в устаревшее поле query (старые Completion-приложения).
        self.query_input = "" if query_input is None else str(query_input)
        self.inputs = dict(cfg.get("inputs") or {})
        self.include_system = bool(cfg.get("include_system", True))

    def describe(self) -> str:
        """Короткое описание для ``llm-test`` и логов."""
        return f"{self.base_url} | app_mode={self.app_mode}"

    def _query(self, prompt: str, system: str) -> str:
        if system and self.include_system:
            return system + "\n\n" + prompt
        return prompt

    def _payload(self, query: str) -> Dict[str, Any]:
        if self.app_mode == "completion":
            inputs = dict(self.inputs)
            payload: Dict[str, Any] = {
                "inputs": inputs,
                "response_mode": "streaming",
                "user": self.user,
            }
            if self.query_input:
                inputs[self.query_input] = query
            else:
                payload["query"] = query
            return payload
        return {
            "inputs": dict(self.inputs),
            "query": query,
            "response_mode": "streaming",
            "user": self.user,
        }

    def _generate(
        self,
        prompt: str,
        system: str,
        max_tokens: Optional[int],
        temperature: Optional[float],
    ) -> str:
        endpoint = "/chat-messages" if self.app_mode == "chat" else "/completion-messages"
        url = self.base_url + endpoint
        payload = self._payload(self._query(prompt, system))
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "text/event-stream",
        }
        return self._request_stream(url, payload, headers)

    def _request_stream(
        self, url: str, payload: Dict[str, Any], headers: Dict[str, str]
    ) -> str:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers)
        request = urllib.request.Request(
            url, data=body, headers=request_headers, method="POST"
        )
        try:
            response = urllib.request.urlopen(request, timeout=max(5.0, float(self.timeout)))
        except urllib.error.HTTPError as exc:
            raise LLMError(
                f"HTTP {exc.code} от Dify ({url}): {_dify_error_detail(exc)}"
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise LLMError(f"сеть недоступна ({url}): {exc}") from exc
        try:
            return self._read_stream(response)
        finally:
            try:  # pragma: no cover - закрытие в тестах не критично
                response.close()
            except Exception:  # pragma: no cover
                pass

    def _read_stream(self, response: Any) -> str:
        """Разбирает SSE-поток Dify и возвращает итоговый текст ответа."""
        content_type = ""
        try:
            content_type = str(response.headers.get("Content-Type") or "")
        except AttributeError:  # pragma: no cover - защита от нестандартного ответа
            content_type = ""
        if "application/json" in content_type:
            # Защита от сервера/прокси, который проигнорировал streaming и ответил JSON.
            raw = response.read()
            try:
                data = json.loads(raw.decode("utf-8", errors="replace"))
            except ValueError as exc:
                raise LLMError("Dify: ответ не JSON и не SSE") from exc
            answer = str((data or {}).get("answer") or "")
            if not answer:
                raise LLMError("Dify: пустой answer в JSON-ответе")
            return answer

        message_parts: list = []
        agent_parts: list = []
        saw_message = False
        saw_agent = False
        finished = False
        for raw_line in response:
            try:
                line = raw_line.decode("utf-8", errors="replace").strip()
            except AttributeError:  # pragma: no cover - если строки уже str
                line = str(raw_line).strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                event = json.loads(payload)
            except ValueError as exc:
                raise LLMError("Dify: некорректный JSON в SSE-потоке") from exc
            if not isinstance(event, dict):
                continue
            kind = str(event.get("event") or "")
            if kind == "error":
                code = str(event.get("code") or "error")
                message = str(event.get("message") or "").strip()
                raise LLMError(f"Dify: {code} — {message}".rstrip(" —"))
            if kind == "message":
                message_parts.append(str(event.get("answer") or ""))
                saw_message = True
            elif kind == "agent_message":
                agent_parts.append(str(event.get("answer") or ""))
                saw_agent = True
            elif kind == "message_replace":
                # Модерация заменила уже отданный ответ.
                message_parts = [str(event.get("answer") or "")]
                saw_message = True
            elif kind == "message_end":
                finished = True
                break
            elif kind == "workflow_finished":
                data = event.get("data") or {}
                status = str(data.get("status") or "")
                if status and status not in ("succeeded", "partial-succeeded"):
                    error = str(data.get("error") or "").strip()
                    raise LLMError(f"Dify workflow: {status}" + (f" — {error}" if error else ""))
            # ping, workflow_started, node_* и прочие события для нас информативны.
        if not finished:
            raise LLMError("Dify: поток завершился без message_end (ответ мог обрезаться)")
        if saw_agent and saw_message:
            # Agent-приложения шлют чанки agent_message, а в конце — полный ответ
            # обычным message: берём финальный message, чтобы не дублировать текст.
            text = "".join(message_parts)
        elif saw_message:
            text = "".join(message_parts)
        else:
            text = "".join(agent_parts)
        if not text.strip():
            raise LLMError("Dify вернул пустой ответ")
        return text


class LimitedLLMClient(LLMClient):
    """Обёртка над LLM-клиентом: не больше N запросов в сутки (UTC).

    После исчерпания бюджета ``generate`` возвращает пустую строку, и конвейер
    автоматически переходит на бесплатный extractive-режим. Так бесплатные
    лимиты Dify Cloud / GigaChat / YandexGPT не выжигаются за пару дней.
    """

    def __init__(self, inner: LLMClient, budget: DailyBudget, token_limit: int = 0) -> None:
        self._inner = inner
        self.budget = budget
        self.token_limit = max(0, int(token_limit or 0))
        super().__init__(name=inner.name, available=inner.available, config={})

    @property
    def available(self) -> bool:  # type: ignore[override]
        return bool(self._inner.available) and self.budget.remaining() > 0

    @available.setter
    def available(self, value: bool) -> None:
        self._inner.available = bool(value)

    def _tokens_exhausted(self) -> bool:
        """Дневной лимит токенов (для платных/лимитированных API; 0 = выключен)."""
        if self.token_limit <= 0:
            return False
        tracker = get_tracker()
        if tracker is None:
            return False
        used = int(tracker.today().get("total_tokens") or 0)
        if used < self.token_limit:
            return False
        LOGGER.warning(
            "LLM %s: дневной лимит токенов исчерпан (%d/%d) — переключаюсь на extractive",
            self.name,
            used,
            self.token_limit,
        )
        return True

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        keep_lines: bool = False,
    ) -> str:
        if not prompt or not self._inner.available:
            return ""
        if self.budget.remaining() <= 0:
            LOGGER.warning(
                "LLM %s: %s — переключаюсь на extractive", self.name, self.budget.describe()
            )
            return ""
        if self._tokens_exhausted():
            return ""
        if not self.budget.try_consume(1):
            return ""
        text = self._inner.generate(
            prompt,
            system=str(system or ""),
            max_tokens=max_tokens,
            temperature=temperature,
            keep_lines=keep_lines,
        )
        self.name = self._inner.name  # после fallback имя — фактический провайдер
        self.last_usage = self._inner.last_usage
        return text

    def describe(self) -> str:
        base = self._inner.describe() if hasattr(self._inner, "describe") else ""
        parts = [part for part in (base, self.budget.describe()) if part]
        if self.token_limit > 0:
            tracker = get_tracker()
            used = int(tracker.today().get("total_tokens") or 0) if tracker else 0
            parts.append("токены: {}/{} сегодня".format(used, self.token_limit))
        return " | ".join(parts)


class FallbackLLMClient(LLMClient):
    """Пробует LLM-провайдеров по очереди: Groq → OpenRouter → … → extractive.

    Нужен, чтобы бесплатные лимиты одного провайдера не останавливали постинг:
    если очередной клиент недоступен или вернул пустой ответ, берём следующего.
    """

    def __init__(self, clients: List[LLMClient]) -> None:
        self.clients = [client for client in clients if client is not None]
        first = next((client for client in self.clients if client.available), None)
        super().__init__(
            name=first.name if first else _DEFAULT_PROVIDER,
            available=bool(first),
            config={},
        )

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        keep_lines: bool = False,
    ) -> str:
        if not prompt:
            return ""
        for client in self.clients:
            if not client.available:
                continue
            text = client.generate(
                prompt,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                keep_lines=keep_lines,
            )
            if text:
                self.name = client.name
                self.last_usage = client.last_usage
                return text
        self.available = False
        return ""

    def describe(self) -> str:
        parts = []
        for client in self.clients:
            describe = getattr(client, "describe", None)
            detail = describe() if callable(describe) else ""
            parts.append(
                "{}:{}".format(client.name, "ok" if client.available else "off")
                + (" (" + detail + ")" if detail else "")
            )
        return "цепочка " + " → ".join(parts)


class CachedLLMClient(LLMClient):
    """Кэш ответов LLM: тот же промпт → готовый ответ без обращения к модели.

    Экономия без потери качества: ключ включает провайдера, системный промпт,
    текст запроса, лимит токенов и температуру — при точном совпадении ответ
    модели был бы тем же, поэтому берём сохранённый. Полезно при перезапусках
    демона/cron и повторном анализе тех же новостей.
    """

    def __init__(self, inner: LLMClient, cache: LLMCache) -> None:
        self._inner = inner
        self.cache = cache
        super().__init__(name=inner.name, available=inner.available, config={})

    @property
    def available(self) -> bool:  # type: ignore[override]
        return bool(self._inner.available)

    @available.setter
    def available(self, value: bool) -> None:
        self._inner.available = bool(value)

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        keep_lines: bool = False,
    ) -> str:
        if not prompt or not self._inner.available:
            return ""
        if not self.cache.enabled:
            return self._inner.generate(
                prompt,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                keep_lines=keep_lines,
            )
        key = make_key(
            self._inner.name + ("|lines" if keep_lines else ""),
            system,
            prompt,
            max_tokens or self._inner.max_tokens,
            temperature if temperature is not None else self._inner.temperature,
        )
        hit = self.cache.get(key)
        if hit is not None and hit.get("response"):
            self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0, "cached": True}
            tracker = get_tracker()
            saved = int(hit.get("prompt_tokens") or 0) + int(hit.get("completion_tokens") or 0)
            if tracker is not None:
                tracker.record_cache_hit(self._inner.name, saved)
            LOGGER.debug(
                "LLM %s: ответ из кэша (сэкономлено ~%d токенов)", self._inner.name, saved
            )
            return str(hit.get("response") or "")
        text = self._inner.generate(
            prompt,
            system=system,
            max_tokens=max_tokens,
            temperature=temperature,
            keep_lines=keep_lines,
        )
        self.name = self._inner.name  # фактический провайдер после fallback
        self.last_usage = self._inner.last_usage
        if text:
            usage = self._inner.last_usage or {}
            self.cache.put(
                key,
                self._inner.name,
                text,
                int(usage.get("prompt_tokens") or 0),
                int(usage.get("completion_tokens") or 0),
            )
        return text

    def describe(self) -> str:
        base = self._inner.describe() if hasattr(self._inner, "describe") else ""
        return " | ".join(part for part in (base, self.cache.describe()) if part)


def _provider_config(settings: Any, provider: str) -> Dict[str, Any]:
    """Собирает конфиг провайдера: секция yaml + общие таймауты/лимиты."""
    llm_section: Dict[str, Any] = {}
    try:
        if settings is not None:
            llm_section = dict(settings.llm or {})
    except Exception:  # pragma: no cover - защита от нестандартного Settings
        llm_section = {}
    config: Dict[str, Any] = dict(llm_section.get(provider) or {})
    for key in ("timeout", "max_tokens", "temperature"):
        if key in llm_section and key not in config:
            config[key] = llm_section[key]
    config.setdefault("timeout", DEFAULT_TIMEOUT)
    config.setdefault("max_tokens", DEFAULT_MAX_TOKENS)
    config.setdefault("temperature", DEFAULT_TEMPERATURE)
    return config


_NAMED_PROVIDERS: Dict[str, Dict[str, str]] = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "model": "llama-3.3-70b-versatile",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
    },
    "sambanova": {
        "base_url": "https://api.sambanova.ai/v1",
        "api_key_env": "SAMBANOVA_API_KEY",
        "model": "Meta-Llama-3.3-70B-Instruct",
    },
    "huggingface": {
        "base_url": "https://router.huggingface.co/v1",
        "api_key_env": "HUGGINGFACE_API_KEY",
        "model": "meta-llama/Llama-3.3-70B-Instruct",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-flash",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "model": "gpt-4o-mini",
    },
    "gemini": {
        # Google Gemini через OpenAI-совместимый endpoint (AI Studio key).
        # Из РФ недоступен (400 location not supported) — работает в Actions/VPN.
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-3.6-flash",
    },    "pollinations": {
        # Pollinations: бесплатный OpenAI-совместимый шлюз, ключ не нужен.
        # Анонимный лимит ~1 запрос в 3 секунды; для постов этого хватает.
        "base_url": "https://text.pollinations.ai/openai",
        "api_key_env": "",
        "model": "openai",
    },
}


def _named_provider_config(settings: Any, name: str) -> Dict[str, Any]:
    """Конфиг провайдера из ``llm.providers.<name>`` + дефолты по имени."""
    llm_section: Dict[str, Any] = {}
    try:
        if settings is not None:
            llm_section = dict(settings.llm or {})
    except Exception:  # pragma: no cover - нестандартные Settings
        llm_section = {}
    providers = dict(llm_section.get("providers") or {})
    config: Dict[str, Any] = dict(_NAMED_PROVIDERS.get(name) or {})
    config.update(dict(providers.get(name) or {}))
    for key in ("timeout", "max_tokens", "temperature"):
        if key in llm_section and key not in config:
            config[key] = llm_section[key]
    config.setdefault("timeout", DEFAULT_TIMEOUT)
    config.setdefault("max_tokens", DEFAULT_MAX_TOKENS)
    config.setdefault("temperature", DEFAULT_TEMPERATURE)
    return config


def _has_key(settings: Any, provider: str) -> bool:
    """Есть ли API-ключ у именованного облачного провайдера."""
    config = _named_provider_config(settings, provider)
    api_key_env = str(config.get("api_key_env") or "")
    if not api_key_env:
        return True
    return bool(env(api_key_env, ""))


def _build_llm(provider: str, settings: Any) -> LLMClient:
    """Создаёт клиент по имени провайдера (без бюджета)."""
    providers = {}
    try:
        providers = dict((settings.llm or {}).get("providers") or {}) if settings is not None else {}
    except Exception:  # pragma: no cover
        providers = {}
    if provider in _NAMED_PROVIDERS or provider in providers:
        config = _named_provider_config(settings, provider)
        client = OpenAICompatibleLLM(config)
        client.name = provider
        if not _has_key(settings, provider):
            client.available = False
            LOGGER.info("LLM %s: ключ %s не задан — провайдер пропущен", provider, config.get("api_key_env"))
        return client
    if provider in ("extractive", "", "none", "off"):
        return ExtractiveLLM(_provider_config(settings, "extractive"))
    if provider == "ollama":
        return OllamaLLM(_provider_config(settings, "ollama"))
    if provider in ("openai_compatible", "openai-compatible"):
        return OpenAICompatibleLLM(_provider_config(settings, "openai_compatible"))
    if provider == "gigachat":
        return GigaChatLLM(_provider_config(settings, "gigachat"))
    if provider == "yandexgpt":
        return YandexGPTLLM(_provider_config(settings, "yandexgpt"))
    if provider == "dify":
        return DifyLLM(_provider_config(settings, "dify"))
    LOGGER.warning("Неизвестный LLM-провайдер %r, используем extractive", provider)
    return ExtractiveLLM({"provider": "extractive"})


def _stage_route(settings: Any, stage: Optional[str]) -> Optional[tuple]:
    """Маршрут этапа из ``llm.stage_routes``: (provider, fallback) или None.

    Этапы: ``analysis`` (резюме/тезисы) и ``generation`` (заголовок/пост).
    Позволяет держать анализ на бесплатных моделях, а генерацию — на качественной
    платной: при исчерпании лимита анализ сам уходит на следующего провайдера.
    """
    if settings is None or not stage:
        return None
    try:
        llm_section = dict(settings.llm or {})
    except Exception:  # pragma: no cover - нестандартные Settings
        return None
    routes = llm_section.get("stage_routes") or {}
    route = routes.get(str(stage)) if isinstance(routes, dict) else None
    if not isinstance(route, dict):
        return None
    provider = str(route.get("provider") or "").strip().lower()
    fallback = [
        str(name).strip().lower()
        for name in (route.get("fallback") or [])
        if str(name).strip()
    ]
    if not provider and not fallback:
        return None
    return provider, fallback


def _provider_request_limit(settings: Any, provider: str) -> int:
    """Суточный лимит запросов провайдера (0 = без лимита).

    Читается из ``llm.provider_limits.<name>`` (число или
    ``{daily_request_limit: N}``), затем из конфига провайдера
    (``llm.providers.<name>`` / ``llm.<name>``).
    """
    try:
        llm_section = dict(settings.llm or {}) if settings is not None else {}
    except Exception:  # pragma: no cover - нестандартные Settings
        llm_section = {}
    limits = llm_section.get("provider_limits") or {}
    value: Any = limits.get(provider) if isinstance(limits, dict) else None
    if isinstance(value, dict):
        value = value.get("daily_request_limit")
    if value is None:
        providers = llm_section.get("providers") or {}
        config = providers.get(provider) if isinstance(providers, dict) else None
        if not isinstance(config, dict):
            config = llm_section.get(provider)
        if isinstance(config, dict):
            value = config.get("daily_request_limit")
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _with_provider_limit(client: LLMClient, settings: Any) -> LLMClient:
    """Обернуть провайдера его суточным лимитом.

    Когда лимит исчерпан, ``available`` становится False, и ``FallbackLLMClient``
    автоматически берёт следующего провайдера — вплоть до платного DeepSeek.
    """
    limit = _provider_request_limit(settings, client.name)
    if limit <= 0 or not client.available or client.name == "extractive":
        return client
    try:
        budget = DailyBudget(
            settings.data_dir / "llm_usage_{}.json".format(client.name), limit
        )
        wrapped = LimitedLLMClient(client, budget)
        LOGGER.info("LLM %s: суточный лимит %s запросов (UTC)", client.name, limit)
        return wrapped
    except Exception as exc:  # pragma: no cover - лимит не должен ломать LLM
        LOGGER.warning("LLM %s: не удалось включить суточный лимит: %s", client.name, exc)
        return client


def get_llm(settings: Any = None, stage: Optional[str] = None) -> LLMClient:
    """Фабрика LLM-клиента по ``settings.llm.provider`` + цепочка fallback.

    ``stage`` (``analysis``/``generation``) выбирает маршрут из
    ``llm.stage_routes``: у анализа и генерации могут быть разные провайдеры и
    fallback-цепочки. Никогда не бросает исключений.

    Суточные лимиты ``llm.provider_limits`` применяются к каждому провайдеру
    отдельно: исчерпали free-лимит → автоматически пошли к следующему, вплоть
    до платного. ``llm.daily_request_limit`` (общий потолок на весь запуск,
    0 = выключен) сохраняется как жёсткий стоп, если задан.
    """
    provider = _DEFAULT_PROVIDER
    fallback_names: List[str] = []
    try:
        if settings is not None:
            provider = str(settings.llm.get("provider") or _DEFAULT_PROVIDER).strip().lower()
            fallback_names = [
                str(name).strip().lower()
                for name in (settings.llm.get("fallback") or [])
                if str(name).strip()
            ]
    except Exception:
        provider = _DEFAULT_PROVIDER

    route = _stage_route(settings, stage)
    if route:
        route_provider, route_fallback = route
        provider = route_provider or provider
        # Маршрут этапа задаёт и fallback-цепочку (пустой список = без fallback).
        fallback_names = route_fallback
        LOGGER.info(
            "LLM этап %r: %s (fallback: %s)",
            stage,
            provider,
            ", ".join(fallback_names) or "—",
        )

    clients: List[LLMClient] = []
    try:
        primary = _build_llm(provider, settings)
    except Exception as exc:  # конфигурация не должна ронять конвейер
        LOGGER.warning("Не удалось создать LLM-клиент %r: %s", provider, exc)
        primary = ExtractiveLLM({"provider": "extractive"})
    clients.append(_with_provider_limit(primary, settings))

    for name in fallback_names:
        if name == provider:
            continue
        try:
            client = _build_llm(name, settings)
        except Exception as exc:  # pragma: no cover - защита от плохого конфига
            LOGGER.warning("LLM fallback %r: не удалось создать клиент: %s", name, exc)
            continue
        clients.append(_with_provider_limit(client, settings))

    available = [client for client in clients if client.available]
    if not available:
        # Все провайдеры недоступны: возвращаем основной как есть — конвейер
        # увидит available=False и уйдёт в extractive, зато в логах будет причина.
        client: LLMClient = primary
    elif len(available) == 1:
        client = available[0]
    else:
        client = FallbackLLMClient(available)
        LOGGER.info(
            "LLM: цепочка провайдеров %s",
            ", ".join(item.name for item in available),
        )

    # Учёт токенов: файл рядом с llm_usage.json, обнуляется по UTC.
    if settings is not None:
        try:
            configure_tokens(settings.data_dir / "llm_tokens.json")
        except Exception as exc:  # pragma: no cover - нестандартные Settings
            LOGGER.warning("Не удалось включить учёт токенов: %s", exc)

    try:
        limit = int(settings.llm.get("daily_request_limit") or 0) if settings is not None else 0
    except (TypeError, ValueError, AttributeError):
        limit = 0
    try:
        token_limit = int(settings.llm.get("daily_token_limit") or 0) if settings is not None else 0
    except (TypeError, ValueError, AttributeError):
        token_limit = 0
    if (limit > 0 or token_limit > 0) and client.available and client.name != "extractive":
        try:
            budget = DailyBudget(settings.data_dir / "llm_usage.json", limit)
            client = LimitedLLMClient(client, budget, token_limit=token_limit)
            if limit > 0:
                LOGGER.info("LLM %s: включён суточный бюджет %s запросов (UTC)", client.name, limit)
            if token_limit > 0:
                LOGGER.info("LLM %s: включён суточный лимит %s токенов (UTC)", client.name, token_limit)
        except Exception as exc:  # pragma: no cover - нестандартные Settings
            LOGGER.warning("Не удалось включить бюджет LLM: %s", exc)

    # Кэш ответов: точное совпадение промпта → ответ без запроса к модели.
    try:
        cache_enabled = bool((settings.llm or {}).get("cache", False)) if settings is not None else False
        ttl = int((settings.llm or {}).get("cache_ttl_hours", 168) or 0) if settings is not None else 0
        if cache_enabled and ttl > 0 and settings is not None:
            cache = LLMCache(settings.data_dir / "llm_cache.sqlite3", ttl_hours=ttl)
            if cache.enabled:
                client = CachedLLMClient(client, cache)
                LOGGER.info("LLM: кэш ответов включён (TTL %d ч)", ttl)
    except Exception as exc:  # pragma: no cover - кэш не должен ронять завод
        LOGGER.warning("Не удалось включить кэш LLM: %s", exc)
    return client
