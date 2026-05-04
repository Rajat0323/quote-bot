import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import ZipFile

from current_affairs_bot.config import Settings
from current_affairs_bot.models import Article


LOGGER = logging.getLogger(__name__)


class DocumentClient:
    SUPPORTED_EXTENSIONS = {".txt", ".md", ".docx", ".json", ".pdf"}

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def fetch_latest(self, posted_urls: set[str] | None = None) -> list[Article]:
        posted_urls = posted_urls or set()
        source_dir = self.settings.books_source_dir
        source_dir.mkdir(parents=True, exist_ok=True)

        excerpts: list[Article] = []
        fresh_count = 0
        documents_loaded = 0
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue
            if self._should_skip_document(path):
                LOGGER.info("Skipped helper document: %s", path)
                continue

            text = self._read_document(path)
            if not text:
                LOGGER.info("Skipped empty document: %s", path)
                continue

            documents_loaded += 1
            book_title = self._humanize_title(path.stem)
            published_at = self._file_modified_at(path)

            for chunk_index, chunk in enumerate(self._chunk_text(text), start=1):
                document_id = self._build_document_id(path, chunk_index)
                excerpts.append(
                    Article(
                        title=f"{book_title} | Insight {chunk_index}",
                        description=self._build_description(chunk),
                        url=document_id,
                        source=book_title,
                        published_at=published_at,
                        content=chunk,
                    )
                )
                if document_id not in posted_urls:
                    fresh_count += 1
                if fresh_count >= self.settings.max_articles_per_cycle:
                    break

            if fresh_count >= self.settings.max_articles_per_cycle:
                break

        if documents_loaded == 0:
            LOGGER.warning(
                "No supported book source files found in %s. Add at least one .txt, .md, .docx, .json, or .pdf file to enable books-mode posting.",
                source_dir,
            )
        LOGGER.info(
            "Loaded %s excerpt(s) from %s document(s) in books mode with %s fresh candidate(s).",
            len(excerpts),
            documents_loaded,
            fresh_count,
        )
        return excerpts

    def _read_document(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md"}:
            return self._normalize_text(path.read_text(encoding="utf-8", errors="ignore"))
        if suffix == ".json":
            return self._normalize_text(self._read_json_document(path))
        if suffix == ".docx":
            return self._normalize_text(self._read_docx_document(path))
        if suffix == ".pdf":
            return self._normalize_text(self._read_pdf_document(path))
        return ""

    def _read_json_document(self, path: Path) -> str:
        raw_text = path.read_text(encoding="utf-8", errors="ignore")
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return raw_text

        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            preferred_keys = ("title", "subtitle", "description", "summary", "content", "text", "body")
            values = [str(payload[key]).strip() for key in preferred_keys if str(payload.get(key, "")).strip()]
            if values:
                return "\n\n".join(values)
            return json.dumps(payload, ensure_ascii=False)
        if isinstance(payload, list):
            values: list[str] = []
            for item in payload:
                if isinstance(item, str) and item.strip():
                    values.append(item.strip())
                elif isinstance(item, dict):
                    for key in ("title", "content", "text", "body", "summary"):
                        value = str(item.get(key, "")).strip()
                        if value:
                            values.append(value)
                            break
            return "\n\n".join(values)
        return raw_text

    def _read_docx_document(self, path: Path) -> str:
        with ZipFile(path) as archive:
            with archive.open("word/document.xml") as handle:
                xml_content = handle.read()
        root = ElementTree.fromstring(xml_content)
        text_parts = [part.strip() for part in root.itertext() if part and part.strip()]
        return "\n".join(text_parts)

    def _read_pdf_document(self, path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "PDF support requires the 'pypdf' package. Install dependencies from requirements.txt."
            ) from exc

        reader = PdfReader(str(path), strict=False)
        text_parts: list[str] = []
        for page in reader.pages:
            extracted = page.extract_text() or ""
            cleaned = extracted.strip()
            if cleaned:
                text_parts.append(cleaned)
        return "\n\n".join(text_parts)

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _chunk_text(self, text: str) -> list[str]:
        if not text:
            return []

        chunk_size = self.settings.books_chunk_size
        overlap = self.settings.books_chunk_overlap
        max_chunks = self.settings.books_max_chunks_per_document
        chunks: list[str] = []
        start = 0
        text_length = len(text)

        while start < text_length and len(chunks) < max_chunks:
            max_end = min(text_length, start + chunk_size)
            end = max_end
            if max_end < text_length:
                tail = text[start:max_end]
                breakpoint_candidates = [
                    tail.rfind("\n\n"),
                    tail.rfind(". "),
                    tail.rfind("! "),
                    tail.rfind("? "),
                ]
                best_break = max(breakpoint_candidates)
                if best_break >= chunk_size // 2:
                    end = start + best_break + 1

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= text_length:
                break

            next_start = max(start + 1, end - overlap)
            if next_start <= start:
                next_start = end
            start = next_start

        return chunks

    def _build_document_id(self, path: Path, chunk_index: int) -> str:
        relative_path = path.relative_to(self.settings.books_source_dir).as_posix()
        return f"book://{relative_path}#chunk-{chunk_index}"

    def _build_description(self, text: str) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= 220:
            return compact
        return compact[:217].rstrip() + "..."

    def _humanize_title(self, raw_title: str) -> str:
        text = raw_title.replace("_", " ").replace("-", " ").strip()
        return re.sub(r"\s+", " ", text).title() or "Book Note"

    def _file_modified_at(self, path: Path) -> str:
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return modified_at.isoformat()

    def _should_skip_document(self, path: Path) -> bool:
        return path.stem.strip().lower() == "readme"
