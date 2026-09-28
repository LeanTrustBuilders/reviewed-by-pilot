"""Reading the declarations the page lists from a dataset and a checkout (scripts/dataset_declarations.py),
through evidence-core's source reader."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dataset_declarations import read  # noqa: E402
from evidence_core import Dataset  # noqa: E402
import mini  # noqa: E402

X = """namespace TauCeti.X

/-- The **function** `f`, with `a := b` in its docstring. -/
@[simp]
abbrev f : Nat := 1

/-- It is one. -/
theorem f_one : f = 1 := by
  rfl

end TauCeti.X
"""
ROWS = [("TauCeti.X.f", "TauCeti/NumberTheory/X.lean", (3, 0), (5, 19), "abbrev"),
        ("TauCeti.X.f_one", "TauCeti/NumberTheory/X.lean", (7, 0), (9, 5), "theorem")]


class Read(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        mini.dataset(root / "ds")
        (root / "ds" / "facets" / "source.jsonl").write_text("".join(
            json.dumps({"decl": n, "path": p, "start": list(s), "end": list(e), "keyword": k}) + "\n" for n, p, s, e, k in ROWS))
        meta = json.loads((root / "ds" / "meta.json").read_text())
        meta["facets"].append({"name": "source", "file": "facets/source.jsonl", "schema": "source/1", "count": len(ROWS)})
        (root / "ds" / "meta.json").write_text(json.dumps(meta))
        (root / "src" / "TauCeti" / "NumberTheory").mkdir(parents=True)
        (root / "src" / "TauCeti" / "NumberTheory" / "X.lean").write_text(X)
        self.ds, self.src = Dataset.load(root / "ds"), root / "src"
        self.found = {d["name"]: d for d in read(self.ds, self.src, mini.COMMIT, "TauCetiProject/TauCeti")["declarations"]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_declarations_with_a_source_range_are_listed(self):
        self.assertEqual(sorted(self.found), ["TauCeti.X.f", "TauCeti.X.f_one"])

    def test_a_definition_is_shown_whole_below_its_doc_comment(self):
        f = self.found["TauCeti.X.f"]
        self.assertEqual((f["source"], f["line"], f["end"], f["keyword"], f["kind"]),
                         ("@[simp]\nabbrev f : Nat := 1", 4, 5, "abbrev", "def"))
        self.assertTrue(f["url"].endswith("#L4-L5"))

    def test_a_theorem_is_shown_by_its_statement(self):
        self.assertEqual(self.found["TauCeti.X.f_one"]["source"], "theorem f_one : f = 1")

    def test_a_slice_of_modules(self):
        """With `modules`, the declarations and modules under those prefixes only; links go to the repo."""
        kept = read(self.ds, self.src, mini.COMMIT, "o/lib", ["TauCeti.NumberTheory"])
        none = read(self.ds, self.src, mini.COMMIT, "o/lib", ["TauCeti.Elsewhere"])
        self.assertEqual(sorted(d["name"] for d in kept["declarations"]), ["TauCeti.X.f", "TauCeti.X.f_one"])
        self.assertTrue(all(d["url"].startswith("https://github.com/o/lib/blob/") for d in kept["declarations"]))
        self.assertEqual((none["declarations"], none["modules"]), ([], []))


if __name__ == "__main__":
    unittest.main()
