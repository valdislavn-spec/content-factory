"""LangGraph-движок пайплайна (опциональная зависимость).

Тот же пайплайн, что и у встроенного ``Orchestrator``, но шаги описаны как узлы
графа `LangGraph <https://www.langchain.com/langgraph>`_, а независимые шаги
выполняются параллельно:

``collect → (classify ∥ research) → write → (critique ∥ checks) → merge
→ (edit?) → (recheck → critique ∥ checks)? → finalize``

Что это даёт:

- **скорость** — классификация и исследование идут одновременно, критик и
  детерминированные проверки тоже; узкое место — самый долгий шаг, а не сумма;
- **качество** — после критики добавляются дешёвые проверки (цифры/годы из
  источников, длина, банворды), а конфиг ``max_revision_rounds`` разрешает
  повторную редактуру, если после правок остались замечания;
- **безопасность не меняется** — узлы вызывают MCP-инструменты кодом, модель
  их не получает; dry-run по умолчанию.

Установка (Python 3.9 получает ветку 0.6.x, Python 3.10+ — 1.x)::

    pip install "langgraph>=0.6,<2"

Запуск::

    python -m mcp_factory demo --engine langgraph
    python -m mcp_factory run --config config/ollama.json --engine langgraph
    python -m mcp_factory demo --engine langgraph --revision-rounds 2

Подробности — ``docs/langgraph.md``.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, TypedDict

from .domain import Article
from .orchestrator import Orchestrator
from .quality import deterministic_issues
from .rendering import render_post

try:  # опциональная зависимость: без неё проект работает как раньше
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except ImportError:  # pragma: no cover - зависит от окружения
    END = START = StateGraph = None  # type: ignore[assignment]
    LANGGRAPH_AVAILABLE = False


INSTALL_HINT = (
    'LangGraph не установлен. Установите: pip install "langgraph>=0.6,<2" '
    "(на Python 3.9 pip возьмёт 0.6.x, на Python 3.10+ — 1.x)."
)


def langgraph_version() -> Optional[str]:
    """Версия установленного LangGraph (None, если пакет не установлен)."""
    if not LANGGRAPH_AVAILABLE:
        return None
    try:
        from importlib.metadata import version

        return version("langgraph")
    except Exception:  # noqa: BLE001 - версия не критична для работы
        return None


def require_langgraph() -> None:
    """Понятная ошибка вместо ImportError в глубине langgraph."""
    if not LANGGRAPH_AVAILABLE:
        raise RuntimeError(INSTALL_HINT)


class FlowState(TypedDict, total=False):
    """Состояние графа: те же данные, что проходят через пайплайн."""

    articles: List[Article]
    classification: Dict[str, Any]
    research: Dict[str, Any]
    title: str
    draft: str
    critique: Dict[str, Any]
    check_issues: List[str]
    ground_issues: List[str]
    body: str
    markdown: str
    saved: Dict[str, Any]
    published: Optional[Dict[str, Any]]
    revisions: int


class LangGraphOrchestrator(Orchestrator):
    """Оркестратор с тем же пайплайном, но исполнением через LangGraph."""

    engine = "langgraph"

    def _timed(self, name: str, node: Callable[[FlowState], Dict[str, Any]]):
        """Обернуть узел замером времени (пишется в run-лог)."""

        def wrapped(state: FlowState) -> Dict[str, Any]:
            started = time.time()
            result = node(state)
            self.timings[name] = self.timings.get(name, 0) + int(
                (time.time() - started) * 1000
            )
            return result

        wrapped.__name__ = "timed_{}".format(name)
        return wrapped

    def build_graph(self):
        """Собрать и скомпилировать граф пайплайна."""
        require_langgraph()
        graph = StateGraph(FlowState)
        graph.add_node("collect", self._timed("collect", self._node_collect))
        graph.add_node("classify", self._timed("classify", self._node_classify))
        graph.add_node("research", self._timed("research", self._node_research))
        graph.add_node("write", self._timed("write", self._node_write))
        graph.add_node("critique", self._timed("critique", self._node_critique))
        graph.add_node("checks", self._timed("checks", self._node_checks))
        graph.add_node("ground", self._timed("ground", self._node_ground))
        graph.add_node("merge", self._timed("merge", self._node_merge))
        graph.add_node("edit", self._timed("edit", self._node_edit))
        graph.add_node("recheck", self._timed("recheck", self._node_recheck))
        graph.add_node("finalize", self._timed("finalize", self._node_finalize))

        graph.add_edge(START, "collect")
        # Независимые шаги — параллельно: время = max(классификация, исследование).
        graph.add_edge("collect", "classify")
        graph.add_edge("collect", "research")
        graph.add_edge("classify", "write")
        graph.add_edge("research", "write")
        # Критик, детерминированные проверки и RAG-фактчек — параллельно.
        graph.add_edge("write", "critique")
        graph.add_edge("write", "checks")
        graph.add_edge("write", "ground")
        graph.add_edge("critique", "merge")
        graph.add_edge("checks", "merge")
        graph.add_edge("ground", "merge")
        graph.add_conditional_edges(
            "merge",
            self._route_after_critique,
            {"edit": "edit", "finalize": "finalize"},
        )
        # Повторная редактура (если разрешена max_revision_rounds): цикл назад
        # в критику и проверки, иначе — сразу финализация.
        graph.add_conditional_edges(
            "edit",
            self._route_after_edit,
            {"recheck": "recheck", "finalize": "finalize"},
        )
        graph.add_edge("recheck", "critique")
        graph.add_edge("recheck", "checks")
        graph.add_edge("recheck", "ground")
        graph.add_edge("finalize", END)
        return graph.compile()

    # -- узлы графа: тонкие обёртки над шагами Orchestrator -----------------

    def _node_collect(self, state: FlowState) -> Dict[str, Any]:
        articles = self._collect_articles()
        self.log("[1/6] собрано новостей: {}".format(len(articles)))
        return {"articles": articles}

    def _node_classify(self, state: FlowState) -> Dict[str, Any]:
        articles = state.get("articles") or []
        classification = self._classify(articles)
        topic = classification.get("topic", "—") if classification else "—"
        self.log("[2/6] классификация: {}".format(topic))
        return {"classification": classification}

    def _node_research(self, state: FlowState) -> Dict[str, Any]:
        research = self._research(state.get("articles") or [])
        self.log(
            "[3/6] исследование: {} фактов, источники {}".format(
                len(research.get("facts", [])), research.get("used", [])
            )
        )
        return {"research": research}

    def _node_write(self, state: FlowState) -> Dict[str, Any]:
        title, draft = self._write(
            state.get("research") or {}, state.get("articles") or []
        )
        self.log("[4/6] черновик: «{}» ({} знаков)".format(title, len(draft)))
        return {"title": title, "draft": draft, "body": "", "revisions": 0}

    def _node_critique(self, state: FlowState) -> Dict[str, Any]:
        critique = self._critique(
            state.get("draft") or "",
            state.get("research") or {},
            state.get("articles") or [],
        )
        return {"critique": critique}

    def _node_checks(self, state: FlowState) -> Dict[str, Any]:
        """Детерминированные проверки черновика (без LLM, ~0 мс)."""
        title = str(state.get("title") or "")
        body = str(state.get("body") or state.get("draft") or "")
        issues = deterministic_issues(
            title,
            body,
            state.get("research") or {},
            state.get("articles") or [],
            self.config.pipeline,
        )
        if issues:
            self.log(
                "проверки: {} замечаний ({})".format(
                    len(issues), "; ".join(issues)[:200]
                )
            )
        return {"check_issues": issues}

    def _node_ground(self, state: FlowState) -> Dict[str, Any]:
        """RAG-фактчек (опция B): сверка цифр черновика с пассажами источников.

        Использует LangChain + BM25 из ``grounding.py``. Включён, только если в
        конфиге ``pipeline.grounding: true``; без LangChain просто пропускается.
        """
        if not bool(self.config.pipeline.get("grounding", False)):
            return {"ground_issues": []}
        try:
            from .grounding import (  # noqa: WPS433 - опциональная зависимость
                INSTALL_HINT,
                LANGCHAIN_AVAILABLE,
                grounding_issues,
            )
        except Exception as exc:  # pragma: no cover - защита от битой установки
            self.log("RAG-фактчек недоступен: {}".format(exc))
            return {"ground_issues": []}
        if not LANGCHAIN_AVAILABLE:
            self.log("RAG-фактчек: LangChain не установлен — пропуск ({})".format(INSTALL_HINT))
            return {"ground_issues": []}
        body = str(state.get("body") or state.get("draft") or "")
        issues = grounding_issues(body, state.get("articles") or [])
        if issues:
            self.log(
                "RAG-фактчек: {} замечаний ({})".format(
                    len(issues), "; ".join(issues)[:200]
                )
            )
        return {"ground_issues": issues}

    def _node_merge(self, state: FlowState) -> Dict[str, Any]:
        """Объединить замечания критика, детерминированных проверок и RAG."""
        critique = dict(state.get("critique") or {})
        issues = list(critique.get("issues") or [])
        check_issues = [issue for issue in (state.get("check_issues") or []) if issue]
        ground_issues = [issue for issue in (state.get("ground_issues") or []) if issue]
        added = [
            issue
            for issue in list(check_issues) + list(ground_issues)
            if issue not in issues
        ]
        issues.extend(added)
        verdict = str(critique.get("verdict") or "ok")
        if added:
            verdict = "revise"
        merged = {
            "verdict": verdict,
            "issues": issues,
            "fact_checks": critique.get("fact_checks") or [],
        }
        self.log(
            "[5/6] критика: {} (замечаний: {}, проверок: {}, RAG: {})".format(
                verdict, len(issues), len(check_issues), len(ground_issues)
            )
        )
        return {"critique": merged}

    def _route_after_critique(self, state: FlowState) -> str:
        """Нужна ли редактура: есть замечания и не исчерпаны раунды."""
        critique = state.get("critique") or {}
        verdict = str(critique.get("verdict") or "ok")
        needs_edit = verdict != "ok" or bool(critique.get("issues"))
        if not needs_edit:
            return "finalize"
        max_rounds = max(1, int(self.config.pipeline_value("max_revision_rounds", 1)))
        revisions = int(state.get("revisions") or 0)
        if revisions >= max_rounds:
            return "finalize"
        if not self.router.has_role("editor"):
            return "finalize"
        return "edit"

    def _node_edit(self, state: FlowState) -> Dict[str, Any]:
        title, body = self._edit(
            state.get("draft") or "",
            state.get("title") or "",
            state.get("critique") or {},
            state.get("research") or {},
            state.get("articles") or [],
        )
        revisions = int(state.get("revisions") or 0) + 1
        self.log(
            "[6/6] редактура #{}: «{}» ({} знаков)".format(revisions, title, len(body))
        )
        # draft = body, чтобы повторная критика проверяла уже исправленный текст
        return {"title": title, "body": body, "draft": body, "revisions": revisions}

    def _route_after_edit(self, state: FlowState) -> str:
        """Если раунды редактуры ещё есть — вернуться к критике и проверкам."""
        max_rounds = max(1, int(self.config.pipeline_value("max_revision_rounds", 1)))
        revisions = int(state.get("revisions") or 0)
        if revisions < max_rounds:
            return "recheck"
        return "finalize"

    def _node_recheck(self, state: FlowState) -> Dict[str, Any]:
        """Пустой узел-развилка: запускает критику, проверки и RAG заново."""
        return {"check_issues": [], "ground_issues": []}

    def _node_finalize(self, state: FlowState) -> Dict[str, Any]:
        """Хештеги, источники, сохранение черновика и (опционально) публикация."""
        articles = state.get("articles") or []
        research = state.get("research") or {}
        title = str(state.get("title") or (articles[0].title if articles else ""))
        body = str(state.get("body") or state.get("draft") or "")
        if not state.get("body"):
            self.log("[6/6] редактура: без изменений (критик одобрил)")
        body = self._add_hashtags(body)
        sources = [articles[index - 1] for index in research.get("used", [])]
        markdown = render_post(
            title, body, [article.as_source() for article in sources]
        )
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
        return {
            "title": title,
            "body": body,
            "markdown": markdown,
            "saved": saved,
            "published": published,
        }

    # -- запуск -------------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        """Полный запуск: подготовить каталоги, MCP-серверы, выполнить граф."""
        require_langgraph()
        self.timings = {}
        self.out_dir.mkdir(parents=True, exist_ok=True)
        for subdir in ("drafts", "outbox", "runs"):
            (self.out_dir / subdir).mkdir(exist_ok=True)
        try:
            self._start_servers()
            graph = self.build_graph()
            state = graph.invoke({})
            articles = state.get("articles") or []
            research = state.get("research") or {}
            title = str(state.get("title") or "")
            body = str(state.get("body") or "")
            markdown = str(state.get("markdown") or "")
            saved = state.get("saved") or {}
            published = state.get("published")
            run_log = self._write_run_log(
                articles=articles,
                classification=state.get("classification") or {},
                research=research,
                critique=state.get("critique") or {},
                title=title,
                body=body,
                markdown=markdown,
                saved=saved,
                published=published,
            )
            return self._finish(
                title=title,
                markdown=markdown,
                saved=saved,
                run_log=run_log,
                published=published,
                articles_count=len(articles),
            )
        finally:
            self._close_servers()
