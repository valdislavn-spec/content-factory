"""Тесты дедупликации: кластеризация сюжетов и защита от повторных заголовков."""
import unittest
from datetime import datetime, timedelta, timezone

from content_factory.dedup import cluster_articles, is_duplicate_title, title_similarity
from content_factory.models import Article
from content_factory.utils import normalize_url, stable_id

NOW = datetime.now(timezone.utc)


def _article(
    title: str,
    source_id: str = "source",
    index: int = 1,
    weight: float = 1.0,
    minutes_ago: float = 0,
    url: str = "",
    source_name: str = "",
) -> Article:
    url = url or f"https://example.com/{source_id}/{index}"
    return Article(
        id=stable_id(normalize_url(url)),
        title=title,
        url=url,
        source_id=source_id,
        source_name=source_name or source_id,
        published_at=NOW - timedelta(minutes=minutes_ago),
        summary="",
        weighted_source_score=weight,
        meta={"url_hash": stable_id(normalize_url(url))},
    )


class ClusterArticlesTest(unittest.TestCase):
    def _same_event_articles(self):
        return [
            _article("OpenAI представила модель GPT-5", "habr", 1, weight=1.2, minutes_ago=60, source_name="Habr"),
            _article("OpenAI выпустила модель GPT-5", "cnews", 2, weight=1.0, minutes_ago=30, source_name="CNews"),
            _article(
                "Компания OpenAI анонсировала модель GPT-5",
                "lenta",
                3,
                weight=0.9,
                minutes_ago=10,
                source_name="Lenta",
            ),
        ]

    def test_same_event_is_one_cluster(self) -> None:
        clusters = cluster_articles(self._same_event_articles())
        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(cluster.coverage, 3)
        self.assertEqual(len(cluster.articles), 3)
        self.assertEqual(cluster.title, "OpenAI представила модель GPT-5", "заголовок — от самого весомого источника")
        self.assertGreater(cluster.score, 0.0)
        self.assertLessEqual(cluster.score, 1.0)
        self.assertTrue(cluster.key_terms, "ключевые слова должны быть заполнены")
        self.assertTrue(all(isinstance(term, str) for term in cluster.key_terms))

    def test_different_events_are_not_merged(self) -> None:
        articles = [
            _article("OpenAI представила модель GPT-5", "habr", 1),
            _article("OpenAI уволила сотрудников", "cnews", 2),
            _article("Курс рубля вырос к доллару", "rbc", 3),
            _article("Погода в Москве завтра будет тёплой", "ria", 4),
        ]
        clusters = cluster_articles(articles)
        self.assertEqual(len(clusters), 4, "разные события не должны склеиваться")
        titles = {cluster.title for cluster in clusters}
        self.assertIn("Курс рубля вырос к доллару", titles)
        self.assertIn("Погода в Москве завтра будет тёплой", titles)

    def test_exact_paraphrase_merges_but_unrelated_does_not(self) -> None:
        articles = [
            _article("ЦБ повысил ключевую ставку до 20%", "tass", 1),
            _article("Банк России поднял ключевую ставку до 20 процентов", "rbc", 2),
            _article("Сбербанк снизил ставки по ипотеке", "vedomosti", 3),
        ]
        clusters = cluster_articles(articles)
        coverage = sorted(cluster.coverage for cluster in clusters)
        self.assertEqual(coverage, [1, 2])

    def test_min_sources_filters_single_source_clusters(self) -> None:
        articles = [
            _article("OpenAI представила модель GPT-5", "habr", 1),
            _article("OpenAI выпустила модель GPT-5", "cnews", 2),
            _article("Курс рубля вырос к доллару", "rbc", 3),
        ]
        clusters = cluster_articles(articles, min_sources=2)
        self.assertEqual(len(clusters), 1)
        self.assertGreaterEqual(clusters[0].coverage, 2)

    def test_high_threshold_keeps_articles_apart(self) -> None:
        clusters = cluster_articles(self._same_event_articles(), threshold=0.99)
        self.assertEqual(len(clusters), 3)

    def test_url_duplicate_merges_across_sources(self) -> None:
        url = "https://example.com/shared/news/1"
        articles = [
            _article("Первая версия заголовка", "habr", 1, url=url),
            _article("Совсем другой заголовок", "cnews", 2, url=url),
        ]
        clusters = cluster_articles(articles)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].coverage, 2)

    def test_empty_input(self) -> None:
        self.assertEqual(cluster_articles([]), [])

    def test_dates_and_sorting(self) -> None:
        clusters = cluster_articles(self._same_event_articles())
        cluster = clusters[0]
        moments = [article.published_at for article in cluster.articles]
        self.assertEqual(moments, sorted(moments, reverse=True), "статьи сортируются от новых к старым")
        self.assertIsNotNone(cluster.first_published)
        self.assertIsNotNone(cluster.last_published)
        self.assertLess(cluster.first_published, cluster.last_published)

    def test_cluster_id_is_deterministic(self) -> None:
        first = {c.id for c in cluster_articles(self._same_event_articles())}
        second = {c.id for c in cluster_articles(self._same_event_articles())}
        self.assertEqual(first, second)

    def test_title_similarity_range(self) -> None:
        self.assertAlmostEqual(title_similarity("Одна и та же новость", "Одна и та же новость"), 1.0)
        self.assertLess(title_similarity("OpenAI представила модель", "Погода в Москве"), 0.34)


class DuplicateTitleTest(unittest.TestCase):
    def test_exact_duplicate_for_articles(self) -> None:
        self.assertTrue(
            is_duplicate_title(
                "OpenAI представила модель GPT-5",
                ["OpenAI представила модель GPT-5"],
                threshold=0.72,
            )
        )

    def test_paraphrase_detected_for_posts(self) -> None:
        self.assertTrue(
            is_duplicate_title(
                "OpenAI представила модель GPT-5",
                ["Компания OpenAI анонсировала модель GPT-5"],
                threshold=0.55,
            )
        )

    def test_paraphrase_is_not_article_duplicate(self) -> None:
        self.assertFalse(
            is_duplicate_title(
                "OpenAI представила модель GPT-5",
                ["Компания OpenAI анонсировала модель GPT-5"],
                threshold=0.72,
            )
        )

    def test_long_post_text_containing_title(self) -> None:
        post = (
            "OpenAI представила модель GPT-5\n\n"
            "Компания показала возможности модели и сроки выхода. "
            "Модель будет доступна всем желающим уже в этом месяце."
        )
        self.assertTrue(is_duplicate_title("OpenAI представила модель GPT-5", [post], threshold=0.55))

    def test_unrelated_title_is_not_duplicate(self) -> None:
        self.assertFalse(
            is_duplicate_title(
                "Курс рубля вырос к доллару",
                ["Погода в Москве завтра будет тёплой", "Сбербанк снизил ставки по ипотеке"],
                threshold=0.55,
            )
        )

    def test_empty_inputs(self) -> None:
        self.assertFalse(is_duplicate_title("", ["Заголовок"], threshold=0.55))
        self.assertFalse(is_duplicate_title("Заголовок", [], threshold=0.55))
        self.assertFalse(is_duplicate_title("Заголовок", [""], threshold=0.55))


if __name__ == "__main__":
    unittest.main()
