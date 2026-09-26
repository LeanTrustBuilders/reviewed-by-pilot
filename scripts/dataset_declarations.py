#!/usr/bin/env python3
"""Read the declarations of Tau Ceti from an extracted dataset (S2), for the page.

  python3 scripts/dataset_declarations.py --dataset DIR --clone TAUCETI [--commit SHA]

Writes data/declarations.json, which the page is built from:

- the declarations are the dataset's project nodes: every declaration a person wrote, as the
  compiled library has it, with its kind, module and source range (the checkout gives the text).
  Private theorems are left out: they are steps of proofs, and no meaning rests on a proof. Private
  definitions stay, under their private names: the meaning of public ones can rest on them;
- `hash` is the declaration's **meaning hash** (S1), which a review is keyed by: it stays current
  until the meaning of the declaration or of anything it rests on changes. `legacy` is the meaning
  hash of datasets before `ltb-dataset/1`, which older reviews hold;
- the modules, with their docstrings, are the dataset's (`modules.jsonl`);
- the `example`s that serve as unit tests are the dataset's `examples` facet, which the extractor's
  `scripts/examples.py` adds from the sources (an `example` is not kept in the compiled library).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from evidence_core import Dataset
except ImportError:  # a checkout of evidence-core next to this repository
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evidence-core"))
    from evidence_core import Dataset

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "TauCetiProject/TauCeti"
# The kinds the page knows, from the dataset's kind and the keyword the declaration is written with.
KIND = {"theorem": "theorem", "definition": "def", "instance": "instance", "class": "class",
        "structure": "structure", "inductive": "inductive", "axiom": "def", "opaque": "def"}


def fingerprint(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:12]


def statement(text: str) -> str:
    """A theorem up to its proof: up to the first `:=` outside brackets, so that a named argument
    such as `(K := K)` stays in the statement."""
    depth = 0
    for k, char in enumerate(text):
        if char in "([{⟨⦃":
            depth += 1
        elif char in ")]}⟩⦄":
            depth = max(depth - 1, 0)
        elif depth == 0 and text.startswith(":=", k):
            return text[:k].rstrip()
    return text.rstrip()


def after_docstring(lines: list[str], start: int, end: int) -> int:
    """The line a declaration starts on, below its doc comment: the dataset's source range starts at
    the doc comment, which the page shows apart. Lines are numbered from 1; a doc comment followed by
    code on its last line is kept."""
    i = start - 1
    if i >= len(lines) or not lines[i].lstrip().startswith("/--"):
        return start
    depth = 0
    for j in range(i, min(end, len(lines))):
        line, k = lines[j], 0
        while k < len(line):
            if line.startswith("/-", k):
                depth, k = depth + 1, k + 2
            elif line.startswith("-/", k):
                depth, k = depth - 1, k + 2
                if depth == 0:
                    if line[k:].strip():
                        return start
                    j += 1
                    while j < end - 1 and not lines[j].strip():
                        j += 1
                    return j + 1 if j < end else start
            else:
                k += 1
    return start


def read(dataset: Dataset, clone: Path, commit: str) -> dict:
    lines_of: dict[str, list[str]] = {}

    def lines(path: str) -> list[str]:
        if path not in lines_of:
            p = clone / path
            lines_of[path] = p.read_text(encoding="utf-8", errors="replace").splitlines() if p.exists() else []
        return lines_of[path]

    found = []
    for d in dataset.decls:
        if not d.is_project or (d.name.startswith("_private.") and d.kind == "theorem"):
            continue
        src = dataset.facet_row("source", d.name)
        if src is None:
            continue
        path, (start, _), (end, _) = src["path"], src["start"], src["end"]
        start = after_docstring(lines(path), start, end)
        text = "\n".join(lines(path)[start - 1:end])
        kind = KIND.get(d.kind, "def")
        keyword = src.get("keyword") or ("theorem" if kind == "theorem" else "def")
        if keyword == "lemma":
            kind = "theorem"
        shown = statement(text) if kind == "theorem" else text
        doc = (dataset.facet_row("docstring", d.name) or {}).get("text", "")
        axioms = dataset.facet_row("axioms", d.name) or {}
        found.append({
            "name": d.name, "kind": kind, "keyword": keyword, "module": d.module, "path": path,
            "line": start, "end": end, "doc": doc, "source": shown,
            "hash": d.meaning or fingerprint(shown), "local": d.local, "content": d.content,
            # ltb-dataset/1: the meaning hash of ltb-dataset/0, which marks made before hold.
            "legacy": d.legacy_meaning,
            "text_hash": fingerprint(shown), "package": d.package,
            "sorry": bool(axioms.get("sorry", False)),
            "url": f"https://github.com/{UPSTREAM}/blob/{commit}/{path}#L{start}-L{end}"})
    # Modules, from the dataset; examples, from its `examples` facet.
    count = {}
    for item in found:
        count[item["module"]] = count.get(item["module"], 0) + 1
    modules = [{"module": m["name"], "path": m.get("path", ""), "doc": "\n\n".join(m.get("doc") or []),
                "url": f"https://github.com/{UPSTREAM}/blob/{commit}/{m.get('path', '')}",
                "declarations": count.get(m["name"], 0)} for m in dataset.modules]
    by_example: dict[tuple, dict] = {}
    for name, rows in dataset.facet("examples").items():
        for row in rows:
            for ex in row.get("examples", []):
                key = (ex["path"], ex["line"])
                e = by_example.setdefault(key, {"path": ex["path"], "line": ex["line"], "end": ex["end"],
                                                "statement": ex["statement"], "sorry": ex["sorry"], "tests": [],
                                                "url": f"https://github.com/{UPSTREAM}/blob/{commit}/{ex['path']}#L{ex['line']}-L{ex['end']}"})
                e["tests"].append(name)
    examples = [by_example[k] for k in sorted(by_example)]
    return {"tauceti": commit, "read": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "modules": modules, "declarations": found, "examples": examples,
            "dataset": {"commit": dataset.commit, "producer": dataset.producer(),
                        "toolchain": dataset.toolchain, "hasher": dataset.hasher,
                        "counts": dataset.meta.get("counts", {}),
                        "unavailable": sorted(dataset.unavailable)}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, required=True, help="an extracted dataset (S2)")
    parser.add_argument("--clone", type=Path, required=True, help="a checkout of Tau Ceti at the dataset's commit")
    parser.add_argument("--commit", help="its commit (default: the dataset's)")
    args = parser.parse_args()
    dataset = Dataset.load(args.dataset)
    commit = args.commit or dataset.commit
    head = subprocess.run(["git", "-C", str(args.clone), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if head and head != dataset.commit:
        print(f"warning: the checkout is at {head[:10]}, the dataset at {dataset.commit[:10]}", file=sys.stderr)
    out = read(dataset, args.clone, commit)
    (ROOT / "data" / "declarations.json").write_text(json.dumps(out, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(out['declarations'])} declarations (from the dataset) and {len(out['examples'])} examples "
          f"from {len(out['modules'])} modules at {commit[:7]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
