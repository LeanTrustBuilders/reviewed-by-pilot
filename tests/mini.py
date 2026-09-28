"""A small dataset (S2, ltb-dataset/2) of three Tau Ceti-like declarations, and records (S3) about
them, for the tests of the page and of the named results."""
from __future__ import annotations

import json
import struct
from pathlib import Path

from evidence_core import Dataset
from evidence_core import records as rec

COMMIT = "c0ffee1234567"
# name, module, kind, isProp, meaning, local, legacy meaning
DECLS = [("TauCeti.X.f", "TauCeti.NumberTheory.X", "definition", False, "aaaaaaaaaaaaaaaa", "1111111111111111", "a0a0a0a0a0a0a0a0"),
         ("TauCeti.X.f_one", "TauCeti.NumberTheory.X", "theorem", True, "bbbbbbbbbbbbbbbb", "2222222222222222", "b0b0b0b0b0b0b0b0"),
         ("TauCeti.Y.g", "TauCeti.Algebra.Y", "definition", False, "cccccccccccccccc", "3333333333333333", "c0c0c0c0c0c0c0c0"),
         ("TauCeti.Y.g_bad", "TauCeti.Algebra.Y", "theorem", True, "dddddddddddddddd", "4444444444444444", "d0d0d0d0d0d0d0d0")]
# f_one rests on f
EDGES = [(1, 0)]

INDEX = {"tauceti": COMMIT, "read": "2026-09-21T15:00:00Z",
         "modules": [{"module": "TauCeti.NumberTheory.X", "path": "TauCeti/NumberTheory/X.lean", "doc": "# X\n\nAbout X.", "url": "u", "declarations": 2},
                     {"module": "TauCeti.Algebra.Y", "path": "TauCeti/Algebra/Y.lean", "doc": "", "url": "v", "declarations": 2}],
         "declarations": [
             {"name": "TauCeti.X.f", "kind": "def", "keyword": "abbrev", "module": "TauCeti.NumberTheory.X", "path": "TauCeti/NumberTheory/X.lean",
              "line": 3, "end": 4, "doc": "The **function** `f`. It is one.", "source": "abbrev f := 1", "hash": "aaaaaaaaaaaaaaaa", "url": "u1"},
             {"name": "TauCeti.X.f_one", "kind": "theorem", "keyword": "lemma", "module": "TauCeti.NumberTheory.X", "path": "TauCeti/NumberTheory/X.lean",
              "line": 6, "end": 6, "doc": "", "source": "lemma f_one : f = 1", "hash": "bbbbbbbbbbbbbbbb", "url": "u2"},
             {"name": "TauCeti.Y.g", "kind": "def", "keyword": "def", "module": "TauCeti.Algebra.Y", "path": "TauCeti/Algebra/Y.lean",
              "line": 1, "end": 1, "doc": "A map.", "source": "def g := 2", "hash": "cccccccccccccccc", "url": "u3"},
             {"name": "TauCeti.Y.g_bad", "kind": "theorem", "keyword": "theorem", "module": "TauCeti.Algebra.Y", "path": "TauCeti/Algebra/Y.lean",
              "line": 3, "end": 3, "doc": "", "source": "theorem g_bad : g = 2", "hash": "dddddddddddddddd", "url": "u4"}],
         "examples": [{"path": "TauCeti/NumberTheory/X.lean", "line": 9, "end": 9, "statement": "example : f = 1", "sorry": False,
                       "tests": ["TauCeti.X.f"], "url": "u9"}]}
SETTINGS = {"repo": "LeanTrustBuilders/reviewed-by-pilot", "bulk_issue": 1, "tauceti": COMMIT}


def dataset(root: Path) -> Dataset:
    """Writes the dataset under ``root`` and loads it."""
    (root / "edges").mkdir(parents=True)
    (root / "facets").mkdir()
    lines = []
    for i, (name, mod, kind, prop, meaning, local, legacy) in enumerate(DECLS):
        lines.append({"id": i, "name": name, "module": mod, "package": "TauCeti", "scope": "project", "kind": kind,
                      "isProp": prop, "hashes": {"meaning": meaning, "local": local, "content": meaning}})
    (root / "decls.jsonl").write_text("".join(json.dumps(l) + "\n" for l in lines))
    (root / "edges" / "meaning.bin").write_bytes(b"".join(struct.pack("<ii", s, t) for s, t in EDGES))
    # g_bad is proved with sorry
    (root / "facets" / "axioms.jsonl").write_text("".join(
        json.dumps({"decl": n, "axioms": ["sorryAx"] if n.endswith("g_bad") else [], "sorry": n.endswith("g_bad")}) + "\n"
        for n, *_ in DECLS))
    (root / "modules.jsonl").write_text("".join(json.dumps({"name": m["module"], "path": m["path"], "doc": [], "imports": []}) + "\n"
                                                for m in INDEX["modules"]))
    meta = {"spec": "ltb-dataset/2", "library": {"root": "TauCeti", "commit": COMMIT, "unavailable": []},
            "hasher": {"name": "ltb-meaning/1", "meaning": "ltb-meaning/1", "local": "ltb-local/2",
                       "content": "ltb-content/1"},
            "counts": {"nodes": len(DECLS), "project": len(DECLS), "upstream": 0},
            "edges": [{"name": "meaning", "file": "edges/meaning.bin", "format": "i32le-pairs", "count": len(EDGES)}],
            "facets": [{"name": "axioms", "file": "facets/axioms.jsonl", "schema": "axioms/1", "count": len(DECLS)}],
            "modules": {"file": "modules.jsonl", "count": len(INDEX["modules"])}}
    (root / "meta.json").write_text(json.dumps(meta))
    return Dataset.load(root)


def person(login: str) -> dict:
    return {"kind": "person", "identity": {"kind": "github", "id": login}}


def agent(login: str, tool: str = "Codex", session: str = "c1") -> dict:
    return {"kind": "agent", "identity": {"kind": "github", "id": login}, "agent": {"tool": tool, "session": session}}


def record(ds: Dataset, kind: str, decl: str, by: dict, at: str, issue: int | None = None, **fields) -> dict:
    r = {"schema": rec.SCHEMA, "kind": kind, "subject": rec.subject_from_decl(ds.by_name[decl], ds), "by": by, "at": at,
         **({"origin": {"kind": "issue", "ref": f"{SETTINGS['repo']}#{issue}"}} if issue else {}), **fields}
    return rec.with_id(r)


def status(target: dict, state: str, by: dict, at: str, **fields) -> dict:
    return rec.with_id({"schema": rec.SCHEMA, "kind": "status", "target": target["id"], "state": state, "by": by,
                        "at": at, **fields})
