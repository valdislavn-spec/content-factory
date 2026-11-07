"""Генератор готовых постов через Dify Workflow-приложение.

Приложение Dify (например, «Six-Channel Editorial News Draft Factory») само
ищет новости, делает SEO-оптимизацию и возвращает **готовый пост**. Заводу
остаётся подставить канал и тему сюжета, проверить результат и опубликовать.

Если приложение недоступно, вернуло пустой ответ или дневной лимит запусков
исчерпан, генератор возвращает ``None`` — конвейер откатывается на встроенную
генерацию (LLM/extractive), поэтому постинг не останавливается.
"""
from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..models import ChannelConfig, GeneratedPost, StoryCluster
from ..nlp.budget import DailyBudget
from ..nlp.lang import language_code
from ..utils import env, normalize_space
from .dify_workflow import DifyWorkflowClient, DifyWorkflowError
from .shortlink import shorten_url

logger = logging.getLogger(__name__)

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_LATIN_RE = re.compile(r"[A-Za-z]{2,}")
_MARKDOWN_FENCE_RE = re.compile(r"^```[A-Za-z0-9_-]*\s*|\s*```$")


def _plain_to_telegram_html(text: str) -> str:
    """Экранирует текст приложения, чтобы он безопасно ушёл с parse_mode=HTML."""
    cleaned = _MARKDOWN_FENCE_RE.sub("", str(text or "").strip())
    cleaned = html.escape(cleaned, quote=False)
    return cleaned.strip()


_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]"
)


def _ensure_emojis(text: str, minimum: int = 3) -> str:
    """Гарантирует минимум emoji в посте (требование к оформлению)."""
    value = str(text or "")
    if len(_EMOJI_RE.findall(value)) >= minimum:
        return value
    lines = value.splitlines() or [value]
    for emoji in ("📰", "🔎", "✨"):
        if len(_EMOJI_RE.findall("\n".join(lines))) >= minimum:
            break
        lines[0] = emoji + " " + lines[0].lstrip()
    return "\n".join(lines)


def _http_url(value: str) -> str:
    url = str(value or "").strip()
    return url if url.startswith(("http://", "https://")) else ""


def _post_id(channel: ChannelConfig, cluster: StoryCluster, now: datetime) -> str:
    """Детерминированный id: один сюжет + канал + час не дублируется."""
    seed = "{}:{}:{}".format(channel.id, cluster.id, now.strftime("%Y%m%d%H"))
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _basic_quality(plain: str, channel: ChannelConfig, settings: Any) -> list:
    """Минимальные проверки готового поста перед публикацией."""
    issues: list = []
    min_chars = 220
    banned: list = []
    if settings is not None:
        try:
            pipeline = settings.pipeline or {}
            min_chars = int(pipeline.get("min_post_chars", min_chars) or min_chars)
            banned = list(pipeline.get("banned_words") or [])
        except Exception:  # pragma: no cover - нестандартные Settings
            pass
    if len(plain) < min_chars:
        issues.append("текст короче минимума ({} < {})".format(len(plain), min_chars))
    lowered = plain.lower()
    for word in banned:
        needle = str(word).strip().lower()
        if needle and needle in lowered:
            issues.append("запрещённое слово: {}".format(word))
    return issues


