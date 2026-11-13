"""Optional LLM verifier for ambiguous news-cluster pairs.

Lexical/complete-linkage clustering is cheap and deterministic, but it misses
paraphrases with no shared words and sometimes over-merges two events that share
a company name.  This verifier asks a local Ollama model a single yes/no question
for a small number of ambiguous pairs, and the answer only adjusts those pairs.

Design constraints:
* off by default — CI and free deployments must not need an LLM;
* one short prompt per pair, hard cap on calls (``cluster_verifier_max_calls``);
* any network/parse failure returns ``None`` and the lexical similarity is kept;
* the model is local (Ollama) by default; no paid API is required.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from ..models import Article
from ..utils import env, normalize_space
from .llm import OllamaLLM

logger = logging.getLogger(__name__)

_PROMPT = """Ты редактор новостной ленты. Определи, описывают ли два материала
ОДНО И ТО ЖЕ СОБЫТИЕ (один факт, одно действие, один релиз), а не просто одну тему.
Общие слова компании/страны/слова «новый», «представил» сами по себе не делают
события одним. Разные продукты, разные действия и разные числа — разные события.

Материал A:
{first}

Материал B:
{second}

Ответь строго JSON без пояснений:
{{"same_event": true|false, "confidence": 0.0-1.0}}
"""

_JSON_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _excerpt(article: Article, limit: int = 700) -> str:
    title = normalize_space(article.title or "")
    body = article.summary or (article.text or "")
    body = normalize_space(body)[:limit]
    return (title + ("\n" + body if body else "")).strip()


def _parse_verdict(raw: str) -> Optional[bool]:
    """Parse the model answer; tolerate markdown fences and extra prose."""
    if not raw:
        return None
    match = _JSON_RE.search(raw)
    if match:
        try:
            data = json.loads(match.group(0))
        except (TypeError, ValueError):
            data = None
        if isinstance(data, dict) and isinstance(data.get("same_event"), bool):
            return bool(data["same_event"])
    lowered = raw.lower()
    if re.search(r"\b(true|да|yes|одно событие|same event)\b", lowered):
        return True
    if re.search(r"\b(false|нет|no|разные события|different)\b", lowered):
        return False
    return None


class ClusterVerifier:
    """Thin cached wrapper around an LLM client; never raises to the pipeline."""

    def __init__(self, client: Any, max_calls: int = 10) -> None:
        self.client = client
        self.max_calls = max(0, int(max_calls))
        self.calls = 0
        self._cache: Dict[tuple[str, str], Optional[bool]] = {}

    def same_event(self, first: Article, second: Article) -> Optional[bool]:
        key = (first.id, second.id)
        if key in self._cache:
            return self._cache[key]
        if self.calls >= self.max_calls or not getattr(self.client, "available", False):
            return None
        prompt = _PROMPT.format(first=_excerpt(first), second=_excerpt(second))
        try:
            raw = self.client.generate(prompt, temperature=0.0, max_tokens=80)
        except Exception as exc:  # pragma: no cover - client already catches most
            logger.warning("Cluster verifier error: %s", exc)
            raw = ""
        verdict = _parse_verdict(raw)
        if raw:
            self.calls += 1
        self._cache[key] = verdict
        return verdict


def make_cluster_verifier(settings: Any) -> Optional[ClusterVerifier]:
    """Build the optional local Ollama verifier from settings/env.

    ``CLUSTER_VERIFIER=ollama`` (or ``auto``) enables it; ``off``/empty disables.
    """
    try:
        raw_mode = env("CLUSTER_VERIFIER", "") or str(
            settings.pipeline.get("cluster_verifier", "off")
        )
    except Exception:
        raw_mode = "off"
    mode = str(raw_mode or "off").strip().lower()
    if mode in ("", "off", "none", "0", "false", "no"):
        return None
    if mode not in ("auto", "ollama", "llm"):
        logger.warning("Неизвестный cluster_verifier=%r, выключаю", mode)
        return None
    try:
        llm_config = settings.llm or {}
        providers = dict(llm_config.get("providers") or {})
        config = dict(providers.get("ollama") or {})
        if not config:
            # В settings.yaml секция llm.ollama лежит на верхнем уровне llm,
            # а в других конфигах — внутри llm.providers. Поддерживаем оба.
            config = dict(llm_config.get("ollama") or {})
        model_override = env("CLUSTER_VERIFIER_MODEL", "")
        if model_override:
            config["model"] = model_override
        config.setdefault("timeout", 20)
        timeout_raw = env("CLUSTER_VERIFIER_TIMEOUT", "") or settings.pipeline.get(
            "cluster_verifier_timeout", config["timeout"]
        )
        config["timeout"] = float(timeout_raw or 20)
        client = OllamaLLM(config)
        calls_raw = env("CLUSTER_VERIFIER_MAX_CALLS", "") or settings.pipeline.get(
            "cluster_verifier_max_calls", 10
        )
        max_calls = int(calls_raw or 10)
    except Exception as exc:  # pragma: no cover - bad config must not break clustering
        logger.warning("Не удалось создать cluster_verifier: %s", exc)
        return None
    if not client.available:
        return None
    return ClusterVerifier(client, max_calls=max_calls)
