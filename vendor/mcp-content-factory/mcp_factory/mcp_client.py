"""Минимальный MCP-клиент для stdio-транспорта.

Поддерживает две эры протокола:

* modern (2026-07-28): stateless, версия и capabilities в `_meta` каждого
  запроса, результаты с `resultType`;
* legacy (2025-11-25 и раньше): handshake `initialize` +
  `notifications/initialized`.

Клиент сам выбирает эру через `server/discover` и fallback. Зависимостей нет.
"""

from __future__ import annotations

import json
import logging
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MODERN_VERSION = "2026-07-28"
LEGACY_VERSION = "2025-11-25"

LOGGER = logging.getLogger("mcp_factory.client")


class MCPError(RuntimeError):
    """Ошибка протокола или транспорта."""

    def __init__(self, message: str, code: Optional[int] = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class MCPTimeout(MCPError):
    """Сервер не ответил за отведённое время."""


class MCPToolError(MCPError):
    """Инструмент вернул isError=true (ошибка исполнения, а не протокола)."""


@dataclass
class ToolResult:
    name: str
    text: str
    structured: Any = None
    raw: Dict[str, Any] = field(default_factory=dict)


class MCPClient:
    """Запускает MCP-сервер как подпроцесс и общается по JSON-RPC 2.0."""

    def __init__(
        self,
        command: List[str],
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        name: str = "mcp-factory",
        version: str = "1.0.0",
    ):
        if not command:
            raise ValueError("command не может быть пустым")
        self.command = [str(part) for part in command]
        self.cwd = cwd
        self.env = env
        self.timeout = float(timeout)
        self.name = name
        self.version = version

        self.proc: Optional[subprocess.Popen] = None
        self.protocol = MODERN_VERSION
        self.modern = True
        self.server_info: Dict[str, Any] = {}
        self._queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._request_id = 0
        self._lock = threading.Lock()
        self._started = False

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> "MCPClient":
        if self._started:
            return self
        LOGGER.debug("запуск MCP-сервера: %s", " ".join(self.command))
        self.proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=self.cwd,
            env=self.env,
        )
        assert self.proc.stdout is not None
        assert self.proc.stderr is not None
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self._started = True
        try:
            self._discover()
        except Exception:
            self.close()
            raise
        return self

    def close(self) -> None:
        if not self.proc:
            return
        proc = self.proc
        self.proc = None
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        for stream in (proc.stdout, proc.stderr):
            try:
                if stream:
                    stream.close()
            except Exception:  # noqa: BLE001
                pass
        self._started = False

    def __enter__(self) -> "MCPClient":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- IO threads --------------------------------------------------------

    def _read_stdout(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                LOGGER.warning("сервер прислал не-JSON в stdout: %s", line[:200])
                continue
            if isinstance(message, dict):
                self._queue.put(message)
        self._queue.put({"__eof__": True})

    def _read_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        for line in self.proc.stderr:
            LOGGER.debug("mcp-server: %s", line.rstrip())

    # -- JSON-RPC ----------------------------------------------------------

    def _write(self, message: Dict[str, Any]) -> None:
        if not self.proc or not self.proc.stdin:
            raise MCPError("MCP-сервер не запущен")
        payload = json.dumps(message, ensure_ascii=False)
        if "\n" in payload:
            raise MCPError("внутри JSON-RPC сообщения оказался перевод строки")
        self.proc.stdin.write(payload + "\n")
        self.proc.stdin.flush()

    def _send(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        request_id: Optional[int] = None,
        notification: bool = False,
    ) -> None:
        message: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if not notification:
            message["id"] = request_id
        self._write(message)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _wait(self, request_id: int, timeout: float) -> Dict[str, Any]:
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise MCPTimeout("нет ответа на запрос id={} за {:.1f} с".format(request_id, timeout))
            try:
                message = self._queue.get(timeout=remaining)
            except queue.Empty:
                raise MCPTimeout(
                    "нет ответа на запрос id={} за {:.1f} с".format(request_id, timeout)
                )
            if message.get("__eof__"):
                raise MCPError("MCP-сервер закрыл соединение")
            if message.get("id") == request_id and (
                "result" in message or "error" in message
            ):
                return message
            # Уведомления и чужие ответы не должны ломать текущий запрос.
            LOGGER.debug("пропущено сообщение: %s", str(message)[:200])

    def _meta(self) -> Dict[str, Any]:
        return {
            "io.modelcontextprotocol/protocolVersion": self.protocol,
            "io.modelcontextprotocol/clientInfo": {
                "name": self.name,
                "version": self.version,
            },
            "io.modelcontextprotocol/clientCapabilities": {},
        }

    def _request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            request_id = self._next_id()
            prepared = dict(params or {})
            if self.modern:
                prepared["_meta"] = self._meta()
            self._send(method, prepared, request_id=request_id)
            message = self._wait(request_id, timeout or self.timeout)
        if "error" in message:
            error = message.get("error") or {}
            raise MCPError(
                str(error.get("message") or "MCP error"),
                code=error.get("code"),
                data=error.get("data"),
            )
        result = message.get("result")
        if not isinstance(result, dict):
            raise MCPError("неожиданный result: {}".format(type(result)))
        return result

    # -- discovery ---------------------------------------------------------

    def _discover(self) -> None:
        """Определить эру и версию протокола.

        Сначала пробуем modern `server/discover`. Если сервер старый и отвечает
        ошибкой/молчит — откатываемся на legacy `initialize`.
        """
        request_id = self._next_id()
        try:
            self._send(
                "server/discover",
                {"_meta": self._meta()},
                request_id=request_id,
            )
            message = self._wait(request_id, min(self.timeout, 10))
        except MCPTimeout:
            LOGGER.info("server/discover не ответил — пробуем legacy initialize")
            self._legacy_handshake()
            return

        if "error" in message:
            error = message.get("error") or {}
            code = error.get("code")
            if code == -32022:
                supported = (error.get("data") or {}).get("supported") or []
                if MODERN_VERSION in supported:
                    self.protocol = MODERN_VERSION
                    self.modern = True
                    return
            LOGGER.info("server/discover вернул ошибку %s — legacy initialize", code)
            self._legacy_handshake()
            return

        result = message.get("result") or {}
        versions = result.get("supportedVersions") or []
        self.server_info = result.get("_meta", {}).get(
            "io.modelcontextprotocol/serverInfo", {}
        ) or {}
        if MODERN_VERSION in versions:
            self.protocol = MODERN_VERSION
            self.modern = True
            return
        LOGGER.info("сервер не поддерживает %s — legacy initialize", MODERN_VERSION)
        self._legacy_handshake()

    def _legacy_handshake(self) -> None:
        self.modern = False
        self.protocol = LEGACY_VERSION
        request_id = self._next_id()
        self._send(
            "initialize",
            {
                "protocolVersion": LEGACY_VERSION,
                "capabilities": {},
                "clientInfo": {"name": self.name, "version": self.version},
            },
            request_id=request_id,
        )
        message = self._wait(request_id, self.timeout)
        if "error" in message:
            error = message.get("error") or {}
            raise MCPError(
                "legacy initialize не удался: {}".format(error.get("message")),
                code=error.get("code"),
            )
        result = message.get("result") or {}
        self.protocol = str(result.get("protocolVersion") or LEGACY_VERSION)
        self.server_info = result.get("serverInfo") or {}
        self._send("notifications/initialized", {}, notification=True)

    # -- public API --------------------------------------------------------

    def list_tools(self) -> List[Dict[str, Any]]:
        result = self._request("tools/list", {})
        tools = result.get("tools") or []
        if not isinstance(tools, list):
            raise MCPError("tools/list вернул не список")
        return [tool for tool in tools if isinstance(tool, dict)]

    def call_tool(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> ToolResult:
        result = self._request(
            "tools/call",
            {"name": name, "arguments": dict(arguments or {})},
            timeout=timeout,
        )
        texts: List[str] = []
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(str(item.get("text", "")))
        text = "\n".join(texts)
        structured = result.get("structuredContent")
        tool_result = ToolResult(
            name=name, text=text, structured=structured, raw=result
        )
        if result.get("isError"):
            raise MCPToolError(
                text or "инструмент {} завершился с ошибкой".format(name),
                data=tool_result,
            )
        return tool_result

    def call_tool_json(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        result = self.call_tool(name, arguments, timeout=timeout)
        if result.structured is not None:
            return result.structured
        try:
            return json.loads(result.text)
        except ValueError as exc:
            raise MCPError(
                "инструмент {} вернул не-JSON: {}".format(name, result.text[:300])
            ) from exc
