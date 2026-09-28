#!/usr/bin/env python3
"""Read the declarations of a library from an extracted dataset (S2), for the page.

  python3 scripts/dataset_declarations.py --dataset DIR --clone CHECKOUT [--commit SHA] [--settings FILE] [--out FILE]

The library is `settings["library"]`: its `repo`, and optionally `modules`, the module prefixes whose
declarations to keep (all by default). Writes data/declarations.json (or `--out`), which the page is
built from:

- the declarations are the dataset's project nodes: every declaration a person wrote, as the
  compiled library has it, with its kind, module and source range; evidence-core reads its text
  from the checkout (without the doc comment, which the page shows apart; a theorem up to its
  proof).
  Private theorems are left out: they are steps of proofs, and no meaning rests on a proof. Private
  definitions stay, under their private names: the meaning of public ones can rest on them;
- `hash` is the declaration's **meaning hash** (S1), which a review is keyed by: it stays current
  until the meaning of the declaration or of anything it rests on changes (the page shows it as the
  version; whether a review still applies is evidence-core's to say);
- the modules, with their docstrings, are the dataset's (`modules.jsonl`).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import evidence_core  # noqa: F401
except ImportError:  # a checkout of evidence-core next to this repository
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evidence-core"))
from evidence_core import Dataset
from evidence_core.source import Sources, split_statement

ROOT = Path(__file__).resolve().parents[1]
# The kinds the page knows, from the dataset's kind and the keyword the declaration is written with.
KIND = {"theorem": "theorem", "definition": "def", "instance": "instance", "class": "class",
        "structure": "structure", "inductive": "inductive", "axiom": "def", "opaque": "def"}


def in_modules(module: str, prefixes: list[str]) -> bool:
    return not prefixes or any(module == p or module.startswith(p + ".") for p in prefixes)


def read(dataset: Dataset, clone: Path, commit: str, repo: str, modules: list[str] | None = None) -> dict:
    """The declarations of `repo`'s dataset, those of the modules under `modules` if given."""
    sources = Sources(clone)
    found = []
    for d in dataset.decls:
        if not d.is_project or (d.name.startswith("_private.") and d.kind == "theorem"):
            continue
        if not in_modules(d.module, modules or []):
            continue
        src = dataset.facet_row("source", d.name)
        span = sources.span(src, doc_comment=False) if src else None
        if span is None:
            continue
        start, end, text = span
        kind = KIND.get(d.kind, "def")
        keyword = src.get("keyword") or ("theorem" if kind == "theorem" else "def")
        if keyword == "lemma":
            kind = "theorem"
        doc = (dataset.facet_row("docstring", d.name) or {}).get("text", "")
        found.append({
            "name": d.name, "kind": kind, "keyword": keyword, "module": d.module, "path": src["path"],
            "line": start, "end": end, "doc": doc, "source": split_statement(text)[0] if kind == "theorem" else text,
            "hash": d.meaning, "url": f"https://github.com/{repo}/blob/{commit}/{src['path']}#L{start}-L{end}"})
    # Modules, from the dataset.
    count = {}
    for item in found:
        count[item["module"]] = count.get(item["module"], 0) + 1
    modules = [{"module": m["name"], "path": m.get("path", ""), "doc": "\n\n".join(m.get("doc") or []),
                "url": f"https://github.com/{repo}/blob/{commit}/{m.get('path', '')}",
                "declarations": count.get(m["name"], 0)} for m in dataset.modules if in_modules(m["name"], modules or [])]
    return {"commit": commit, "read": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "modules": modules, "declarations": found,
            "dataset": {"commit": dataset.commit, "producer": dataset.producer(),
                        "toolchain": dataset.toolchain, "hasher": dataset.hasher,
                        "counts": dataset.meta.get("counts", {}),
                        "unavailable": sorted(dataset.unavailable)}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, required=True, help="an extracted dataset (S2)")
    parser.add_argument("--clone", type=Path, required=True, help="a checkout of the library at the dataset's commit")
    parser.add_argument("--commit", help="its commit (default: the dataset's)")
    parser.add_argument("--settings", type=Path, default=ROOT / "data" / "settings.json",
                        help="the library: its repository, and the modules to keep")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "declarations.json")
    args = parser.parse_args()
    lib = json.loads(args.settings.read_text(encoding="utf-8"))["library"]
    dataset = Dataset.load(args.dataset)
    commit = args.commit or dataset.commit
    head = subprocess.run(["git", "-C", str(args.clone), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if head and head != dataset.commit:
        print(f"warning: the checkout is at {head[:10]}, the dataset at {dataset.commit[:10]}", file=sys.stderr)
    out = read(dataset, args.clone, commit, lib["repo"], lib.get("modules"))
    args.out.write_text(json.dumps(out, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(out['declarations'])} declarations (from the dataset) from {len(out['modules'])} modules "
          f"at {commit[:7]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
