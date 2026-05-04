from dataclasses import dataclass
from pathlib import Path
import os
import re

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _optional_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _sanitize_secret_like_value(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _first_present(names: tuple[str, ...], default: str = "") -> str:
    for name in names:
        value = _sanitize_secret_like_value(os.getenv(name, ""))
        if value:
            return value
    return default


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer.") from exc


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: str = "") -> tuple[str, ...]:
    raw = _optional_env(name, default)
    if not raw:
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _choice_env(name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = _optional_env(name, default).lower()
    if value not in allowed:
        allowed_text = ", ".join(allowed)
        raise ValueError(f"Environment variable {name} must be one of: {allowed_text}.")
    return value


def _validate_telegram_bot_token(value: str) -> str:
    token = _sanitize_secret_like_value(value)
    if not re.match(r"^\d{6,}:[A-Za-z0-9_-]{20,}$", token):
        raise ValueError(
            "TELEGRAM_BOT_TOKEN does not look like a valid BotFather token. "
            "It should look like '123456789:AA...' without quotes or extra spaces."
        )
    return token


def _validate_chat_id(value: str, env_name: str) -> str:
    chat_id = _sanitize_secret_like_value(value)
    if not chat_id:
        return ""
    if chat_id.startswith("@"):
        if not re.match(r"^@[A-Za-z0-9_]{4,}$", chat_id):
            raise ValueError(
                f"{env_name} does not look like a valid Telegram username-based chat id. "
                "Use @channelusername without quotes."
            )
        return chat_id
    if not re.match(r"^-?\d+$", chat_id):
        raise ValueError(
            f"{env_name} does not look like a valid numeric Telegram chat id. "
            "Use values like -1001234567890 without quotes."
        )
    return chat_id


def _validate_public_ref(value: str, env_name: str) -> str:
    ref = _sanitize_secret_like_value(value)
    if not ref:
        return ""
    if ref.startswith("@"):
        if not re.match(r"^@[A-Za-z0-9_]{4,}$", ref):
            raise ValueError(
                f"{env_name} does not look like a valid Telegram username. "
                "Use @channelusername without quotes."
            )
        return ref
    if ref.startswith("https://t.me/"):
        return ref
    raise ValueError(
        f"{env_name} must be either a Telegram username like @channelusername "
        "or a public link like https://t.me/channelusername."
    )


@dataclass(frozen=True)
class Settings:
    content_mode: str
    telegram_bot_token: str
    telegram_channel_id: str
    telegram_group_id: str
    news_api_key: str
    news_api_url: str
    newsdata_api_key: str
    newsdata_api_url: str
    current_affairs_query: str
    newsdata_india_query: str
    newsdata_world_query: str
    newsdata_india_country: str
    news_language: str
    news_page_size: int
    max_articles_per_cycle: int
    poll_interval_minutes: int
    request_timeout_seconds: int
    state_file: Path
    group_reveal_state_file: Path
    books_source_dir: Path
    books_chunk_size: int
    books_chunk_overlap: int
    books_max_chunks_per_document: int
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    telegram_send_mcq_polls: bool
    mcqs_per_article: int
    telegram_require_group: bool
    telegram_brand_name: str
    telegram_channel_ref: str
    telegram_group_ref: str
    telegram_call_to_action: str
    telegram_channel_description: str
    telegram_discovery_keywords: tuple[str, ...]
    group_answer_delay_minutes: int
    group_discussion_call_to_action: str

    def __post_init__(self) -> None:
        if self.content_mode == "news" and not self.news_api_key and not self.newsdata_api_key:
            raise ValueError(
                "Set at least one news provider key: NEWS_API_KEY or NEWSDATA_API_KEY."
            )
        if self.books_chunk_size <= self.books_chunk_overlap:
            raise ValueError("BOOKS_CHUNK_SIZE must be greater than BOOKS_CHUNK_OVERLAP.")
        if self.telegram_require_group and not self.telegram_group_id:
            raise ValueError(
                "TELEGRAM_GROUP_ID is required because TELEGRAM_REQUIRE_GROUP is enabled. "
                "TELEGRAM_GROUP_REF is only a public link/username and does not send posts by itself."
            )
        if self.telegram_group_ref and not self.telegram_group_id:
            raise ValueError(
                "TELEGRAM_GROUP_REF is set, but TELEGRAM_GROUP_ID is missing. "
                "Use TELEGRAM_GROUP_ID for actual group posting."
            )

    @property
    def chat_ids(self) -> list[str]:
        seen: set[str] = set()
        chat_ids: list[str] = []
        for chat_id in (self.telegram_channel_id, self.telegram_group_id):
            if chat_id and chat_id not in seen:
                seen.add(chat_id)
                chat_ids.append(chat_id)
        return chat_ids

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(BASE_DIR / ".env")
        content_mode = _choice_env("CONTENT_MODE", "news", ("news", "books"))
        state_relative_path = Path(_optional_env("STATE_FILE", "data/posted_articles.json"))
        reveal_state_relative_path = Path(
            _optional_env("GROUP_REVEAL_STATE_FILE", "data/pending_group_reveals.json")
        )
        default_brand_name = "Current Affairs Hub" if content_mode == "news" else "Book Quote Daily"
        default_call_to_action = (
            "Follow for daily UPSC/SSC current affairs, exam-focused summaries, and quick MCQ practice."
            if content_mode == "news"
            else "Join for daily motivational quotes from books, mindset lessons, and shareable self-growth posts."
        )
        default_discovery_keywords = (
            "UPSC current affairs, SSC current affairs, daily current affairs, current affairs quiz, government exam preparation, GK updates"
            if content_mode == "news"
            else "motivational quotes, book quotes, self growth, mindset motivation, daily inspiration, success habits"
        )
        default_channel_description = (
            "Daily UPSC and SSC current affairs updates, exam-ready summaries, MCQs, and revision-focused insights."
            if content_mode == "news"
            else "Daily motivational quotes from books, mindset lessons, self growth insights, and shareable inspiration posts."
        )
        return cls(
            content_mode=content_mode,
            telegram_bot_token=_validate_telegram_bot_token(
                _first_present(("TELEGRAM_BOT_TOKEN", "BOT_TOKEN")) or _require_env("TELEGRAM_BOT_TOKEN")
            ),
            telegram_channel_id=_validate_chat_id(
                _first_present(("TELEGRAM_CHANNEL_ID", "CHANNEL_ID")) or _require_env("TELEGRAM_CHANNEL_ID"),
                "TELEGRAM_CHANNEL_ID",
            ),
            telegram_group_id=_validate_chat_id(
                _first_present(("TELEGRAM_GROUP_ID", "GROUP_ID")),
                "TELEGRAM_GROUP_ID",
            ),
            news_api_key=_first_present(("NEWS_API_KEY", "NEWSAPI_KEY")),
            news_api_url=_optional_env("NEWS_API_URL", "https://newsapi.org/v2/everything"),
            newsdata_api_key=_first_present(("NEWSDATA_API_KEY",)),
            newsdata_api_url=_optional_env("NEWSDATA_API_URL", "https://newsdata.io/api/1/latest"),
            current_affairs_query=_optional_env(
                "CURRENT_AFFAIRS_QUERY",
                "India OR government OR parliament OR economy OR summit OR diplomacy OR science OR sports",
            ),
            newsdata_india_query=_optional_env(
                "NEWSDATA_INDIA_QUERY",
                "India OR government OR parliament OR economy OR summit OR diplomacy OR science OR sports",
            ),
            newsdata_world_query=_optional_env(
                "NEWSDATA_WORLD_QUERY",
                "government OR parliament OR economy OR summit OR diplomacy OR science OR sports",
            ),
            newsdata_india_country=_optional_env("NEWSDATA_INDIA_COUNTRY", "in"),
            news_language=_optional_env("NEWS_LANGUAGE", "en"),
            news_page_size=_int_env("NEWS_PAGE_SIZE", 10),
            max_articles_per_cycle=_int_env("MAX_ARTICLES_PER_CYCLE", 2),
            poll_interval_minutes=_int_env("POLL_INTERVAL_MINUTES", 30),
            request_timeout_seconds=_int_env("REQUEST_TIMEOUT_SECONDS", 30),
            state_file=(BASE_DIR / state_relative_path).resolve(),
            group_reveal_state_file=(BASE_DIR / reveal_state_relative_path).resolve(),
            books_source_dir=(BASE_DIR / Path(_optional_env("BOOKS_SOURCE_DIR", "data/books"))).resolve(),
            books_chunk_size=_int_env("BOOKS_CHUNK_SIZE", 2200),
            books_chunk_overlap=_int_env("BOOKS_CHUNK_OVERLAP", 250),
            books_max_chunks_per_document=_int_env("BOOKS_MAX_CHUNKS_PER_DOCUMENT", 20),
            openai_api_key=_first_present(("OPENAI_API_KEY", "LLM_API_KEY")) or _require_env("OPENAI_API_KEY"),
            openai_base_url=_first_present(("OPENAI_BASE_URL", "LLM_BASE_URL"), "https://api.openai.com/v1"),
            openai_model=_first_present(("OPENAI_MODEL", "LLM_MODEL"), "gpt-4.1-mini"),
            telegram_send_mcq_polls=_bool_env("TELEGRAM_SEND_MCQ_POLLS", True),
            mcqs_per_article=_int_env("MCQS_PER_ARTICLE", 3),
            telegram_require_group=_bool_env("TELEGRAM_REQUIRE_GROUP", False),
            telegram_brand_name=_optional_env("TELEGRAM_BRAND_NAME", default_brand_name),
            telegram_channel_ref=_validate_public_ref(
                _optional_env("TELEGRAM_CHANNEL_REF"),
                "TELEGRAM_CHANNEL_REF",
            ),
            telegram_group_ref=_validate_public_ref(
                _optional_env("TELEGRAM_GROUP_REF"),
                "TELEGRAM_GROUP_REF",
            ),
            telegram_call_to_action=_optional_env("TELEGRAM_CALL_TO_ACTION", default_call_to_action),
            telegram_channel_description=_optional_env(
                "TELEGRAM_CHANNEL_DESCRIPTION",
                default_channel_description,
            ),
            telegram_discovery_keywords=_csv_env(
                "TELEGRAM_DISCOVERY_KEYWORDS",
                default_discovery_keywords,
            ),
            group_answer_delay_minutes=_int_env("GROUP_ANSWER_DELAY_MINUTES", 30),
            group_discussion_call_to_action=_optional_env(
                "GROUP_DISCUSSION_CALL_TO_ACTION",
                "Reply with your reason or one keyword you would revise from this topic.",
            ),
        )

