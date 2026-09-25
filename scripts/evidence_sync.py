#!/usr/bin/env python3
"""Keep reviews/evidence.jsonl (S3 evidence records) in step with the ledgers.

  python3 scripts/evidence_sync.py --dataset DIR [--at COMMIT=DIR ...]

The intake is unchanged: scripts/reviews.py appends marks, tests, named results and problem events
to the ledgers of reviews/. This script converts every ledger entry that has no S3 record yet into
one, keyed by the hashes of a dataset (S2) of the commit the entry was made at: the pinned commit's
dataset for entries made from the page, and `--at` datasets for older commits. An entry made at a
commit with no dataset gets the pinned dataset's hashes, and its record says so
(`migration.hashes_from`).

Each converted record carries `migration.key`, derived from the ledger entry, so running this
again converts nothing twice: it can run after every recorded event.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from evidence_core import Dataset, with_id
    from evidence_core import migrate as mig
    from evidence_core import records as rec
except ImportError:  # a checkout of evidence-core next to this repository
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evidence-core"))
    from evidence_core import Dataset, with_id
    from evidence_core import migrate as mig
    from evidence_core import records as rec

ROOT = Path(__file__).resolve().parents[1]
REVIEWS = ROOT / "reviews"
EVIDENCE = REVIEWS / "evidence.jsonl"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def key(entry: dict) -> str:
    """A ledger entry's identity: what it is, about what, by whom, when."""
    schema = entry.get("schema", "")
    about = entry.get("decl") or f"#{entry.get('issue')}"
    extra = entry.get("test", "") or entry.get("event", "")
    return f"{schema}|{about}|{extra}|{entry.get('by', '')}|{entry.get('at', '')}"


def keyed(record: dict, k: str) -> dict:
    record = {key_: v for key_, v in record.items() if key_ != "id"}
    record.setdefault("migration", {})["key"] = k
    return with_id(record)


def sync(pinned: Dataset, at: dict[str, Dataset], repo: str, evidence_path: Path = EVIDENCE,
         inherited: dict | None = None) -> list[dict]:
    """Converts the ledger entries that have no S3 record yet; returns the new records.

    `inherited` ({"repo", "until"}) names the repository whose issues the entries made before
    `until` came from, for a ledger carried over from another repository."""
    existing = load(evidence_path)
    done = {r.get("migration", {}).get("key") for r in existing}
    new: list[dict] = []
    datasets = dict(at)
    datasets.setdefault(pinned.commit, pinned)

    def origin_repo(entries) -> str:
        at_ = min((e.get("at", "") for e in entries), default="")
        if inherited and at_ and at_ < inherited["until"]:
            return inherited["repo"]
        return repo

    def convert(records=(), tests=(), named=(), problems=()) -> list[dict]:
        entries = list(records) + list(tests) + list(named) + list(problems)
        report = mig.from_reviewed_by(list(records), list(tests), list(named), list(problems), origin_repo(entries),
                                      datasets, pinned)
        for s in report.skipped:
            print(f"skipped: {s}", file=sys.stderr)
        return report.migrated

    for entry in load(REVIEWS / "records.jsonl"):
        if key(entry) not in done:
            new += [keyed(r, key(entry)) for r in convert(records=[entry])]
    for entry in load(REVIEWS / "tests.jsonl"):
        if key(entry) not in done:
            new += [keyed(r, key(entry)) for r in convert(tests=[entry])]
    for entry in load(REVIEWS / "named.jsonl"):
        if key(entry) not in done:
            new += [keyed(r, key(entry)) for r in convert(named=[entry])]
    # Problem events: a report becomes a problem review; closing and reopening become statuses of
    # it, which must name the report's record, whether converted now or earlier.
    reports = {r["origin"]["ref"]: r for r in existing + new
               if r.get("kind") == "review" and r.get("verdict") == "problem" and r.get("origin")}
    for entry in sorted(load(REVIEWS / "problems.jsonl"), key=lambda e: e.get("at", "")):
        if key(entry) in done:
            continue
        ref = f"{origin_repo([entry])}#{entry.get('issue')}"
        if entry.get("event") == "reported":
            for r in convert(problems=[entry]):
                r = keyed(r, key(entry))
                reports[ref] = r
                new.append(r)
        elif entry.get("event") in ("closed", "reopened") and ref in reports:
            state = "reopened" if entry["event"] == "reopened" else \
                {"fixed": "fixed", "not planned": "invalid", "duplicate": "invalid"}.get(entry.get("resolution", ""), "invalid")
            new.append(keyed({"schema": "ltb-evidence/0", "kind": "status", "target": reports[ref]["id"],
                              "state": state, "at": entry.get("at", ""),
                              "by": {"kind": "person", "identity": {"kind": "github", "id": entry.get("by", "")},
                                     "involvement": "unknown"},
                              "origin": {"kind": "issue", "ref": ref}}, key(entry)))
    if new:
        rec.append(evidence_path, new)
    return new


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, required=True, help="the dataset of the pinned commit")
    parser.add_argument("--at", action="append", default=[], help="COMMIT=DIR: a dataset of an older commit")
    args = parser.parse_args()
    settings = json.loads((ROOT / "data" / "settings.json").read_text())
    pinned = Dataset.load(args.dataset)
    at = {}
    for spec in args.at:
        commit, _, path = spec.partition("=")
        at[commit] = Dataset.load(path)
    new = sync(pinned, at, settings["repo"], inherited=settings.get("inherited_ledger"))
    print(f"{len(new)} new evidence records in {EVIDENCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
