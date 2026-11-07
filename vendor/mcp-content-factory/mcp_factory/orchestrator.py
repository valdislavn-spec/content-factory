"""Оркестратор: связывает модели, MCP-инструменты и контент-пайплайн."""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import FactoryConfig
from .domain import Article, ToolCall
from .mcp_client import MCPClient
from .models import build_provider
from .prompts import (
    classifier_messages,
    critic_messages,
    editor_messages,
    researcher_messages,
    writer_messages,
)
from .quality import deterministic_issues
from .rendering import render_post
from .router import ModelRouter
from .utils import now_iso, truncate

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def normalize_url(url: str) -> str:
    """Убрать трекинг-параметры и фрагмент, чтобы дедуп работал."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.scheme:
        return url.strip()
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in ("fbclid", "gclid", "yclid")
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def parse_title_body(text: str) -> tuple:
    """Разобрать ответ модели на заголовок и тело."""
    text = (text or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(?:ЗАГОЛОВОК|TITLE)\s*:\s*(.+)$", line, re.I)
        if match:
            body = "\n".join(lines[index + 1 :]).strip()
            return match.group(1).strip(), body
    if lines and lines[0].startswith("#"):
        return lines[0].lstrip("#").strip(), "\n".join(lines[1:]).strip()
    if lines:
        return lines[0].strip(), "\n".join(lines[1:]).strip()
    return "", ""


class Orchestrator:
    """Пайплайн: сбор → классификация → исследование → черновик → критика →
    редактура → сохранение (→ публикация)."""

    #: Движок исполнения: встроенный пошаговый пайплайн (см. langgraph_flow.py).
    engine = "pipeline"

    def __init__(
        self,
        config: FactoryConfig,
        out_dir: Path,
        publish: bool = False,
        logger=None,
        injected_articles: Optional[List[Article]] = None,
    ):
        self.config = config
        self.out_dir = Path(out_dir).resolve()
        self.publish = bool(publish)
        # Готовые статьи (мост из content-factory): не ходим в RSS повторно.
        self.injected_articles = (
            list(injected_articles) if injected_articles is not None else None
        )
        self.log = logger or (lambda message: print(message, flush=True))
        providers = {
            name: build_provider(name, provider_config)
            for name, provider_config in config.providers.items()
        }
        self.router = ModelRouter(
            providers=providers,
            routes=config.routes,
            budget_tokens=config.budget_tokens,
        )
        self.clients: Dict[str, MCPClient] = {}
        self.tool_owner: Dict[str, str] = {}
        self.tool_calls: List[ToolCall] = []
        self.started_at = now_iso()
        self.started_ts = time.time()
        self.timings: Dict[str, int] = {}

    # -- servers ----------------------------------------------------------

    def _start_servers(self) -> None:
        for name, server in self.config.servers.items():
            if server.builtin:
                command = [
                    sys.executable,
                    "-m",
                    "mcp_factory.mcp_server",
                    "--root",
                    str(self.out_dir),
                ]
                if self.publish:
                    command.append("--allow-publish")
                cwd = str(PROJECT_ROOT)
                env = os.environ.copy()
                existing = env.get("PYTHONPATH", "")
                env["PYTHONPATH"] = (
                    str(PROJECT_ROOT) + (os.pathsep + existing if existing else "")
                )
                env.update(server.env)
            else:
                command = list(server.command)
                cwd = server.cwd or str(PROJECT_ROOT)
                env = os.environ.copy()
                env.update(server.env)
            client = MCPClient(
                command=command,
                cwd=cwd,
                env=env,
                timeout=server.timeout,
                name="mcp-factory",
            )
            client.start()
            tools = client.list_tools()
            if not tools:
                client.close()
                raise RuntimeError("MCP-сервер {!r} не отдал ни одного инструмента".format(name))
            for tool in tools:
                tool_name = str(tool.get("name", ""))
                if not tool_name:
                    continue
                if tool_name in self.tool_owner:
                    self.log(
                        "предупреждение: инструмент {!r} уже есть у {!r}, "
                        "побеждает {!r}".format(tool_name, self.tool_owner[tool_name], name)
                    )
                self.tool_owner[tool_name] = name
            self.clients[name] = client
            self.log(
                "MCP: {} — {} инструментов, протокол {}".format(
                    name, len(tools), client.protocol
                )
            )

    def _close_servers(self) -> None:
        for client in self.clients.values():
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
        self.clients.clear()

    def _call_tool(self, name: str, arguments: Dict[str, Any], timeout: Optional[float] = None):
        owner = self.tool_owner.get(name)
        if not owner:
            raise RuntimeError("инструмент {!r} не найден ни на одном MCP-сервере".format(name))
        started = time.time()
        safe_arguments = {}
        for key, value in arguments.items():
            if isinstance(value, str):
                safe_arguments[key] = truncate(value, 200)
            elif isinstance(value, list):
                safe_arguments[key] = value[:3]
            else:
                safe_arguments[key] = value
        try:
            result = self.clients[owner].call_tool(name, arguments, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            self.tool_calls.append(
                ToolCall(
                    server=owner,
                    name=name,
                    arguments=safe_arguments,
                    ok=False,
                    ms=int((time.time() - started) * 1000),
                    error=str(exc)[:500],
                )
            )
            raise
        self.tool_calls.append(
            ToolCall(
                server=owner,
                name=name,
                arguments=safe_arguments,
                ok=True,
                ms=int((time.time() - started) * 1000),
            )
        )
        return result

    def _call_tool_json(self, name: str, arguments: Dict[str, Any]) -> Any:
        result = self._call_tool(name, arguments)
        if result.structured is not None:
            return result.structured
        return json.loads(result.text)

    # -- pipeline ---------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "drafts").mkdir(exist_ok=True)
        (self.out_dir / "outbox").mkdir(exist_ok=True)
        (self.out_dir / "runs").mkdir(exist_ok=True)
        try:
            self._start_servers()
            articles = self._collect_articles()
            self.log("[1/6] собрано новостей: {}".format(len(articles)))

            classification = self._classify(articles)
            topic = classification.get("topic", "—") if classification else "—"
            self.log("[2/6] классификация: {}".format(topic))

            research = self._research(articles)
            self.log(
                "[3/6] исследование: {} фактов, источники {}".format(
                    len(research.get("facts", [])), research.get("used", [])
                )
            )

            title, draft = self._write(research, articles)
            self.log("[4/6] черновик: «{}» ({} знаков)".format(title, len(draft)))

            critique = self._critique(draft, research, articles)
            critique, check_issues = self._apply_checks(
                critique, title, draft, research, articles
            )
            self.log(
                "[5/6] критика: {} (замечаний: {}, проверок: {})".format(
                    critique.get("verdict"),
                    len(critique.get("issues", [])),
                    len(check_issues),
                )
            )

            title, body = self._edit(draft, title, critique, research, articles)
            body = self._add_hashtags(body)
            sources = [articles[index - 1] for index in research["used"]]
            markdown = render_post(title, body, [article.as_source() for article in sources])
            self.log("[6/6] редактура: «{}» ({} знаков)".format(title, len(body)))

            saved = self._call_tool_json(
                "save_draft",
                {
                    "channel": self.config.pipeline.get("channel", "tech-ai"),
                    "title": title,
                    "body": body,
                    "sources": [article.as_source() for article in sources],
                },
            )
            published = self._publish(title, body)
            run_log = self._write_run_log(
                articles=articles,
                classification=classification,
                research=research,
                critique=critique,
                title=title,
                body=body,
                markdown=markdown,
                saved=saved,
                published=published,
            )
            unique_models = sorted(
                {
                    "{}:{}".format(record.provider, record.model)
                    for record in self.router.records
                    if record.ok
                }
            )
            return self._finish(
                title=title,
                markdown=markdown,
                saved=saved,
                run_log=run_log,
                published=published,
                articles_count=len(articles),
                unique_models=unique_models,
            )
        finally:
            self._close_servers()

    def _finish(
        self,
        *,
        title: str,
        markdown: str,
        saved: Dict[str, Any],
        run_log: Path,
        published: Optional[Dict[str, Any]],
        articles_count: int,
        unique_models: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Напечатать итог запуска и вернуть результат (общий для движков)."""
        if unique_models is None:
            unique_models = sorted(
                {
                    "{}:{}".format(record.provider, record.model)
                    for record in self.router.records
                    if record.ok
                }
            )
        self.log("=" * 56)
        self.log("Готово. Черновик: {}".format(saved.get("path")))
        self.log("Модели: {}".format(", ".join(unique_models) or "—"))
        self.log("Токены (оценка): {}".format(self.router.used_tokens))
        self.log("Run-лог: {}".format(run_log))
        self.log("Движок: {}".format(self.engine))
        duration_ms = int((time.time() - getattr(self, "started_ts", time.time())) * 1000)
        self.log("Время: {:.2f} с".format(duration_ms / 1000.0))
        if published:
            self.log("Публикация: {}".format(published.get("status")))
        return {
            "title": title,
            "markdown": markdown,
            "draft_path": saved.get("path"),
            "run_log": str(run_log),
            "published": published,
            "articles": articles_count,
            "router": self.router.summary(),
            "engine": self.engine,
            "duration_ms": duration_ms,
            "timings": dict(getattr(self, "timings", {})),
        }

    # -- stages -----------------------------------------------------------

    def _collect_articles(self) -> List[Article]:
        if self.injected_articles is not None:
            return list(self.injected_articles)
        raw_items: List[Dict[str, str]] = []
        for feed in self.config.feeds:
            try:
                payload = self._call_tool_json("fetch_rss", {"url": feed, "limit": 20})
            except Exception as exc:  # noqa: BLE001 — одна лента не должна ронять всё
                self.log("предупреждение: лента {} недоступна: {}".format(feed, exc))
                continue
            label = str(payload.get("label") or feed)
            for item in payload.get("items") or []:
                title = str(item.get("title") or "").strip()
                link = str(item.get("link") or "").strip()
                if not title:
                    continue
                raw_items.append(
                    {
                        "title": title,
                        "url": link,
                        "summary": str(item.get("summary") or "").strip(),
                        "published": str(item.get("published") or ""),
                        "source": label,
                    }
                )

        unique: List[Dict[str, str]] = []
        seen = set()
        for item in raw_items:
            key = normalize_url(item["url"]) or item["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)

        unique.sort(key=lambda item: item.get("published") or "", reverse=True)
        limit = int(self.config.pipeline.get("max_articles", 8))
        unique = unique[: max(1, limit)]
        minimum = int(self.config.pipeline.get("min_articles", 2))
        if len(unique) < minimum:
            raise RuntimeError(
                "слишком мало новостей: {} (нужно минимум {})".format(len(unique), minimum)
            )
        return [
            Article(
                index=index,
                title=item["title"],
                url=item["url"],
                summary=item["summary"],
                source=item["source"],
                published=item["published"],
            )
            for index, item in enumerate(unique, start=1)
        ]

    def _classify(self, articles: List[Article]) -> Dict[str, Any]:
        if not self.router.has_role("classifier"):
            return {}
        try:
            data, _ = self.router.complete_json(
                "classifier", classifier_messages(articles)
            )
        except Exception as exc:  # noqa: BLE001 — классификация не критична
            self.log("предупреждение: классификатор недоступен: {}".format(exc))
            return {}
        return data if isinstance(data, dict) else {}

    def _research(self, articles: List[Article]) -> Dict[str, Any]:
        channel = str(self.config.pipeline.get("channel", "tech-ai"))
        if not self.router.has_role("researcher"):
            used = list(range(1, min(3, len(articles)) + 1))
            return {
                "facts": [article.title for article in articles[:3]],
                "numbers": [],
                "angles": [],
                "used": used,
                "confidence": 0.0,
            }
        try:
            data, _ = self.router.complete_json(
                "researcher", researcher_messages(articles, channel)
            )
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("исследователь не смог обработать новости: {}".format(exc)) from exc
        data = data if isinstance(data, dict) else {}
        used: List[int] = []
        for value in data.get("used") or []:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if 1 <= number <= len(articles) and number not in used:
                used.append(number)
        if not used:
            used = [1]
        facts = [str(item) for item in (data.get("facts") or []) if str(item).strip()]
        if not facts:
            facts = [article.title for article in articles[:3]]
        numbers = [str(item) for item in (data.get("numbers") or []) if str(item).strip()]
        angles = [str(item) for item in (data.get("angles") or []) if str(item).strip()]
        return {
            "facts": facts[:6],
            "numbers": numbers[:4],
            "angles": angles[:4],
            "used": sorted(used),
            "confidence": data.get("confidence", 0.5),
        }

    def _write(self, research: Dict[str, Any], articles: List[Article]) -> tuple:
        channel = str(self.config.pipeline.get("channel", "tech-ai"))
        language = str(self.config.pipeline.get("language") or "ru")
        completion = self.router.complete(
            "writer", writer_messages(research, articles, channel, language=language)
        )
        title, body = parse_title_body(completion.text)
        if not title:
            title = articles[0].title
        if len(body) < 80:
            body = completion.text.strip()
        return title, body

    def _critique(
        self,
        draft: str,
        research: Dict[str, Any],
        articles: List[Article],
    ) -> Dict[str, Any]:
        if not self.router.has_role("critic"):
            return {"verdict": "ok", "issues": [], "fact_checks": []}
        try:
            data, _ = self.router.complete_json(
                "critic", critic_messages(draft, research, articles)
            )
        except Exception as exc:  # noqa: BLE001
            self.log("предупреждение: критик недоступен: {}".format(exc))
            return {"verdict": "ok", "issues": [], "fact_checks": []}
        data = data if isinstance(data, dict) else {}
        issues = [str(item) for item in (data.get("issues") or []) if str(item).strip()]
        return {
            "verdict": str(data.get("verdict") or "ok"),
            "issues": issues,
            "fact_checks": data.get("fact_checks") or [],
        }

    def _edit(
        self,
        draft: str,
        title: str,
        critique: Dict[str, Any],
        research: Dict[str, Any],
        articles: List[Article],
    ) -> tuple:
        needs_edit = critique.get("verdict") != "ok" or bool(critique.get("issues"))
        if not needs_edit or not self.router.has_role("editor"):
            return title, draft
        try:
            completion = self.router.complete(
                "editor",
                editor_messages(
                    draft,
                    critique.get("issues") or [],
                    research,
                    articles,
                    language=str(self.config.pipeline.get("language") or "ru"),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self.log("предупреждение: редактор недоступен: {}".format(exc))
            return title, draft
        new_title, new_body = parse_title_body(completion.text)
        if not new_title:
            new_title = title
        if len(new_body) < 80:
            return title, draft
        return new_title, new_body

    def _apply_checks(
        self,
        critique: Dict[str, Any],
        title: str,
        body: str,
        research: Dict[str, Any],
        articles: List[Article],
    ) -> tuple:
        """Добавить к критике детерминированные проверки черновика.

        Возвращает (объединённая критика, список найденных проверками замечаний).
        """
        check_issues = deterministic_issues(
            title, body, research, articles, self.config.pipeline
        )
        if not check_issues:
            return critique or {}, []
        merged = dict(critique or {})
        issues = list(merged.get("issues") or [])
        for issue in check_issues:
            if issue not in issues:
                issues.append(issue)
        merged["issues"] = issues
        merged["verdict"] = "revise"
        merged.setdefault("fact_checks", [])
        return merged, check_issues

    def _add_hashtags(self, body: str) -> str:
        tags = [str(tag) for tag in (self.config.pipeline.get("hashtags") or []) if str(tag)]
        if not tags:
            return body
        return body.rstrip() + "\n\n" + " ".join(tags)

    def _publish(self, title: str, body: str) -> Dict[str, Any]:
        if not self.publish:
            return {"status": "skipped", "reason": "запуск без --publish"}
        chat_id = str(self.config.pipeline.get("telegram_chat_id") or "").strip()
        if not chat_id:
            return {"status": "skipped", "reason": "не задан pipeline.telegram_chat_id"}
        text = "{}\n\n{}".format(title, body)
        try:
            payload = self._call_tool_json(
                "publish_telegram", {"chat_id": chat_id, "text": text}
            )
        except Exception as exc:  # noqa: BLE001
            self.log("публикация не удалась: {}".format(exc))
            return {"status": "error", "error": str(exc)[:500]}
        return payload if isinstance(payload, dict) else {"status": "unknown"}

    # -- observability ----------------------------------------------------

    def _write_run_log(
        self,
        articles: List[Article],
        classification: Dict[str, Any],
        research: Dict[str, Any],
        critique: Dict[str, Any],
        title: str,
        body: str,
        markdown: str,
        saved: Dict[str, Any],
        published: Optional[Dict[str, Any]],
    ) -> Path:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = self.out_dir / "runs" / ("run-{}.json".format(stamp))
        router_summary = self.router.summary()
        payload = {
            "started_at": self.started_at,
            "finished_at": now_iso(),
            "engine": self.engine,
            "duration_ms": int(
                (time.time() - getattr(self, "started_ts", time.time())) * 1000
            ),
            "timings": dict(getattr(self, "timings", {})),
            "config": str(self.config.path) if self.config.path else None,
            "feeds": self.config.feeds,
            "out_dir": str(self.out_dir),
            "articles": [article.as_dict() for article in articles],
            "classification": classification,
            "research": research,
            "critique": critique,
            "draft": {
                "path": saved.get("path"),
                "title": title,
                "channel": saved.get("channel"),
                "chars": len(markdown),
            },
            "published": published,
            "model_calls": router_summary["calls"],
            "tool_calls": [call.as_dict() for call in self.tool_calls],
            "usage": {
                "used_tokens": router_summary["used_tokens"],
                "budget_tokens": router_summary["budget_tokens"],
                "failures": router_summary["failures"],
            },
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path
