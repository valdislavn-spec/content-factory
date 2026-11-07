"""CLI мультимодельного контент-завода."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from .config import ConfigError, load_config
from .mcp_client import MCPClient, MCPError
from .mcp_server import main as mcp_server_main
from .orchestrator import PROJECT_ROOT, Orchestrator
from .router import AllProvidersFailed, BudgetExceeded

logging.basicConfig(
    stream=sys.stderr,
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)


def _demo_config_path() -> Path:
    return PROJECT_ROOT / "config" / "demo.json"


def _run(
    config_path: Path,
    out_dir: Path,
    publish: bool,
    engine: str = "pipeline",
    revision_rounds: Optional[int] = None,
    tracing: Optional[bool] = None,
    grounding: bool = False,
) -> int:
    config = load_config(config_path)
    if revision_rounds is not None:
        config.pipeline["max_revision_rounds"] = max(1, int(revision_rounds))
    if grounding:
        config.pipeline["grounding"] = True
    # LangSmith-трейсинг (опция A): ключ можно хранить в .env проекта.
    from .tracing import configure_tracing, load_env_file

    load_env_file(PROJECT_ROOT / ".env")

    trace_status = configure_tracing(enabled=tracing)
    if trace_status.get("enabled"):
        print("LangSmith: трейсинг включён, проект {!r}".format(trace_status.get("project")))
    elif tracing:
        print("LangSmith: трейсинг не включён — {}".format(trace_status.get("reason")))
    if engine == "langgraph":
        # Импорт внутри ветки: без установленного LangGraph проект работает как раньше.
        from .langgraph_flow import LangGraphOrchestrator

        orchestrator = LangGraphOrchestrator(
            config=config, out_dir=out_dir, publish=publish
        )
    else:
        orchestrator = Orchestrator(config=config, out_dir=out_dir, publish=publish)
    result = orchestrator.run()
    if result.get("markdown"):
        print("\n--- Предпросмотр ---\n")
        print(result["markdown"])
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve() if args.config else _demo_config_path()
    print("MCP Content Factory: демо на mock-моделях")
    print("Конфиг: {}".format(config_path))
    print("Движок: {}".format(args.engine))
    print("Вывод:  {}\n".format(Path(args.out).resolve()))
    return _run(
        config_path,
        Path(args.out),
        args.publish,
        args.engine,
        args.revision_rounds,
        tracing=args.tracing,
        grounding=args.grounding,
    )


def cmd_run(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    return _run(
        config_path,
        Path(args.out),
        args.publish,
        args.engine,
        args.revision_rounds,
        tracing=args.tracing,
        grounding=args.grounding,
    )


def cmd_brain(args: argparse.Namespace) -> int:
    """Мост из content-factory: сгенерировать пост по готовым статьям.

    Читает JSON {"articles": [...], "channel": "...", "language": "en"} из
    stdin/файла и запускает пайплайн (по умолчанию LangGraph) без сбора RSS.
    В stdout — только JSON-результат, служебные логи — в stderr.
    """
    import json as json_module
    import sys as sys_module
    from pathlib import Path as PathClass

    from .domain import Article
    from .langgraph_flow import LangGraphOrchestrator
    from .orchestrator import Orchestrator
    from .tracing import configure_tracing, load_env_file

    load_env_file(PROJECT_ROOT / ".env")
    configure_tracing()

    if args.articles == "-":
        raw = sys_module.stdin.read()
    else:
        raw = PathClass(args.articles).read_text(encoding="utf-8")
    try:
        payload = json_module.loads(raw or "{}")
    except ValueError as exc:
        print("brain: невалидный JSON со статьями: {}".format(exc), file=sys_module.stderr)
        return 2
    items = payload.get("articles") or []
    if not items:
        print("brain: в payload нет articles", file=sys_module.stderr)
        return 2
    articles = []
    for index, item in enumerate(items, start=1):
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        articles.append(
            Article(
                index=int(item.get("index") or index),
                title=title,
                url=str(item.get("url") or ""),
                summary=str(item.get("summary") or ""),
                source=str(item.get("source") or ""),
                published=str(item.get("published") or ""),
            )
        )
    if not articles:
        print("brain: все статьи без заголовка", file=sys_module.stderr)
        return 2

    config = load_config(PathClass(args.config).resolve())
    channel = str(payload.get("channel") or args.channel)
    language = str(payload.get("language") or args.language)
    config.pipeline["channel"] = channel
    config.pipeline["language"] = language
    if args.revision_rounds is not None:
        config.pipeline["max_revision_rounds"] = max(1, int(args.revision_rounds))
    if args.grounding is not None:
        config.pipeline["grounding"] = bool(args.grounding)

    orchestrator_cls = LangGraphOrchestrator if args.engine == "langgraph" else Orchestrator
    orchestrator = orchestrator_cls(
        config=config,
        out_dir=PathClass(args.out).resolve(),
        publish=False,
        logger=lambda message: print(message, file=sys_module.stderr, flush=True),
        injected_articles=articles,
    )
    try:
        result = orchestrator.run()
    except Exception as exc:  # noqa: BLE001 - мост не должен ронять content-factory
        print("brain: ошибка генерации: {}".format(exc), file=sys_module.stderr)
        return 1
    published = result.get("published") or {}
    output = {
        "title": result.get("title") or "",
        "markdown": result.get("markdown") or "",
        "draft_path": result.get("draft_path"),
        "run_log": result.get("run_log"),
        "engine": result.get("engine"),
        "published": published.get("status"),
        "channel": channel,
        "language": language,
        "articles": len(articles),
    }
    print(json_module.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["markdown"] else 2


def cmd_mcp_server(args: argparse.Namespace) -> int:
    argv: List[str] = ["--root", args.root]
    if args.allow_publish:
        argv.append("--allow-publish")
    argv.extend(["--log-level", args.log_level])
    return mcp_server_main(argv)


def cmd_tools(args: argparse.Namespace) -> int:
    config = load_config(Path(args.config).resolve())
    server = next(iter(config.servers.values()))
    if not server.builtin and not server.command:
        print("Ошибка: у MCP-сервера нет command", file=sys.stderr)
        return 1
    if server.builtin:
        command = [
            sys.executable,
            "-m",
            "mcp_factory.mcp_server",
            "--root",
            str(Path(args.out).resolve()),
        ]
        cwd = str(PROJECT_ROOT)
        env = None
    else:
        command = server.command
        cwd = server.cwd or str(PROJECT_ROOT)
        env = None
    with MCPClient(command=command, cwd=cwd, env=env, timeout=server.timeout) as client:
        print("Протокол: {} (modern={})".format(client.protocol, client.modern))
        print("Сервер:   {}".format(client.server_info))
        for tool in client.list_tools():
            print("- {}: {}".format(tool.get("name"), tool.get("description", "")))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-factory",
        description=(
            "Мультимодельный контент-завод: LLM-роли + MCP-инструменты. "
            "Демо работает офлайн на mock-моделях."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="офлайн-демо на mock-моделях")
    demo.add_argument("--config", help="путь к конфигу (по умолчанию config/demo.json)")
    demo.add_argument("--out", default="out", help="каталог результатов")
    demo.add_argument("--publish", action="store_true", help="разрешить публикацию (dry-run по умолчанию)")
    demo.add_argument(
        "--engine",
        choices=["pipeline", "langgraph"],
        default="pipeline",
        help="движок исполнения: встроенный пайплайн или граф LangGraph "
        "(нужен pip install 'langgraph>=0.6,<2')",
    )
    demo.add_argument(
        "--revision-rounds",
        type=int,
        default=None,
        help="максимум раундов редактуры после критика (по умолчанию из конфига, "
        "1 = без повторной критики; работает в --engine langgraph)",
    )
    demo.add_argument(
        "--tracing",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="LangSmith-трейсинг (нужен LANGSMITH_API_KEY); --no-tracing выключает явно",
    )
    demo.add_argument(
        "--grounding",
        action="store_true",
        help="RAG-фактчек цифр через LangChain (нужен pip install '.[langchain]')",
    )
    demo.set_defaults(func=cmd_demo)

    run = subparsers.add_parser("run", help="запуск с реальными моделями")
    run.add_argument("--config", required=True, help="путь к конфигу")
    run.add_argument("--out", default="out", help="каталог результатов")
    run.add_argument("--publish", action="store_true", help="опубликовать в Telegram")
    run.add_argument(
        "--engine",
        choices=["pipeline", "langgraph"],
        default="pipeline",
        help="движок исполнения: встроенный пайплайн или граф LangGraph "
        "(нужен pip install 'langgraph>=0.6,<2')",
    )
    run.add_argument(
        "--revision-rounds",
        type=int,
        default=None,
        help="максимум раундов редактуры после критика (по умолчанию из конфига, "
        "1 = без повторной критики; работает в --engine langgraph)",
    )
    run.add_argument(
        "--tracing",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="LangSmith-трейсинг (нужен LANGSMITH_API_KEY); --no-tracing выключает явно",
    )
    run.add_argument(
        "--grounding",
        action="store_true",
        help="RAG-фактчек цифр через LangChain (нужен pip install '.[langchain]')",
    )
    run.set_defaults(func=cmd_run)

    brain = subparsers.add_parser(
        "brain", help="сгенерировать пост из готовых статей (мост из content-factory)"
    )
    brain.add_argument("--config", required=True, help="JSON-конфиг провайдеров/ролей")
    brain.add_argument(
        "--articles", default="-", help="JSON со статьями или - (stdin)"
    )
    brain.add_argument("--channel", default="brain", help="канал/тема для промпта")
    brain.add_argument("--language", default="ru", choices=["ru", "en", "es"])
    brain.add_argument("--out", default="out", help="каталог drafts/runs")
    brain.add_argument(
        "--engine", choices=["pipeline", "langgraph"], default="langgraph"
    )
    brain.add_argument("--revision-rounds", type=int, default=None)
    brain.add_argument(
        "--grounding", action=argparse.BooleanOptionalAction, default=None,
        help="RAG-фактчек (нужен LangChain)",
    )
    brain.set_defaults(func=cmd_brain)

    server = subparsers.add_parser("mcp-server", help="запустить MCP-сервер (stdio)")
    server.add_argument("--root", default="out", help="каталог drafts/outbox")
    server.add_argument("--allow-publish", action="store_true", help="разрешить реальную публикацию")
    server.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    server.set_defaults(func=cmd_mcp_server)

    tools = subparsers.add_parser("tools", help="показать инструменты MCP-сервера")
    tools.add_argument("--config", default=str(_demo_config_path()))
    tools.add_argument("--out", default="out")
    tools.set_defaults(func=cmd_tools)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ConfigError, MCPError, AllProvidersFailed, BudgetExceeded, RuntimeError) as exc:
        print("Ошибка: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
