import unittest
from types import SimpleNamespace
from unittest.mock import patch

from current_affairs_bot.models import Article, GeneratedPost, MCQ, PendingGroupReveal
from current_affairs_bot.telegram_client import TelegramClient


MIGRATED_GROUP_ID = "-1003705590403"
OLD_GROUP_ID = "-123456789"


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 300
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, data: dict[str, object], timeout: int) -> FakeResponse:
        self.calls.append({"url": url, "data": data, "timeout": timeout})
        if not self.responses:
            raise AssertionError("No fake responses remaining for Telegram request.")
        return self.responses.pop(0)


def build_settings(**overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "content_mode": "news",
        "telegram_bot_token": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef",
        "request_timeout_seconds": 10,
        "telegram_channel_id": "",
        "telegram_group_id": OLD_GROUP_ID,
        "telegram_send_mcq_polls": True,
        "mcqs_per_article": 1,
        "telegram_require_group": True,
        "group_discussion_call_to_action": "Reply with your answer.",
        "telegram_channel_ref": "",
        "telegram_group_ref": "",
        "telegram_brand_name": "Current Affairs Hub",
        "telegram_call_to_action": "Follow for daily updates.",
        "telegram_channel_description": "Daily updates and searchable topic posts.",
        "telegram_discovery_keywords": (),
        "group_answer_delay_minutes": 30,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def build_article() -> Article:
    return Article(
        title="Cabinet clears new education initiative",
        description="A short description",
        url="https://example.com/article",
        source="Example News",
        published_at="2026-05-02T10:00:00Z",
        content="Full article content",
    )


def build_generated_post() -> GeneratedPost:
    return GeneratedPost(
        title="Education initiative approved",
        summary="The cabinet approved a new initiative.",
        why_it_matters=["It can appear in polity and governance questions."],
        mcqs=[
            MCQ(
                question="Which ministry is expected to lead the rollout?",
                options=["Education", "Finance", "Home", "Health"],
                answer_index=0,
                explanation="The education ministry owns the policy rollout.",
            )
        ],
    )


def migrated_group_response() -> FakeResponse:
    return FakeResponse(
        400,
        {
            "ok": False,
            "error_code": 400,
            "description": "Bad Request: group chat was upgraded to a supergroup chat",
            "parameters": {"migrate_to_chat_id": int(MIGRATED_GROUP_ID)},
        },
    )


def rate_limited_response(retry_after: int = 28) -> FakeResponse:
    return FakeResponse(
        429,
        {
            "ok": False,
            "error_code": 429,
            "description": f"Too Many Requests: retry after {retry_after}",
            "parameters": {"retry_after": retry_after},
        },
    )


class TelegramClientMigrationTests(unittest.TestCase):
    def test_broadcast_retries_group_posts_with_migrated_chat_id(self) -> None:
        client = TelegramClient(build_settings())
        client.session = FakeSession(
            [
                migrated_group_response(),
                FakeResponse(200, {"ok": True, "result": {"message_id": 1}}),
                FakeResponse(200, {"ok": True, "result": {"message_id": 2}}),
            ]
        )

        reveals = client.broadcast(build_article(), build_generated_post())

        self.assertEqual(len(reveals), 1)
        self.assertEqual(
            [call["data"]["chat_id"] for call in client.session.calls],
            [OLD_GROUP_ID, MIGRATED_GROUP_ID, MIGRATED_GROUP_ID],
        )
        self.assertEqual(client._resolve_chat_id(OLD_GROUP_ID), MIGRATED_GROUP_ID)

    def test_answer_reveal_retries_when_group_id_migrates(self) -> None:
        client = TelegramClient(build_settings())
        client.session = FakeSession(
            [
                migrated_group_response(),
                FakeResponse(200, {"ok": True, "result": {"message_id": 3}}),
            ]
        )

        client.send_group_answer_reveal(
            PendingGroupReveal(
                reveal_id="reveal-1",
                article_title="Education initiative approved",
                question="Which ministry leads the rollout?",
                answer_label="A",
                answer_text="Education",
                explanation="The education ministry owns the policy rollout.",
                due_at="2026-05-02T10:30:00+00:00",
            )
        )

        self.assertEqual(
            [call["data"]["chat_id"] for call in client.session.calls],
            [OLD_GROUP_ID, MIGRATED_GROUP_ID],
        )

    def test_group_posts_use_messages_only_with_channel_ref_and_hashtags(self) -> None:
        client = TelegramClient(
            build_settings(
                telegram_channel_ref="@currentaffairschannel",
                telegram_discovery_keywords=("Daily current affairs",),
            )
        )
        client.session = FakeSession(
            [
                FakeResponse(200, {"ok": True, "result": {"message_id": 1}}),
                FakeResponse(200, {"ok": True, "result": {"message_id": 2}}),
            ]
        )

        reveals = client.broadcast(build_article(), build_generated_post())

        self.assertEqual(len(reveals), 1)
        self.assertTrue(all(call["url"].endswith("/sendMessage") for call in client.session.calls))
        self.assertTrue(all("@currentaffairschannel" in str(call["data"]["text"]) for call in client.session.calls))
        self.assertTrue(
            all("subscribe for more - @currentaffairschannel" in str(call["data"]["text"]) for call in client.session.calls)
        )
        self.assertTrue(all("#CurrentAffairs" in str(call["data"]["text"]) for call in client.session.calls))
        self.assertTrue(all("Vote in the poll" not in str(call["data"]["text"]) for call in client.session.calls))

    def test_group_answer_reveal_includes_channel_ref_and_hashtags(self) -> None:
        client = TelegramClient(build_settings(telegram_channel_ref="@currentaffairschannel"))
        message = client._build_group_answer_reveal(
            PendingGroupReveal(
                reveal_id="reveal-1",
                article_title="Education initiative approved",
                question="Which ministry leads the rollout?",
                answer_label="A",
                answer_text="Education",
                explanation="The education ministry owns the policy rollout.",
                due_at="2026-05-02T10:30:00+00:00",
            )
        )

        self.assertIn("@currentaffairschannel", message)
        self.assertIn("subscribe for more - @currentaffairschannel", message)
        self.assertIn("#CurrentAffairs", message)

    def test_channel_text_posts_include_channel_ref_in_all_messages(self) -> None:
        client = TelegramClient(
            build_settings(
                telegram_channel_id="@currentaffairschannel",
                telegram_group_id="",
                telegram_channel_ref="@currentaffairschannel",
                telegram_send_mcq_polls=False,
            )
        )
        client.session = FakeSession(
            [
                FakeResponse(200, {"ok": True, "result": True}),
                FakeResponse(200, {"ok": True, "result": {"message_id": 1}}),
                FakeResponse(200, {"ok": True, "result": {"message_id": 2}}),
            ]
        )

        client.broadcast(build_article(), build_generated_post())

        send_message_calls = [call for call in client.session.calls if str(call["url"]).endswith("/sendMessage")]
        self.assertEqual(len(client.session.calls), 3)
        self.assertEqual(len(send_message_calls), 2)
        self.assertTrue(all("@currentaffairschannel" in str(call["data"]["text"]) for call in send_message_calls))
        self.assertTrue(
            all("subscribe for more - @currentaffairschannel" in str(call["data"]["text"]) for call in send_message_calls)
        )
        self.assertTrue(all("#CurrentAffairs" in str(call["data"]["text"]) for call in send_message_calls))

    def test_group_posts_retry_after_rate_limit(self) -> None:
        client = TelegramClient(build_settings())
        client.session = FakeSession(
            [
                rate_limited_response(28),
                FakeResponse(200, {"ok": True, "result": {"message_id": 1}}),
                FakeResponse(200, {"ok": True, "result": {"message_id": 2}}),
            ]
        )

        with patch("current_affairs_bot.telegram_client.time.sleep") as sleep_mock:
            reveals = client.broadcast(build_article(), build_generated_post())

        self.assertEqual(len(reveals), 1)
        sleep_mock.assert_called_once_with(28)
        self.assertEqual(
            [call["data"]["chat_id"] for call in client.session.calls],
            [OLD_GROUP_ID, OLD_GROUP_ID, OLD_GROUP_ID],
        )

    def test_books_channel_post_uses_quote_format_and_book_tags(self) -> None:
        client = TelegramClient(
            build_settings(
                content_mode="books",
                telegram_channel_id="@bookquotesdaily",
                telegram_group_id="",
                telegram_channel_ref="@bookquotesdaily",
                telegram_discovery_keywords=("daily motivation",),
            )
        )
        article = Article(
            title="Atomic Habits | Insight 1",
            description="A short book excerpt about consistency.",
            url="book://atomic-habits.txt#chunk-1",
            source="Atomic Habits",
            published_at="2026-05-04T10:00:00Z",
            content="Big changes grow from small, repeated actions.",
        )
        generated_post = GeneratedPost(
            title="Consistency Wins Quietly",
            summary="Small steps look ordinary today, but they become the proof of your future self.",
            why_it_matters=["Daily effort compounds into visible growth."],
            mcqs=[],
            quote="Stay loyal to the work before the results arrive.",
            hashtags=["#ReadingMotivation"],
        )

        message = client._build_post_message("@bookquotesdaily", article, generated_post)

        self.assertIn("Quote of the Day", message)
        self.assertIn("Inspired by:</b> Atomic Habits", message)
        self.assertIn("#BookQuotes", message)
        self.assertIn("#ReadingMotivation", message)
        self.assertIn("@bookquotesdaily", message)


if __name__ == "__main__":
    unittest.main()
