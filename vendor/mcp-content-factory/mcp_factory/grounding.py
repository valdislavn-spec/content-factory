"""RAG-фактчек черновика (опция B): LangChain + лёгкий BM25-ретривер.

Идея: разбить статьи-источники на пассажи LangChain-сплиттером и проверять
цифры/годы из черновика по *контексту* пассажа, а не просто по вхождению
строки. Если число есть в источнике, но в другом сюжете (низкое пересечение
слов), это ловится как «цифра подтверждена в другом контексте».

Эмбеддинги и сеть не нужны: BM25 по токенам, быстро и офлайн. LangChain
используется для ``Document``, ``RecursiveCharacterTextSplitter`` и
``BaseRetriever``. Если LangChain не установлен (``pip install ".[langchain]"``),
модуль импортируется, но функции возвращают пустой результат.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .quality import extract_significant_numbers

try:  # LangChain — опциональная зависимость
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    LANGCHAIN_AVAILABLE = True
except ImportError:  # pragma: no cover - зависит от окружения
    Document = None  # type: ignore[assignment]
    BaseRetriever = object  # type: ignore[misc,assignment]
    RecursiveCharacterTextSplitter = None  # type: ignore[assignment]
    LANGCHAIN_AVAILABLE = False


INSTALL_HINT = (
    'RAG-фактчек требует LangChain: pip install "langchain>=0.3,<0.4" '
    '"langchain-text-splitters>=0.3,<0.4" (Python 3.9) или '
    'pip install "mcp-content-factory[langchain]"'
)

_TOKEN_RE = re.compile(r"[0-9a-zA-Zа-яА-ЯёЁ$€₽%.,]+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_STOPWORDS = frozenset(
    {
        "и", "в", "во", "на", "не", "что", "это", "как", "по", "из", "за",
        "для", "от", "к", "с", "о", "об", "а", "но", "же", "ли", "бы",
        "мы", "вы", "он", "она", "они", "его", "её", "их", "все", "уже",
        "при", "или", "так", "был", "была", "было", "были", "будет",
        "the", "and", "for", "with", "that", "this", "from", "are", "was",
        "were", "has", "have", "its", "their", "not", "but", "you", "our",
    }
)


def _tokens(text: str) -> List[str]:
    return [
        token.lower()
        for token in _TOKEN_RE.findall(text or "")
        if len(token) > 1 and token.lower() not in _STOPWORDS
    ]


def _normalize(text: str) -> str:
    """Нормализация для сверки чисел (как в quality.py)."""
    return re.sub(r"[\s\u00a0]+", "", (text or "").lower()).replace(",", ".")


def split_articles(
    articles: Sequence[Any],
    chunk_size: int = 400,
    chunk_overlap: int = 60,
) -> List[Any]:
    """Нарезать статьи на LangChain-документы (пассажи)."""
    if not LANGCHAIN_AVAILABLE or not articles:
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    documents: List[Any] = []
    for article in articles:
        title = str(getattr(article, "title", "") or "").strip()
        summary = str(getattr(article, "summary", "") or "").strip()
        text = ". ".join(part for part in (title, summary) if part).strip()
        if not text:
            continue
        metadata = {
            "index": int(getattr(article, "index", 0) or 0),
            "title": title,
            "url": str(getattr(article, "url", "") or ""),
            "source": str(getattr(article, "source", "") or ""),
        }
        for chunk in splitter.split_text(text):
            if chunk.strip():
                documents.append(Document(page_content=chunk, metadata=metadata))
    return documents


def bm25_search(documents: Sequence[Any], query: str, k: int = 3) -> List[Any]:
    """BM25-поиск по пассажам (без внешних зависимостей)."""
    if not LANGCHAIN_AVAILABLE or not documents or not query:
        return []
    query_tokens = set(_tokens(query))
    if not query_tokens:
        return []
    docs_tokens = [_tokens(doc.page_content) for doc in documents]
    total = len(docs_tokens)
    avg_len = sum(len(tokens) for tokens in docs_tokens) / total or 1.0
    document_freq: Counter = Counter()
    for tokens in docs_tokens:
        document_freq.update(set(tokens))
    scored: List[Tuple[float, Any]] = []
    for doc, tokens in zip(documents, docs_tokens):
        if not tokens:
            continue
        term_freq = Counter(tokens)
        length_norm = 1.0 - 0.75 + 0.75 * len(tokens) / avg_len
        score = 0.0
        for token in query_tokens:
            if token not in term_freq or token not in document_freq:
                continue
            idf = math.log(1.0 + (total - document_freq[token] + 0.5) / (document_freq[token] + 0.5))
            score += idf * term_freq[token] * 2.5 / (term_freq[token] + 1.5 * length_norm)
        if score > 0:
            scored.append((score, doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [doc for _, doc in scored[: max(1, int(k))]]


if LANGCHAIN_AVAILABLE:

    class BM25Retriever(BaseRetriever):  # type: ignore[misc]
        """LangChain-ретривер поверх BM25 (офлайн, без эмбеддингов)."""

        documents: List[Any] = []
        k: int = 3

        def _get_relevant_documents(self, query: str, *, run_manager=None):
            return bm25_search(self.documents, query, self.k)

else:  # pragma: no cover - без LangChain
    BM25Retriever = None  # type: ignore[assignment]


def build_retriever(articles: Sequence[Any], k: int = 3):
    """Собрать BM25-ретривер по статьям (None, если LangChain нет)."""
    if not LANGCHAIN_AVAILABLE:
        return None
    return BM25Retriever(documents=split_articles(articles), k=max(1, int(k)))


def grounding_issues(
    draft: str,
    articles: Sequence[Any],
    max_issues: int = 4,
) -> List[str]:
    """Проверить цифры/годы черновика по контексту пассажей-источников.

    Возвращает список замечаний: число не найдено в источниках или найдено,
    но в другом контексте (сюжете). Пустой список — всё подтверждено.
    """
    if not LANGCHAIN_AVAILABLE or not draft or not articles:
        return []
    documents = split_articles(articles)
    if not documents:
        return []
    corpus = _normalize(" ".join(doc.page_content for doc in documents))
    issues: List[str] = []
    seen: set = set()
    for sentence in _SENTENCE_RE.split(draft):
        numbers = extract_significant_numbers(sentence)
        if not numbers:
            continue
        sentence_tokens = set(_tokens(sentence))
        for number in numbers:
            key = (number, sentence.strip()[:60])
            if key in seen:
                continue
            seen.add(key)
            if number not in corpus:
                issues.append(
                    "RAG: цифра/год «{}» не найдена в источниках".format(number)
                )
                continue
            candidates = [
                doc for doc in documents if number in _normalize(doc.page_content)
            ]
            best_overlap = 0.0
            for doc in candidates:
                doc_tokens = set(_tokens(doc.page_content))
                if not doc_tokens or not sentence_tokens:
                    continue
                overlap = len(sentence_tokens & doc_tokens) / len(sentence_tokens)
                best_overlap = max(best_overlap, overlap)
            if best_overlap < 0.30:
                issues.append(
                    "RAG: «{}» подтверждено источником, но контекст другой".format(number)
                )
            if len(issues) >= max_issues:
                return issues
    return issues


def grounding_report(draft: str, articles: Sequence[Any], k: int = 3) -> Dict[str, Any]:
    """Отчёт для логов/отладки: замечания + топ-пассажи по первой фразе."""
    issues = grounding_issues(draft, articles)
    retriever = build_retriever(articles, k=k)
    passages: List[Dict[str, Any]] = []
    if retriever is not None and draft:
        query = _SENTENCE_RE.split(draft.strip())[0] if draft.strip() else ""
        for doc in retriever.invoke(query):
            passages.append(
                {
                    "text": doc.page_content[:240],
                    "source": doc.metadata.get("source", ""),
                    "title": doc.metadata.get("title", ""),
                }
            )
    return {"issues": issues, "passages": passages}
