import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from current_affairs_bot.document_client import DocumentClient


def build_settings(source_dir: Path, **overrides: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "books_source_dir": source_dir,
        "books_chunk_size": 180,
        "books_chunk_overlap": 30,
        "books_max_chunks_per_document": 10,
        "max_articles_per_cycle": 2,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class DocumentClientTests(unittest.TestCase):
    def test_fetch_latest_loads_book_excerpts_from_text_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            source_dir.joinpath("atomic-habits.txt").write_text(
                (
                    "Small daily actions change identity over time. "
                    "Consistency matters more than intensity.\n\n"
                    "Each repeated action becomes a vote for the person you want to become. "
                    "Momentum grows when your habits stay visible."
                ),
                encoding="utf-8",
            )
            client = DocumentClient(build_settings(source_dir))

            excerpts = client.fetch_latest()

        self.assertEqual(len(excerpts), 2)
        self.assertTrue(excerpts[0].url.startswith("book://atomic-habits.txt#chunk-1"))
        self.assertEqual(excerpts[0].source, "Atomic Habits")
        self.assertIn("Consistency", excerpts[0].description)


if __name__ == "__main__":
    unittest.main()
