#!/usr/bin/env python3
"""Read the declarations a reviewer can mark from an extracted dataset (S2) instead of from
regular expressions over the source.

  python3 scripts/dataset_declarations.py --dataset DIR --clone TAUCETI [--commit SHA]

Writes data/declarations.json in the format scripts/fetch_declarations.py writes, so the rest of
the page is unchanged, with these differences:

- the declarations are the dataset's project nodes: every declaration a person wrote, as the
  compiled library has it, with its kind, module and source range;
- `hash` is the declaration's **meaning hash** (semantic_hash, proof-irrelevant, deep): a mark keyed
  by it stays current until the meaning of the declaration or of anything it rests on changes;
- `local` and `content` are the two other hashes of the declaration key (S1), and `package` its
  package; the file also records the dataset it came from (`dataset`), including the modules left
  out because they did not build at the commit (`dataset.unavailable`).

The `example`s that serve as unit tests are still read from the source, as fetch_declarations.py
does: an `example` is elaborated and discarded, so the compiled library does not keep it.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_declarations import UPSTREAM, fingerprint, module_doc, resolve_tests, scan, statement  # noqa: E402

try:
    from evidence_core import Dataset
except ImportError:  # a checkout of evidence-core next to this repository
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evidence-core"))
    from evidence_core import Dataset

ROOT = Path(__file__).resolve().parents[1]
# The kinds the page knows, from the dataset's kind and the keyword the declaration is written with.
KIND = {"theorem": "theorem", "definition": "def", "instance": "instance", "class": "class",
        "structure": "structure", "inductive": "inductive", "axiom": "def", "opaque": "def"}


def read(dataset: Dataset, clone: Path, commit: str) -> dict:
    lines_of: dict[str, list[str]] = {}

    def lines(path: str) -> list[str]:
        if path not in lines_of:
            p = clone / path
            lines_of[path] = p.read_text(encoding="utf-8", errors="replace").splitlines() if p.exists() else []
        return lines_of[path]

    found = []
    for d in dataset.decls:
        if not d.is_project:
            continue
        src = dataset.facet_row("source", d.name)
        if src is None:
            continue
        path, (start, _), (end, _) = src["path"], src["start"], src["end"]
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
    # Modules, and examples, from the source as before.
    modules, examples = [], []
    for file in sorted((clone / "TauCeti").rglob("*.lean")):
        rel = file.relative_to(clone).as_posix()
        source = file.read_text(encoding="utf-8", errors="replace")
        _, tests = scan(source, rel, commit)
        examples += tests
        module = rel[:-len(".lean")].replace("/", ".")
        modules.append({"module": module, "path": rel, "doc": module_doc(source),
                        "url": f"https://github.com/{UPSTREAM}/blob/{commit}/{rel}",
                        "declarations": sum(1 for x in found if x["module"] == module)})
    names = {item["name"] for item in found}
    return {"tauceti": commit, "read": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "modules": modules, "declarations": found, "examples": resolve_tests(examples, names),
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
