import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from current_affairs_bot.document_client import DocumentClient


TEST_TEMP_ROOT = (Path(__file__).resolve().parent / ".tmp_document_client").resolve()
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


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
        source_dir = TEST_TEMP_ROOT / "books_case_one"
        shutil.rmtree(source_dir, ignore_errors=True)
        source_dir.mkdir(parents=True, exist_ok=True)
        try:
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
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)

        self.assertEqual(len(excerpts), 2)
        self.assertTrue(excerpts[0].url.startswith("book://atomic-habits.txt#chunk-1"))
        self.assertEqual(excerpts[0].source, "Atomic Habits")
        self.assertIn("Consistency", excerpts[0].description)

    def test_fetch_latest_skips_readme_helper_files(self) -> None:
        source_dir = TEST_TEMP_ROOT / "books_case_two"
        shutil.rmtree(source_dir, ignore_errors=True)
        source_dir.mkdir(parents=True, exist_ok=True)
        try:
            source_dir.joinpath("README.md").write_text(
                "Add your source book files here.",
                encoding="utf-8",
            )
            source_dir.joinpath("mindset.txt").write_text(
                "Your habits shape your future more than your moods do.",
                encoding="utf-8",
            )
            client = DocumentClient(build_settings(source_dir, max_articles_per_cycle=5))

            excerpts = client.fetch_latest()
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)

        self.assertEqual(len(excerpts), 1)
        self.assertEqual(excerpts[0].source, "Mindset")

    def test_fetch_latest_loads_book_excerpts_from_pdf_files(self) -> None:
        source_dir = TEST_TEMP_ROOT / "books_case_pdf"
        shutil.rmtree(source_dir, ignore_errors=True)
        source_dir.mkdir(parents=True, exist_ok=True)
        try:
            pdf_path = source_dir.joinpath("deep-work.pdf")
            pdf_path.write_bytes(b"%PDF-1.4\n%mock pdf content")
            client = DocumentClient(build_settings(source_dir, max_articles_per_cycle=5))

            with patch.object(
                DocumentClient,
                "_read_pdf_document",
                return_value=(
                    "Focus is a competitive advantage. "
                    "Deep work compounds when attention stays uninterrupted."
                ),
            ):
                excerpts = client.fetch_latest()
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)

        self.assertEqual(len(excerpts), 1)
        self.assertTrue(excerpts[0].url.startswith("book://deep-work.pdf#chunk-1"))
        self.assertEqual(excerpts[0].source, "Deep Work")
        self.assertIn("competitive advantage", excerpts[0].description)


if __name__ == "__main__":
    unittest.main()
