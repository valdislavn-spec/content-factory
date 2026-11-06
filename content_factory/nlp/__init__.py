"""Пакет NLP-ядра контент-завода.

Публичный API для конвейера: суммаризация и ключевые термины, тональность,
анализ кластера, генерация постов и LLM-клиенты. Все функции работают без
сети и без обязательных LLM: по умолчанию используются TextRank и шаблоны.
"""
from __future__ import annotations

from .analyzer import analyze_cluster
from .extractive import (
    dedupe_sentences,
    rank_sentences,
    split_sentences,
    summarize_sentences,
    summarize_texts,
)
from .generator import generate_digest, generate_post
from .keywords import extract_key_terms
from .llm import (
    DifyLLM,
    ExtractiveLLM,
    GigaChatLLM,
    LLMClient,
    OllamaLLM,
    OpenAICompatibleLLM,
    YandexGPTLLM,
    clean_llm_output,
    get_llm,
)
from .sentiment import detect_sentiment

__all__ = [
    "LLMClient",
    "DifyLLM",
    "ExtractiveLLM",
    "OllamaLLM",
    "OpenAICompatibleLLM",
    "GigaChatLLM",
    "YandexGPTLLM",
    "get_llm",
    "clean_llm_output",
    "analyze_cluster",
    "generate_post",
    "generate_digest",
    "extract_key_terms",
    "detect_sentiment",
    "summarize_texts",
    "summarize_sentences",
    "rank_sentences",
    "dedupe_sentences",
    "split_sentences",
]
