"""Тесты экстрактивной суммаризации и ключевых терминов (unittest, без сети).

Проверяют обязательный офлайн-режим NLP-ядра: TextRank, дедупликация,
аккуратные обрезки, пустой ввод и TF-IDF по русским текстам.
"""
import unittest

from content_factory.nlp.extractive import (
    dedupe_sentences,
    rank_sentences,
    split_sentences,
    summarize_sentences,
    summarize_texts,
)
from content_factory.nlp.keywords import extract_key_terms
from content_factory.utils import STOPWORDS_RU

TEXT_MEDICINE_1 = (
    "Российские учёные представили новую модель нейросети для анализа медицинских снимков. "
    "Разработка показала точность 94% на тестовой выборке. "
    "Исследователи отмечают, что модель обучена на открытых данных. "
    "В дальнейшем её планируют использовать в клиниках."
)
TEXT_MEDICINE_2 = (
    "Нейросеть для диагностики заболеваний представили в России. "
    "По словам разработчиков, точность модели достигает 94%. "
    "Аналогичные решения уже применяются в нескольких клиниках. "
    "Эксперты положительно оценили рост качества медицинских ИИ-сервисов."
)
TEXT_MEDICINE_3 = (
    "Учёные создали ИИ-модель для анализа снимков. "
    "Точность разработки составила 94%, сообщает пресс-служба. "
    "Модель обучали на открытом наборе данных. "
    "В клиниках новую нейросеть начнут тестировать в следующем году."
)
TEXTS = [TEXT_MEDICINE_1, TEXT_MEDICINE_2, TEXT_MEDICINE_3]


def _all_sentences():
    sentences = []
    for text in TEXTS:
        sentences.extend(split_sentences(text))
    return sentences


class SplitSentencesTest(unittest.TestCase):
    def test_splits_russian_text_into_sentences(self):
        sentences = split_sentences(TEXT_MEDICINE_1)
        self.assertEqual(len(sentences), 4)
        for sentence in sentences:
            self.assertGreaterEqual(len(sentence), 12)
            self.assertTrue(sentence.endswith("."))

    def test_empty_and_whitespace_input(self):
        self.assertEqual(split_sentences(""), [])
        self.assertEqual(split_sentences("   \n\t  "), [])

    def test_text_without_punctuation_returns_single_phrase(self):
        sentences = split_sentences("Заголовок новости без точки")
        self.assertEqual(len(sentences), 1)

    def test_bullet_markers_are_removed(self):
        sentences = split_sentences("• Первое важное предложение текста.\n— Второе важное предложение текста.")
        self.assertEqual(len(sentences), 2)
        self.assertFalse(sentences[0].startswith("•"))
        self.assertFalse(sentences[1].startswith("—"))


class SummarizeTest(unittest.TestCase):
    def test_summarize_texts_returns_limited_sentences(self):
        summary = summarize_texts(TEXTS, max_sentences=4)
        self.assertTrue(summary)
        self.assertEqual(summary, summary.strip())
        self.assertNotIn("  ", summary)
        sentences = split_sentences(summary)
        self.assertGreaterEqual(len(sentences), 1)
        self.assertLessEqual(len(sentences), 4)

    def test_summary_keeps_source_order(self):
        all_sentences = _all_sentences()
        summary = summarize_texts(TEXTS, max_sentences=5)
        indexes = []
        for sentence in split_sentences(summary):
            self.assertIn(sentence, all_sentences)
            indexes.append(all_sentences.index(sentence))
        self.assertEqual(indexes, sorted(indexes))

    def test_summary_does_not_repeat_same_fact(self):
        summary = summarize_texts([TEXT_MEDICINE_1, TEXT_MEDICINE_1], max_sentences=5)
        sentences = split_sentences(summary)
        # Один и тот же текст не должен давать два одинаковых предложения.
        self.assertEqual(len(sentences), len(set(sentences)))

    def test_summarize_sentences_joins_and_ends_with_punctuation(self):
        summary = summarize_sentences(_all_sentences(), max_sentences=3)
        sentences = split_sentences(summary)
        self.assertLessEqual(len(sentences), 3)
        for sentence in sentences:
            self.assertIn(sentence[-1], ".!?…»")

    def test_empty_inputs_return_empty_string(self):
        self.assertEqual(summarize_texts([], max_sentences=5), "")
        self.assertEqual(summarize_texts(["", "   "], max_sentences=5), "")
        self.assertEqual(summarize_sentences([], max_sentences=3), "")

    def test_long_sentences_are_cut_accurately(self):
        long_text = ("Слово " * 120) + "конец."
        summary = summarize_texts([long_text], max_sentences=1)
        self.assertLessEqual(len(summary), 430)
        self.assertTrue(summary.endswith("…") or summary.endswith("."))

    def test_dedupe_near_duplicates(self):
        sentences = [
            "Курс доллара вырос на 2 рубля.",
            "Курс доллара вырос на 2 рубля!",
            "Центробанк повысил ключевую ставку.",
        ]
        deduped = dedupe_sentences(sentences)
        self.assertEqual(len(deduped), 2)
        self.assertIn("Центробанк повысил ключевую ставку.", deduped)


class RankSentencesTest(unittest.TestCase):
    def test_rank_returns_at_most_top_n_in_source_order(self):
        sentences = _all_sentences()
        ranked = rank_sentences(sentences, top_n=3)
        self.assertLessEqual(len(ranked), 3)
        indexes = [sentences.index(sentence) for sentence in ranked]
        self.assertEqual(indexes, sorted(indexes))
        self.assertEqual(ranked, [sentences[index] for index in indexes])

    def test_rank_empty_and_zero(self):
        self.assertEqual(rank_sentences([], top_n=3), [])
        self.assertEqual(rank_sentences(_all_sentences(), top_n=0), [])


class KeyTermsTest(unittest.TestCase):
    def test_extracts_terms_from_russian_news(self):
        terms = extract_key_terms(TEXTS, top_n=8)
        self.assertEqual(len(terms), 8)
        self.assertEqual(len({term.lower() for term in terms}), len(terms))
        self.assertTrue(any("модел" in term.lower() for term in terms))
        self.assertTrue(any("нейросет" in term.lower() for term in terms))
        self.assertTrue(any("клиник" in term.lower() for term in terms))
        for term in terms:
            self.assertNotIn(term.lower().replace("ё", "е"), STOPWORDS_RU)
            self.assertGreaterEqual(len(term), 2)

    def test_terms_are_deterministic(self):
        first = extract_key_terms(TEXTS, top_n=6)
        second = extract_key_terms(TEXTS, top_n=6)
        self.assertEqual(first, second)

    def test_keeps_short_acronyms_and_brands(self):
        texts = [
            "ИИ и нейросети развиваются. OpenAI выпустила модель GPT-5.",
            "Модель GPT-5 от OpenAI стала доступна разработчикам.",
        ]
        terms = extract_key_terms(texts, top_n=8)
        self.assertIn("OpenAI", terms)
        self.assertIn("GPT-5", terms)

    def test_empty_input_and_zero_limit(self):
        self.assertEqual(extract_key_terms([], top_n=8), [])
        self.assertEqual(extract_key_terms(["", "   "], top_n=8), [])
        self.assertEqual(extract_key_terms(TEXTS, top_n=0), [])

    def test_single_document_still_returns_terms(self):
        terms = extract_key_terms([TEXT_MEDICINE_1], top_n=5)
        self.assertEqual(len(terms), 5)
        self.assertTrue(all(term.strip() for term in terms))


if __name__ == "__main__":
    unittest.main()
