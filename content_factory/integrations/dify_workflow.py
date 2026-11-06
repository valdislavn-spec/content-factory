"""Клиент Dify Workflow API: проверка приложения и запуск сценария.

Service API workflow-приложений: ``GET /info``, ``GET /parameters``,
``POST /workflows/run``. Используется для интеграций «новости / тренды / SEO»:
сначала проверяем, какие входы объявлены у приложения, затем запускаем и
читаем ``data.outputs``.

Частая ошибка в Dify — Workflow без End-узла: запуск проходит (status
``succeeded``), но ``outputs`` пустой. Клиент явно сообщает об этом.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from ..utils import env

DEFAULT_BASE_URL = "https://api.dify.ai/v1"
DEFAULT_TIMEOUT = 120.0


class DifyWorkflowError(RuntimeError):
    """Приложение недоступно, вернуло ошибку или пустые outputs."""


class DifyWorkflowClient:
    """Минимальный клиент Dify Workflow API (только stdlib)."""

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = str(api_key or "").strip()
        self.base_url = str(
            base_url or env("DIFY_BASE_URL", "") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = float(timeout)

    # -- HTTP ------------------------------------------------------------
    def _request(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        headers = {
            "Authorization": "Bearer " + self.api_key,
            "Accept": "application/json",
        }
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=max(5.0, self.timeout)) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:500]
            except Exception:  # pragma: no cover - тело ошибки может быть недоступно
                detail = ""
            raise DifyWorkflowError(
                "Dify HTTP {} ({}): {}".format(exc.code, path, detail)
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise DifyWorkflowError("Dify: сеть недоступна ({}): {}".format(path, exc)) from exc
        try:
            parsed = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise DifyWorkflowError("Dify: ответ не JSON ({})".format(path)) from exc
        if not isinstance(parsed, dict):
            raise DifyWorkflowError("Dify: неожиданный формат ответа ({})".format(path))
        return parsed

    # -- API -------------------------------------------------------------
    def info(self) -> Dict[str, Any]:
        """Имя приложения и тип (``mode``)."""
        return self._request("GET", "/info")

    def parameters(self) -> Dict[str, Any]:
        """Параметры приложения: ``user_input_form`` — объявленные входы."""
        return self._request("GET", "/parameters")

    def run(
        self,
        inputs: Optional[Dict[str, Any]] = None,
        user: str = "content-factory",
    ) -> Dict[str, Any]:
        """Запускает workflow в blocking-режиме и возвращает полный ответ."""
        payload = {
            "inputs": dict(inputs or {}),
            "response_mode": "blocking",
            "user": str(user or "content-factory"),
        }
        data = self._request("POST", "/workflows/run", payload)
        run_data = data.get("data") or {}
        status = str(run_data.get("status") or "")
        if status and status not in ("succeeded", "partial-succeeded"):
            error = str(run_data.get("error") or "").strip()
            raise DifyWorkflowError(
                "Dify workflow status={}".format(status) + (": " + error if error else "")
            )
        return data

    @staticmethod
    def outputs(data: Dict[str, Any]) -> Dict[str, Any]:
        """Возвращает ``data.outputs`` (может быть пустым при отсутствии End-узла)."""
        return (data.get("data") or {}).get("outputs") or {}

    def run_text(
        self,
        inputs: Optional[Dict[str, Any]] = None,
        output_key: Optional[str] = None,
        user: str = "content-factory",
    ) -> str:
        """Запускает workflow и возвращает текстовый результат.

        ``output_key`` — имя выходной переменной из End-узла. Если не задан,
        берётся первое непустое строковое значение, иначе — первый output.
        """
        data = self.run(inputs, user=user)
        outputs = self.outputs(data)
        if not outputs:
            raise DifyWorkflowError(
                "Dify вернул пустые outputs: в Workflow нет End-узла с выходной "
                "переменной. Добавьте End node и опубликуйте приложение."
            )
        value: Any = None
        if output_key:
            if output_key not in outputs:
                raise DifyWorkflowError(
                    "В outputs нет переменной {!r}; доступны: {}".format(
                        output_key, ", ".join(sorted(outputs))
                    )
                )
            value = outputs.get(output_key)
        else:
            for candidate in outputs.values():
                if isinstance(candidate, str) and candidate.strip():
                    value = candidate
                    break
            if value is None:
                value = next(iter(outputs.values()))
        if isinstance(value, str):
            text = value
        else:
            text = json.dumps(value, ensure_ascii=False)
        if not text.strip():
            raise DifyWorkflowError("Dify вернул пустой текстовый output")
        return text

    def input_variables(self) -> list:
        """Имена входных переменных приложения из ``user_input_form``."""
        parameters = self.parameters()
        names = []
        for item in parameters.get("user_input_form") or []:
            if not isinstance(item, dict):
                continue
            for _kind, spec in item.items():
                if isinstance(spec, dict) and spec.get("variable"):
                    names.append(str(spec["variable"]))
        return names
