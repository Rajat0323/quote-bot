import json
from datetime import datetime, timezone
from pathlib import Path

from current_affairs_bot.models import Article, PendingGroupReveal


class StateStore:
    def __init__(self, path: Path, max_items: int = 1000) -> None:
        self.path = path
        self.max_items = max_items
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def was_posted(self, article: Article) -> bool:
        state = self._load()
        return article.url in state

    def posted_urls(self) -> set[str]:
        return set(self._load().keys())

    def mark_posted(self, article: Article) -> None:
        state = self._load()
        state[article.url] = {
            "title": article.title,
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        while len(state) > self.max_items:
            oldest_key = next(iter(state))
            state.pop(oldest_key)
        self._save(state)

    def _load(self) -> dict[str, dict[str, str]]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _save(self, payload: dict[str, dict[str, str]]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2)


class PendingRevealStore:
    def __init__(self, path: Path, max_items: int = 5000) -> None:
        self.path = path
        self.max_items = max_items
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def due_reveals(self, now: datetime | None = None) -> list[PendingGroupReveal]:
        now = now or datetime.now(timezone.utc)
        due: list[PendingGroupReveal] = []
        for reveal in self._load():
            try:
                due_at = datetime.fromisoformat(reveal.due_at)
            except ValueError:
                due.append(reveal)
                continue
            if due_at <= now:
                due.append(reveal)
        return due

    def add_many(self, reveals: list[PendingGroupReveal]) -> None:
        if not reveals:
            return
        existing = self._load()
        existing.extend(reveals)
        existing = existing[-self.max_items :]
        self._save(existing)

    def remove_ids(self, reveal_ids: set[str]) -> None:
        if not reveal_ids:
            return
        remaining = [reveal for reveal in self._load() if reveal.reveal_id not in reveal_ids]
        self._save(remaining)

    def _load(self) -> list[PendingGroupReveal]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            return []
        reveals: list[PendingGroupReveal] = []
        for item in payload:
            if isinstance(item, dict):
                reveal = PendingGroupReveal.from_dict(item)
                if reveal.reveal_id:
                    reveals.append(reveal)
        return reveals

    def _save(self, payload: list[PendingGroupReveal]) -> None:
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump([reveal.to_dict() for reveal in payload], handle, ensure_ascii=True, indent=2)

