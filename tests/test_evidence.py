"""The pilot's link to the suite: ledger entries become S3 evidence records keyed by a dataset's
hashes (scripts/evidence_sync.py), and the page's marks carry their evidence-core status
(scripts/build_site.py). Runs on a small dataset written here, in the format trust-extract writes."""
from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_site  # noqa: E402
import evidence_sync  # noqa: E402
from evidence_core import Dataset, Evidence  # noqa: E402


def write_dataset(root: Path, commit: str, hashes: dict) -> Dataset:
    """Three declarations: `T.claim` (a theorem) rests on `T.foo`, which rests on `T.bar`."""
    names = ["T.claim", "T.foo", "T.bar"]
    decls = [{"id": i, "name": n, "module": "T.M", "package": "T", "scope": "project",
              "kind": "theorem" if n == "T.claim" else "definition", "isProp": n == "T.claim",
              "hashes": hashes[n]} for i, n in enumerate(names)]
    (root / "edges").mkdir(parents=True)
    (root / "facets").mkdir()
    (root / "decls.jsonl").write_text("".join(json.dumps(d) + "\n" for d in decls))
    edges = struct.pack("<iiii", 0, 1, 1, 2)
    for notion in ("statement", "meaning"):
        (root / "edges" / f"{notion}.bin").write_bytes(edges)
    meta = {"spec": "ltb-dataset/0", "producer": {"name": "test", "version": "0"},
            "library": {"root": "T", "package": "T", "commit": commit},
            "toolchain": "leanprover/lean4:v4.34.0-rc2",
            "hasher": {"name": "semantic_hash", "revision": "r", "local": "ltb-local-v1"},
            "counts": {"nodes": 3, "project": 3, "upstream": 0},
            "edges": [{"name": n, "file": f"edges/{n}.bin", "format": "i32le-pairs", "count": 2}
                      for n in ("statement", "meaning")],
            "facets": []}
    (root / "meta.json").write_text(json.dumps(meta))
    return Dataset.load(root)


HASHES_A = {"T.claim": {"meaning": "a" * 16, "local": "1" * 16}, "T.foo": {"meaning": "b" * 16, "local": "2" * 16},
            "T.bar": {"meaning": "c" * 16, "local": "3" * 16}}
# In B, `T.bar` was rewritten: its meaning and local hashes change, and so do the meaning hashes of
# everything resting on it, whose local hashes do not.
HASHES_B = {"T.claim": {"meaning": "d" * 16, "local": "1" * 16}, "T.foo": {"meaning": "e" * 16, "local": "2" * 16},
            "T.bar": {"meaning": "f" * 16, "local": "4" * 16}}


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.a = write_dataset(tmp / "a", "A", HASHES_A)
        self.b = write_dataset(tmp / "b", "B", HASHES_B)
        self.reviews = tmp / "reviews"
        self.reviews.mkdir()
        self.saved = evidence_sync.REVIEWS
        evidence_sync.REVIEWS = self.reviews
        mark = {"schema": "reviewed-by/v1", "decl": "T.foo", "hash": "x", "tauceti": "A", "trailer": "Reviewed-by",
                "by": "someone", "kind": "person", "agent": "", "evidence": "checked against the book",
                "source": {"issue": 3}, "at": "2026-09-26T10:00:00Z"}
        (self.reviews / "records.jsonl").write_text(json.dumps(mark) + "\n")
        self.index = {"tauceti": "B", "declarations": [{"name": n} for n in HASHES_B]}

    def tearDown(self):
        evidence_sync.REVIEWS = self.saved
        self.tmp.cleanup()

    def sync(self):
        return evidence_sync.sync(self.a, {"A": self.a}, "owner/pilot", self.reviews.parent / "evidence",
                                  inherited={"repo": "owner/original", "until": "2026-09-25T16:00:00Z"})

    def records(self):
        from evidence_core.store import Store
        return Store.load(self.reviews.parent / "evidence").records

    def test_sync_is_idempotent_and_keyed_by_the_dataset(self):
        new = self.sync()
        # Written by a person, under their GitHub account; the store checks every record.
        self.assertEqual(new[0]["by"]["identity"], {"kind": "github", "id": "someone"})
        self.assertEqual(len(new), 1)
        subject = new[0]["subject"]
        self.assertEqual((subject["name"], subject["commit"], subject["hashes"]["meaning"]), ("T.foo", "A", "b" * 16))
        self.assertEqual(new[0]["origin"]["ref"], "owner/pilot#3")  # made after the fork
        self.assertEqual(self.sync(), [])

    def test_inherited_entries_link_to_the_original_repository(self):
        path = self.reviews / "records.jsonl"
        entry = json.loads(path.read_text())
        entry["at"] = "2026-09-22T10:00:00Z"
        path.write_text(json.dumps(entry) + "\n")
        self.assertEqual(self.sync()[0]["origin"]["ref"], "owner/original#3")

    def test_marks_carry_their_status(self):
        self.sync()
        records = self.records()
        now = build_site.marks_from_evidence(self.index, Evidence.resolve(records, self.a))
        self.assertEqual([(m["status"], m["current"]) for m in now["T.foo"]], [("current", True)])
        later = build_site.marks_from_evidence(self.index, Evidence.resolve(records, self.b))
        self.assertEqual([(m["status"], m["current"]) for m in later["T.foo"]], [("stale-underneath", False)])
        self.assertEqual(later["T.foo"][0]["url"], "https://github.com/owner/pilot/issues/3")

    def test_named_coverage(self):
        self.sync()
        records = self.records()
        named = {"T.claim": {"name": "The claim", "what": "result", "about": "", "sources": []}}
        build_site.named_coverage(named, Evidence.resolve(records, self.a))
        self.assertEqual(named["T.claim"]["coverage"], {"members": 3, "people": 1, "any": 1, "problems": 0, "upstream": 0})


if __name__ == "__main__":
    unittest.main()
