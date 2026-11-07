"""Мост «мозга»: готовый пост из mcp-content-factory (LangGraph) для content-factory.

Берёт топ-сюжеты уже собранные контент-заводом и генерирует пост отдельным
пайплайном mcp-content-factory (5 ролей + критик + редактура + RAG-фактчек),
после чего content-factory публикует результат по обычному расписанию.

Конфиг в ``settings.yaml``::

    pipeline:
      post_generator: brain        # или internal / dify_app
    brain:
      enabled: true
      channels: [crypto-news, ai-news]
      path: ../mcp-content-factory
      python: ../mcp-content-factory/.venv/bin/python
      config: ../mcp-content-factory/config/brain.json
      engine: langgraph
      grounding: true
      revision_rounds: 1
      timeout: 300

Если mcp-content-factory/venv/config недоступны (например, в GitHub Actions,
где лежит только content-factory), генератор возвращает None — конвейер
автоматически откатывается на внутреннюю генерацию. Так автопостинг не
останавливается.
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..models import ChannelConfig, GeneratedPost, StoryCluster
from ..utils import env

logger = logging.getLogger(__name__)

_SOURCES_MARK = "**Источники:**"
_TITLE_RE = re.compile(r"^#\s+(.+)$")
_HASHTAG_RE = re.compile(r"^#?")


def _plain_body(markdown: str, fallback_title: str = "") -> tuple:
    """Разобрать markdown mcp-поста на (title, body) без блока источников."""
    title = str(fallback_title or "").strip()
    body_lines = []
    for line in str(markdown or "").splitlines():
        stripped = line.strip()
        # H1 из markdown всегда убираем из тела (заголовок идёт отдельным <b>).
        match = _TITLE_RE.match(stripped)
        if match:
            if not title:
                title = match.group(1).strip()
            continue
        if stripped == _SOURCES_MARK or stripped == "---":
            break
        body_lines.append(line)
    body = "\n".join(body_lines).strip()
    body = re.sub(r"\n{3,}", "\n\n", body)
    return title, body


def _post_id(channel_id: str, cluster_id: str, now: datetime) -> str:
    seed = "brain:{}:{}:{}".format(channel_id, cluster_id, now.strftime("%Y%m%d%H"))
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


class BrainPostGenerator:
    """Готовый пост из mcp-content-factory (LangGraph) для топ-сюжетов."""

    def __init__(self, settings: Any, config: Optional[Dict[str, Any]] = None) -> None:
        cfg = dict(config or {})
        self.settings = settings
        self.enabled = bool(cfg.get("enabled", False))
        self.channels = [str(item).strip() for item in (cfg.get("channels") or []) if str(item).strip()]
        self.engine = str(cfg.get("engine") or "langgraph").strip().lower()
        self.grounding = bool(cfg.get("grounding", True))
        try:
            self.revision_rounds = max(1, int(cfg.get("revision_rounds") or 1))
        except (TypeError, ValueError):
            self.revision_rounds = 1
        try:
            self.timeout = float(cfg.get("timeout") or 300)
        except (TypeError, ValueError):
            self.timeout = 300.0

        try:
            root = Path(getattr(settings, "root"))
        except (TypeError, AttributeError):
            root = Path.cwd()
        self.root = root
        brain_path = str(cfg.get("path") or "../mcp-content-factory")
        python_path = str(cfg.get("python") or "../mcp-content-factory/.venv/bin/python")
        config_path = str(cfg.get("config") or "../mcp-content-factory/config/brain.json")
        self.brain_dir = (root / brain_path).resolve()
        # НЕ resolve(): bin/python в venv — симлинк на системный Python, и
        # resolve() теряет venv (мозг запускался бы без langgraph).
        self.python = Path(os.path.abspath(str(root / python_path)))
        self.config_path = (root / config_path).resolve()
        try:
            data_dir = Path(getattr(settings, "data_dir"))
        except (TypeError, AttributeError):
            data_dir = root / "data"
        self.out_dir = data_dir / "brain-posts"
        self._warned = False

    # -- доступность ------------------------------------------------------
    def available(self) -> bool:
        return (
            self.enabled
            and self.brain_dir.is_dir()
            and self.python.is_file()
            and self.config_path.is_file()
        )

    def reason(self) -> str:
        missing = []
        if not self.brain_dir.is_dir():
            missing.append("нет {}".format(self.brain_dir))
        if not self.python.is_file():
            missing.append("нет {}".format(self.python))
        if not self.config_path.is_file():
            missing.append("нет {}".format(self.config_path))
        return "; ".join(missing) or "выключен"

    # -- генерация --------------------------------------------------------
    def _payload(self, channel: ChannelConfig, cluster: StoryCluster) -> Dict[str, Any]:
        articles = []
        for index, article in enumerate(getattr(cluster, "articles", []) or [], start=1):
            title = str(getattr(article, "title", "") or "").strip()
            if not title:
                continue
            text = str(getattr(article, "text", "") or "")
            summary = str(getattr(article, "summary", "") or "").strip()
            if not summary and text:
                summary = text[:500]
            source = str(
                getattr(article, "source_name", "")
                or getattr(article, "source_id", "")
                or ""
            )
            articles.append(
                {
                    "index": index,
                    "title": title,
                    "url": str(getattr(article, "url", "") or ""),
                    "summary": summary,
                    "source": source,
                    "published": str(getattr(article, "published_at", "") or ""),
                }
            )
        return {
            "articles": articles,
            "channel": channel.id,
            "language": str(getattr(channel, "language", "en") or "en"),
        }

    def _command(self, channel: ChannelConfig) -> list:
        command = [
            str(self.python),
            "-m",
            "mcp_factory",
            "brain",
            "--config",
            str(self.config_path),
            "--articles",
            "-",
            "--channel",
            channel.id,
            "--language",
            str(getattr(channel, "language", "en") or "en"),
            "--out",
            str(self.out_dir),
            "--engine",
            self.engine,
            "--revision-rounds",
            str(self.revision_rounds),
        ]
        command.append("--grounding" if self.grounding else "--no-grounding")
        return command

    def _hashtags(self, channel: ChannelConfig) -> list:
        values = []
        for item in getattr(channel, "hashtags", []) or []:
            value = str(item or "").strip()
            if not value:
                continue
            value = "#" + _HASHTAG_RE.sub("", value)
            if value not in values:
                values.append(value)
        return values

    def _build_post(
        self,
        channel: ChannelConfig,
        cluster: StoryCluster,
        data: Dict[str, Any],
    ) -> Optional[GeneratedPost]:
        markdown = str(data.get("markdown") or "")
        title, body = _plain_body(markdown, str(data.get("title") or cluster.title))
        if not title or not body:
            return None
        hashtags = self._hashtags(channel)
        text = "<b>{}</b>\n\n{}".format(html.escape(title), html.escape(body))
        if hashtags:
            text += "\n\n" + " ".join(hashtags)
        cta = str(getattr(channel, "cta", "") or "").strip()
        if cta and cta not in text:
            text += "\n\n" + html.escape(cta)
        max_chars = int(getattr(channel, "max_post_chars", 0) or 0)
        if max_chars and len(text) > max_chars:
            text = text[: max(0, max_chars - 1)].rstrip() + "…"
        sources = []
        for article in (getattr(cluster, "articles", []) or [])[:5]:
            url = str(getattr(article, "url", "") or "")
            if not url:
                continue
            sources.append(
                {
                    "title": str(getattr(article, "title", "") or ""),
                    "url": url,
                    "source": str(
                        getattr(article, "source_name", "")
                        or getattr(article, "source_id", "")
                        or ""
                    ),
                }
            )
        return GeneratedPost(
            id=_post_id(channel.id, cluster.id, datetime.now(timezone.utc)),
            channel_id=channel.id,
            cluster_id=str(cluster.id),
            format="story",
            text=text,
            hashtags=hashtags,
            sources=sources,
            meta={
                "generator": "brain",
                "engine": data.get("engine"),
                "draft_path": data.get("draft_path"),
                "run_log": data.get("run_log"),
                "language": data.get("language"),
            },
        )

    def generate(
        self,
        channel: ChannelConfig,
        cluster: StoryCluster,
    ) -> Optional[GeneratedPost]:
        """Сгенерировать пост «мозгом»; None → внутренняя генерация."""
        if not self.enabled or channel is None or cluster is None:
            return None
        if self.channels and channel.id not in self.channels:
            return None
        if not self.available():
            if not self._warned:
                logger.warning(
                    "pipeline.post_generator=brain, но мост недоступен (%s) — "
                    "использую внутреннюю генерацию",
                    self.reason(),
                )
                self._warned = True
            return None
        payload = self._payload(channel, cluster)
        if not payload.get("articles"):
            return None
        try:
            result = subprocess.run(
                self._command(channel),
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(self.brain_dir),
                env=os.environ.copy(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("Мозг недоступен: %s", exc)
            return None
        if result.returncode != 0:
            detail = (result.stderr or "").strip().splitlines()[-3:]
            logger.warning(
                "Мозг вернул код %s: %s", result.returncode, " | ".join(detail)[:300]
            )
            return None
        try:
            data = json.loads((result.stdout or "").strip())
        except ValueError:
            logger.warning("Мозг вернул не-JSON: %s", (result.stdout or "")[:200])
            return None
        post = self._build_post(channel, cluster, data)
        if post is None:
            logger.warning("Мозг вернул пустой пост — внутренняя генерация")
        return post


def build_brain_generator(settings: Any) -> Optional[BrainPostGenerator]:
    """Собрать мост из настроек; ``None`` — генератор недоступен/выключен."""
    if env("CONTENT_FACTORY_BRAIN", "").strip().lower() in ("0", "false", "off", "no"):
        return None
    try:
        cfg = dict(settings.raw.get("brain") or {})
        llm_provider = str(
            ((settings.raw.get("llm") or {}).get("provider") or "")
        ).strip().lower()
    except (AttributeError, TypeError):
        return None
    if not bool(cfg.get("enabled", False)):
        return None
    # Демо/офлайн-режим обязан оставаться без сети и вызовов «мозга».
    if llm_provider == "extractive":
        return None
    generator = BrainPostGenerator(settings, cfg)
    if not generator.available():
        logger.warning(
            "brain.enabled=true, но мост недоступен (%s) — внутренняя генерация",
            generator.reason(),
        )
        return None
    return generator
