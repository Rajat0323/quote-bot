import unittest
from types import SimpleNamespace

from current_affairs_bot.models import Article, GeneratedPost
from current_affairs_bot.service import CurrentAffairsService


class FakeContentClient:
    def __init__(self, articles: list[Article]) -> None:
        self.articles = articles

    def fetch_latest(self, posted_urls: set[str] | None = None) -> list[Article]:
        return list(self.articles)


class FakeLLMClient:
    def __init__(self) -> None:
        self.generated_for: list[str] = []

    def generate_post(self, article: Article) -> GeneratedPost:
        self.generated_for.append(article.url)
        return GeneratedPost(
            title=article.title,
            summary="Generated summary",
            why_it_matters=["Keep going."],
            mcqs=[],
            quote="Generated quote",
            hashtags=["#Motivation"],
        )


class FakeTelegramClient:
    def __init__(self) -> None:
        self.broadcasted_urls: list[str] = []

    def broadcast(self, article: Article, generated_post: GeneratedPost) -> list:
        self.broadcasted_urls.append(article.url)
        return []

    def send_group_answer_reveal(self, reveal: object) -> None:
        return None


class FakeStateStore:
    def __init__(self, state: dict[str, dict[str, str]]) -> None:
        self.state = dict(state)

    def posted_urls(self) -> set[str]:
        return set(self.state.keys())

    def posted_state(self) -> dict[str, dict[str, str]]:
        return dict(self.state)

    def mark_posted(self, article: Article) -> None:
        self.state[article.url] = {
            "title": article.title,
            "posted_at": "2026-05-04T12:00:00+00:00",
        }


class FakePendingRevealStore:
    def due_reveals(self) -> list:
        return []

    def add_many(self, reveals: list) -> None:
        return None

    def remove_ids(self, reveal_ids: set[str]) -> None:
        return None


class ServiceBooksModeTests(unittest.TestCase):
    def test_books_mode_reuses_oldest_excerpt_when_no_fresh_items_remain(self) -> None:
        articles = [
            Article(
                title="Book One | Insight 1",
                description="Excerpt one",
                url="book://book-one.txt#chunk-1",
                source="Book One",
                published_at="2026-05-04T10:00:00+00:00",
                content="Excerpt one",
            ),
            Article(
                title="Book One | Insight 2",
                description="Excerpt two",
                url="book://book-one.txt#chunk-2",
                source="Book One",
                published_at="2026-05-04T10:00:00+00:00",
                content="Excerpt two",
            ),
        ]
        state = {
            "book://book-one.txt#chunk-1": {"title": "Book One | Insight 1", "posted_at": "2026-05-04T06:00:00+00:00"},
            "book://book-one.txt#chunk-2": {"title": "Book One | Insight 2", "posted_at": "2026-05-04T08:00:00+00:00"},
        }
        llm_client = FakeLLMClient()
        telegram_client = FakeTelegramClient()
        service = CurrentAffairsService(
            settings=SimpleNamespace(content_mode="books", max_articles_per_cycle=1, poll_interval_minutes=120),
            content_client=FakeContentClient(articles),
            llm_client=llm_client,
            telegram_client=telegram_client,
            state_store=FakeStateStore(state),
            pending_reveal_store=FakePendingRevealStore(),
        )

        processed = service.run_cycle(dry_run=False)

        self.assertEqual(processed, 1)
        self.assertEqual(llm_client.generated_for, ["book://book-one.txt#chunk-1"])
        self.assertEqual(telegram_client.broadcasted_urls, ["book://book-one.txt#chunk-1"])


if __name__ == "__main__":
    unittest.main()
