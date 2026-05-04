import json
import logging
import re

import requests

from current_affairs_bot.config import Settings
from current_affairs_bot.models import Article, GeneratedPost, MCQ


LOGGER = logging.getLogger(__name__)

NEWS_SYSTEM_PROMPT = """
You create concise current affairs study material for UPSC and SSC aspirants.
Return only valid JSON.
Keep the tone clear, factual, and easy to revise quickly.
Use only the facts available in the provided article details.
""".strip()

BOOKS_SYSTEM_PROMPT = """
You turn book excerpts into motivational Telegram-ready content.
Return only valid JSON.
Keep the tone warm, uplifting, and simple.
Use only the ideas available in the provided excerpt.
Do not copy long lines from the source text verbatim.
""".strip()


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()

    def generate_post(self, article: Article) -> GeneratedPost:
        payload = {
            "model": self.settings.openai_model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {
                    "role": "user",
                    "content": self._build_user_prompt(article),
                },
            ],
        }
        response = self.session.post(
            f"{self.settings.openai_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.settings.request_timeout_seconds,
        )
        response.raise_for_status()
        raw_payload = response.json()
        message = raw_payload["choices"][0]["message"]["content"]
        content = self._message_to_text(message)
        parsed = self._parse_json(content)
        generated = self._coerce_generated_post(article, parsed)
        LOGGER.info("Generated summary and %s MCQs for article: %s", len(generated.mcqs), article.title)
        return generated

    def _build_user_prompt(self, article: Article) -> str:
        if self.settings.content_mode == "books":
            return f"""
Create a motivational Telegram post from this book excerpt.

Return JSON with exactly these keys:
{{
  "title": "short emotional theme title",
  "quote": "1-2 line original motivational quote inspired by the excerpt",
  "summary": "80-140 word attractive Telegram caption in simple English",
  "why_it_matters": ["short takeaway 1", "short takeaway 2"],
  "hashtags": ["#TagOne", "#TagTwo", "#TagThree"]
}}

Rules:
- quote must be original wording inspired by the excerpt, not a direct copyrighted line
- summary should feel polished, shareable, and human
- why_it_matters should contain 2 short self-growth takeaways
- hashtags should contain 5 to 8 concise tags without spaces
- avoid cliches, spammy language, and fake claims

Book source: {article.source}
Excerpt title: {article.title}
Excerpt: {article.content[:4000]}
""".strip()

        return f"""
Create a UPSC/SSC current affairs digest from this article.

Return JSON with exactly these keys:
{{
  "title": "short cleaned title",
  "summary": "60-90 words in simple English",
  "why_it_matters": ["point 1", "point 2"],
  "mcqs": [
    {{
      "question": "question text",
      "options": ["option A", "option B", "option C", "option D"],
      "answer_index": 0,
      "explanation": "1-2 sentence explanation"
    }}
  ]
}}

Rules:
- summary must be concise and revision-friendly
- why_it_matters should have 2 short points
- create {self.settings.mcqs_per_article} MCQs
- every MCQ must have exactly 4 options
- answer_index must be 0, 1, 2, or 3
- avoid jargon and sensational wording
- include India relevance whenever the article supports it

Article title: {article.title}
Source: {article.source}
Published at: {article.published_at}
Description: {article.description}
Content: {article.content[:3000]}
URL: {article.url}
""".strip()

    def _system_prompt(self) -> str:
        if self.settings.content_mode == "books":
            return BOOKS_SYSTEM_PROMPT
        return NEWS_SYSTEM_PROMPT

    def _message_to_text(self, message: str | list[dict]) -> str:
        if isinstance(message, str):
            return message.strip()
        if isinstance(message, list):
            parts: list[str] = []
            for item in message:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "\n".join(parts).strip()
        raise TypeError(f"Unsupported message content type: {type(message)!r}")

    def _parse_json(self, raw_text: str) -> dict:
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    def _coerce_generated_post(self, article: Article, payload: dict) -> GeneratedPost:
        title = str(payload.get("title") or article.title).strip()
        summary = str(payload.get("summary") or article.description or article.title).strip()
        quote = str(payload.get("quote") or "").strip()

        why_raw = payload.get("why_it_matters") or []
        if isinstance(why_raw, str):
            why_it_matters = [why_raw.strip()]
        else:
            why_it_matters = [str(item).strip() for item in why_raw if str(item).strip()]
        default_takeaway = (
            "Relevant for current affairs revision."
            if self.settings.content_mode == "news"
            else "A reminder to keep growing with patience and purpose."
        )
        why_it_matters = why_it_matters[:2] or [default_takeaway]

        mcqs: list[MCQ] = []
        for item in payload.get("mcqs", []):
            if not isinstance(item, dict):
                continue
            options = [str(option).strip() for option in item.get("options", []) if str(option).strip()]
            answer_index = item.get("answer_index")
            if len(options) != 4:
                continue
            if not isinstance(answer_index, int) or not 0 <= answer_index <= 3:
                continue
            mcqs.append(
                MCQ(
                    question=str(item.get("question") or "").strip(),
                    options=options,
                    answer_index=answer_index,
                    explanation=str(item.get("explanation") or "").strip(),
                )
            )

        hashtags = self._coerce_hashtags(payload.get("hashtags"))
        return GeneratedPost(
            title=title or article.title,
            summary=summary,
            why_it_matters=why_it_matters,
            mcqs=mcqs[: self.settings.mcqs_per_article],
            quote=quote,
            hashtags=hashtags,
        )

    def _coerce_hashtags(self, raw_hashtags: object) -> list[str]:
        if isinstance(raw_hashtags, str):
            items = re.findall(r"#?[A-Za-z0-9_]+", raw_hashtags)
        elif isinstance(raw_hashtags, list):
            items = [str(item).strip() for item in raw_hashtags if str(item).strip()]
        else:
            items = []

        hashtags: list[str] = []
        seen: set[str] = set()
        for item in items:
            normalized = "#" + "".join(ch for ch in item if ch.isalnum() or ch == "_").lstrip("#")
            if len(normalized) <= 1:
                continue
            if normalized.lower() in seen:
                continue
            seen.add(normalized.lower())
            hashtags.append(normalized)
        return hashtags[:8]

