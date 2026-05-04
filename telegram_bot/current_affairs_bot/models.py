from dataclasses import dataclass, field


@dataclass(frozen=True)
class Article:
    title: str
    description: str
    url: str
    source: str
    published_at: str
    content: str


@dataclass(frozen=True)
class MCQ:
    question: str
    options: list[str]
    answer_index: int
    explanation: str


@dataclass(frozen=True)
class GeneratedPost:
    title: str
    summary: str
    why_it_matters: list[str]
    mcqs: list[MCQ]
    quote: str = ""
    hashtags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PendingGroupReveal:
    reveal_id: str
    article_title: str
    question: str
    answer_label: str
    answer_text: str
    explanation: str
    due_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "reveal_id": self.reveal_id,
            "article_title": self.article_title,
            "question": self.question,
            "answer_label": self.answer_label,
            "answer_text": self.answer_text,
            "explanation": self.explanation,
            "due_at": self.due_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, str]) -> "PendingGroupReveal":
        return cls(
            reveal_id=str(payload.get("reveal_id") or "").strip(),
            article_title=str(payload.get("article_title") or "").strip(),
            question=str(payload.get("question") or "").strip(),
            answer_label=str(payload.get("answer_label") or "").strip(),
            answer_text=str(payload.get("answer_text") or "").strip(),
            explanation=str(payload.get("explanation") or "").strip(),
            due_at=str(payload.get("due_at") or "").strip(),
        )

