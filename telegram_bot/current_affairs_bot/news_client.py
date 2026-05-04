import logging
from collections.abc import Callable

import requests

from current_affairs_bot.config import Settings
from current_affairs_bot.models import Article


LOGGER = logging.getLogger(__name__)


class NewsClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()

    def fetch_latest(self, posted_urls: set[str] | None = None) -> list[Article]:
        posted_urls = posted_urls or set()
        articles: list[Article] = []
        seen_urls: set[str] = set()
        fresh_count = 0

        for provider_name, provider_call in self._provider_plan():
            batch = provider_call()
            provider_added = 0
            provider_fresh = 0
            for article in batch:
                if article.url in seen_urls:
                    continue
                seen_urls.add(article.url)
                articles.append(article)
                provider_added += 1
                if article.url not in posted_urls:
                    fresh_count += 1
                    provider_fresh += 1

            LOGGER.info(
                "Provider %s returned %s unique article(s), including %s fresh candidate(s).",
                provider_name,
                provider_added,
                provider_fresh,
            )
            if fresh_count >= self.settings.max_articles_per_cycle:
                break

        LOGGER.info(
            "Aggregated %s unique candidate article(s) across providers with %s fresh candidate(s).",
            len(articles),
            fresh_count,
        )
        return articles

    def _provider_plan(self) -> list[tuple[str, Callable[[], list[Article]]]]:
        plan: list[tuple[str, Callable[[], list[Article]]]] = []

        if self.settings.newsdata_api_key:
            plan.append(
                (
                    "newsdata-india",
                    lambda: self._fetch_newsdata(
                        query=self.settings.newsdata_india_query,
                        country=self.settings.newsdata_india_country,
                    ),
                )
            )
            plan.append(
                (
                    "newsdata-world",
                    lambda: self._fetch_newsdata(
                        query=self.settings.newsdata_world_query,
                        country="",
                    ),
                )
            )

        if self.settings.news_api_key:
            plan.append(("newsapi-world", self._fetch_newsapi))

        return plan

    def _fetch_newsapi(self) -> list[Article]:
        params = {
            "q": self.settings.current_affairs_query,
            "language": self.settings.news_language,
            "sortBy": "publishedAt",
            "pageSize": self.settings.news_page_size,
            "apiKey": self.settings.news_api_key,
        }
        response = self.session.get(
            self.settings.news_api_url,
            params=params,
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") not in {None, "ok"}:
            raise RuntimeError(f"News API returned an unexpected payload: {payload}")
        return self._normalize_newsapi_articles(payload.get("articles", []))

    def _fetch_newsdata(self, query: str, country: str) -> list[Article]:
        params = {
            "apikey": self.settings.newsdata_api_key,
            "q": query,
            "language": self.settings.news_language,
        }
        if country:
            params["country"] = country

        response = self.session.get(
            self.settings.newsdata_api_url,
            params=params,
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        status = str(payload.get("status", "")).lower()
        if status not in {"", "ok", "success"}:
            raise RuntimeError(f"NewsData.io returned an unexpected payload: {payload}")
        return self._normalize_newsdata_articles(payload.get("results", []))

    def _normalize_newsapi_articles(self, items: list[dict]) -> list[Article]:
        articles: list[Article] = []
        seen_urls: set[str] = set()
        for item in items:
            url = (item.get("url") or "").strip()
            title = (item.get("title") or "").strip()
            if not url or not title or url in seen_urls:
                continue

            source_name = (
                item.get("source", {}).get("name", "Unknown Source")
                if isinstance(item.get("source"), dict)
                else "Unknown Source"
            )
            seen_urls.add(url)
            articles.append(
                Article(
                    title=title,
                    description=(item.get("description") or "").strip(),
                    url=url,
                    source=source_name.strip() or "Unknown Source",
                    published_at=(item.get("publishedAt") or "").strip(),
                    content=(item.get("content") or item.get("description") or "").strip(),
                )
            )
        return articles

    def _normalize_newsdata_articles(self, items: list[dict]) -> list[Article]:
        articles: list[Article] = []
        seen_urls: set[str] = set()
        for item in items:
            url = (item.get("link") or "").strip()
            title = (item.get("title") or "").strip()
            if not url or not title or url in seen_urls:
                continue

            source_name = (item.get("source_id") or item.get("source_name") or "Unknown Source").strip()
            seen_urls.add(url)
            articles.append(
                Article(
                    title=title,
                    description=(item.get("description") or "").strip(),
                    url=url,
                    source=source_name or "Unknown Source",
                    published_at=(item.get("pubDate") or "").strip(),
                    content=(item.get("content") or item.get("description") or "").strip(),
                )
            )
        return articles