class DifyPostGenerator:
    """Готовый пост из Dify Workflow по паре «канал + тема сюжета»."""

    def __init__(
        self,
        client: DifyWorkflowClient,
        config: Optional[Dict[str, Any]] = None,
        budget: Optional[DailyBudget] = None,
        purpose: str = "posts",
        settings: Any = None,
    ) -> None:
        cfg = dict(config or {})
        self.client = client
        self.settings = settings
        self.purpose = purpose
        self.output_key = str(cfg.get("output_key") or "").strip()
        raw_outputs = cfg.get("outputs") or {}
        self.outputs_map = {
            "text": str(
                (raw_outputs.get("text") if isinstance(raw_outputs, dict) else "")
                or self.output_key
                or "result"
            ),
            "image_url": str(
                (raw_outputs.get("image_url") if isinstance(raw_outputs, dict) else "")
                or "image_url"
            ),
            "source_url": str(
                (raw_outputs.get("source_url") if isinstance(raw_outputs, dict) else "")
                or "source_url"
            ),
        }
        raw_inputs = cfg.get("inputs") or {"channel": "{channel}", "topic": "{topic}"}
        self.inputs_template = dict(raw_inputs) if isinstance(raw_inputs, dict) else {}
        self.budget = budget
        self.user = str(cfg.get("user") or "content-factory")

    def _inputs(self, channel: ChannelConfig, cluster: StoryCluster) -> Dict[str, str]:
        channel_value = (
            str(getattr(channel, "telegram_chat_id", "") or "").strip()
            or str(channel.title or channel.id)
        )
        topic_value = normalize_space(
            "{} — {}".format(cluster.title, "; ".join((cluster.key_terms or [])[:4])).strip(" —")
        )
        values = {"channel": channel_value, "topic": topic_value, "cluster": cluster.title}
        rendered: Dict[str, str] = {}
        for name, template in self.inputs_template.items():
            try:
                rendered[str(name)] = str(template).format(**values)
            except (KeyError, IndexError, ValueError):
                rendered[str(name)] = str(template)
        return rendered

    def generate(
        self,
        channel: ChannelConfig,
        cluster: StoryCluster,
        now: Optional[datetime] = None,
    ) -> Optional[GeneratedPost]:
        """Возвращает готовый пост или ``None`` (тогда работает встроенный путь)."""
        if self.budget is not None and not self.budget.try_consume(1):
            logger.warning(
                "Dify-приложение %s: %s — откат на встроенную генерацию",
                self.purpose,
                self.budget.describe(),
            )
            return None
        now = now or datetime.now(timezone.utc)
        try:
            data = self.client.run(self._inputs(channel, cluster), user=self.user)
        except DifyWorkflowError as exc:
            logger.warning("Dify-приложение %s недоступно: %s", self.purpose, exc)
            return None
        except Exception as exc:  # pragma: no cover - защита от нестандартных ошибок
            logger.warning("Dify-приложение %s: неожиданная ошибка: %s", self.purpose, exc)
            return None

        outputs = self.client.outputs(data)
        if not outputs:
            logger.warning(
                "Dify-приложение %s вернуло пустые outputs (нет Output-узла) — откат",
                self.purpose,
            )
            return None
        text = outputs.get(self.outputs_map["text"])
        if not isinstance(text, str) or not text.strip():
            text = ""
            for candidate in outputs.values():
                if isinstance(candidate, str) and candidate.strip():
                    text = candidate
                    break
        if not str(text or "").strip():
            logger.warning("Dify-приложение %s вернуло пустой текст поста", self.purpose)
            return None
        image_url = _http_url(outputs.get(self.outputs_map["image_url"]))
        source_url = _http_url(outputs.get(self.outputs_map["source_url"]))
        raw_text = str(text).strip()
        if source_url:
            short_source = shorten_url(source_url)
            if short_source and short_source not in raw_text:
                raw_text = raw_text.rstrip() + "\n\n📰 Source: " + short_source
        raw_text = _ensure_emojis(raw_text)
        post_html = _plain_to_telegram_html(raw_text)
        plain = normalize_space(html.unescape(re.sub(r"<[^>]+>", "", post_html)))
        if not plain:
            logger.warning("Dify-приложение %s вернуло пустой пост", self.purpose)
            return None
        language = language_code(channel.language)
        if language == "en":
            if _CYRILLIC_RE.search(plain):
                logger.warning("Dify-приложение %s: в англоязычном посте кириллица — откат", self.purpose)
                return None
            if not _LATIN_RE.search(plain):
                logger.warning("Dify-приложение %s: пост не похож на английский — откат", self.purpose)
                return None
        if len(plain) > int(getattr(channel, "max_post_chars", 3500)):
            logger.warning(
                "Dify-приложение %s: пост длиннее лимита канала (%d > %d) — откат",
                self.purpose,
                len(plain),
                int(getattr(channel, "max_post_chars", 3500)),
            )
            return None

        hashtags = list(getattr(channel, "hashtags", []) or [])
        if hashtags and "#" not in plain:
            post_html = post_html.rstrip() + "\n\n" + " ".join(hashtags)
        sources = [
            {
                "title": str(getattr(article, "title", "") or ""),
                "url": str(getattr(article, "url", "") or ""),
                "source": str(getattr(article, "source_name", "") or ""),
            }
            for article in (getattr(cluster, "articles", []) or [])[:5]
        ]
        post = GeneratedPost(
            id=_post_id(channel, cluster, now),
            channel_id=channel.id,
            cluster_id=cluster.id,
            format="story",
            text=post_html,
            hashtags=hashtags,
            sources=sources,
            created_at=now,
            score=float(getattr(cluster, "relevance", 0.0) or 0.0),
            meta={
                "generator": "dify_app",
                "app": self.purpose,
                "tone": getattr(channel, "tone", ""),
                "image_url": image_url,
                "source_url": source_url,
                "short_source": shorten_url(source_url) if source_url else "",
            },
        )
        issues = _basic_quality(plain, channel, self.settings)
        if issues:
            logger.warning("Dify-приложение %s: пост отклонён: %s", self.purpose, "; ".join(issues))
            return None
        return post


def build_post_generator(settings: Any) -> Optional[DifyPostGenerator]:
    """Собирает генератор из настроек; ``None``, если он отключён или нет ключа."""
    try:
        pipeline = dict(settings.raw.get("pipeline") or {})
    except Exception:
        return None
    generator_name = str(pipeline.get("post_generator") or "internal").strip().lower()
    if generator_name == "brain":
        from .brain_posts import build_brain_generator

        return build_brain_generator(settings)
    if generator_name != "dify_app":
        return None
    purpose = str(pipeline.get("dify_post_app") or "posts").strip() or "posts"
    apps = ((settings.raw.get("integrations") or {}).get("dify_apps") or {})
    cfg = dict(apps.get(purpose) or {})
    key_env = str(cfg.get("api_key_env") or "DIFY_POSTS_API_KEY")
    api_key = env(key_env, "") or ""
    if not api_key:
        logger.warning(
            "pipeline.post_generator=dify_app, но %s не задан — генерация внутренняя", key_env
        )
        return None
    client = DifyWorkflowClient(
        api_key, timeout=float(cfg.get("timeout", 180))
    )
    limit = int(cfg.get("daily_limit") or 0)
    budget = None
    if limit > 0:
        try:
            budget = DailyBudget(settings.data_dir / "dify_{}_usage.json".format(purpose), limit)
        except Exception:  # pragma: no cover - нестандартные Settings
            budget = None
    return DifyPostGenerator(client, cfg, budget=budget, purpose=purpose, settings=settings)
