import logging
import time
from datetime import datetime, timezone
from typing import Protocol

from current_affairs_bot.config import Settings
from current_affairs_bot.document_client import DocumentClient
from current_affairs_bot.llm_client import LLMClient
from current_affairs_bot.models import Article
from current_affairs_bot.news_client import NewsClient
from current_affairs_bot.state_store import PendingRevealStore, StateStore
from current_affairs_bot.telegram_client import TelegramClient


LOGGER = logging.getLogger(__name__)


class ContentClient(Protocol):
    def fetch_latest(self, posted_urls: set[str] | None = None) -> list[Article]:
        ...


class CurrentAffairsService:
    def __init__(
        self,
        settings: Settings,
        content_client: ContentClient,
        llm_client: LLMClient,
        telegram_client: TelegramClient,
        state_store: StateStore,
        pending_reveal_store: PendingRevealStore,
    ) -> None:
        self.settings = settings
        self.content_client = content_client
        self.llm_client = llm_client
        self.telegram_client = telegram_client
        self.state_store = state_store
        self.pending_reveal_store = pending_reveal_store

    def run_cycle(self, dry_run: bool = False) -> int:
        reveal_count = self._process_due_group_reveals(dry_run=dry_run)
        posted_state = self.state_store.posted_state()
        posted_urls = set(posted_state.keys())
        articles = self.content_client.fetch_latest(posted_urls=posted_urls)
        fresh_articles = [article for article in articles if article.url not in posted_urls]
        selected_articles = self._select_articles_for_cycle(articles, fresh_articles, posted_state)
        if not selected_articles:
            if self.settings.content_mode == "books" and not articles:
                LOGGER.warning(
                    "Books mode did not find any usable excerpts, so nothing was posted. Add at least one .txt, .md, .docx, .json, or text-based .pdf file to %s.",
                    self.settings.books_source_dir,
                )
                return 0
            LOGGER.info(
                "No new articles found in this cycle. fetched=%s fresh=%s already_posted=%s pending_reveals_processed=%s",
                len(articles),
                len(fresh_articles),
                len(articles) - len(fresh_articles),
                reveal_count,
            )
            return 0

        LOGGER.info(
            "Preparing %s fresh article(s) from %s fetched candidates.",
            len(selected_articles),
            len(articles),
        )
        posted_count = 0
        failure_count = 0
        for article in selected_articles:
            try:
                generated_post = self.llm_client.generate_post(article)
                if dry_run:
                    LOGGER.info("Dry run preview for article: %s", article.title)
                    LOGGER.info("Summary: %s", generated_post.summary)
                else:
                    pending_reveals = self.telegram_client.broadcast(article, generated_post)
                    self.pending_reveal_store.add_many(pending_reveals)
                    self.state_store.mark_posted(article)
                    LOGGER.info("Posted article to Telegram: %s", article.title)
                posted_count += 1
            except Exception:
                failure_count += 1
                LOGGER.exception("Failed to process article: %s", article.title)
        if posted_count == 0 and failure_count > 0:
            raise RuntimeError("The bot found fresh articles but failed to process all of them.")
        return posted_count

    def _process_due_group_reveals(self, dry_run: bool = False) -> int:
        due_reveals = self.pending_reveal_store.due_reveals()
        if not due_reveals:
            return 0

        LOGGER.info("Processing %s due group answer reveal(s).", len(due_reveals))
        sent_ids: set[str] = set()
        processed = 0
        for reveal in due_reveals:
            try:
                if dry_run:
                    LOGGER.info("Dry run answer reveal for topic: %s", reveal.article_title)
                else:
                    self.telegram_client.send_group_answer_reveal(reveal)
                    sent_ids.add(reveal.reveal_id)
                processed += 1
            except Exception:
                LOGGER.exception("Failed to send pending group answer reveal: %s", reveal.reveal_id)

        if not dry_run and sent_ids:
            self.pending_reveal_store.remove_ids(sent_ids)
        return processed

    def _select_articles_for_cycle(
        self,
        articles: list[Article],
        fresh_articles: list[Article],
        posted_state: dict[str, dict[str, str]],
    ) -> list[Article]:
        if fresh_articles:
            return list(reversed(fresh_articles[: self.settings.max_articles_per_cycle]))

        if self.settings.content_mode != "books" or not articles:
            return []

        def posted_at_key(article: Article) -> datetime:
            state = posted_state.get(article.url, {})
            raw_value = str(state.get("posted_at") or "").strip()
            if not raw_value:
                return datetime.min.replace(tzinfo=timezone.utc)
            try:
                return datetime.fromisoformat(raw_value)
            except ValueError:
                return datetime.min.replace(tzinfo=timezone.utc)

        recycled_articles = sorted(articles, key=posted_at_key)
        selected = recycled_articles[: self.settings.max_articles_per_cycle]
        LOGGER.info(
            "No fresh book excerpts remained, so reusing %s previously posted excerpt(s) for continued scheduling.",
            len(selected),
        )
        return selected

    def run_forever(self) -> None:
        LOGGER.info("Starting scheduler with %s-minute interval.", self.settings.poll_interval_minutes)
        while True:
            cycle_start = time.monotonic()
            self.run_cycle()
            elapsed = time.monotonic() - cycle_start
            sleep_seconds = max(15, self.settings.poll_interval_minutes * 60 - int(elapsed))
            LOGGER.info("Sleeping for %s seconds before next cycle.", sleep_seconds)
            time.sleep(sleep_seconds)


def build_service(settings: Settings) -> CurrentAffairsService:
    content_client: ContentClient
    if settings.content_mode == "books":
        content_client = DocumentClient(settings)
    else:
        content_client = NewsClient(settings)
    return CurrentAffairsService(
        settings=settings,
        content_client=content_client,
        llm_client=LLMClient(settings),
        telegram_client=TelegramClient(settings),
        state_store=StateStore(settings.state_file),
        pending_reveal_store=PendingRevealStore(settings.group_reveal_state_file),
    )

