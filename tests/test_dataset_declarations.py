"""Reading the declarations from a dataset (scripts/dataset_declarations.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dataset_declarations import after_docstring  # noqa: E402

SOURCE = """/-- The **ideal von Mangoldt function**, with `f := g` in its text
and a nested /- comment -/. -/

@[simp]
noncomputable def vonMangoldt : ℕ → ℂ := fun _ ↦ 0
/-- A doc comment, then code on the same line. -/ def one : ℕ := 1
def two : ℕ := 2""".splitlines()


class Source(unittest.TestCase):
    def test_a_declaration_is_shown_from_below_its_doc_comment(self):
        self.assertEqual(after_docstring(SOURCE, 1, 5), 4)
        self.assertEqual(SOURCE[4 - 1], "@[simp]")

    def test_a_declaration_without_doc_comment_or_sharing_its_line_is_kept_whole(self):
        self.assertEqual(after_docstring(SOURCE, 7, 7), 7)
        self.assertEqual(after_docstring(SOURCE, 6, 6), 6)


if __name__ == "__main__":
    unittest.main()
